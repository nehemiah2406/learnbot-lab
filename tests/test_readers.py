"""File readers and the self-check of every type (small files made here; no AI, no internet)."""

import json
import zipfile
from pathlib import Path

import pytest
from test_quiz import FakeChain, FakeSearcher

from learnbot import config, readers
from learnbot.answer import ANSWERED, answer_question
from learnbot.book import make_chapter, render
from learnbot.chunking import Chunk
from learnbot.eval_check import is_plain_filename
from learnbot.evaluate import feature_gate
from learnbot.flashcards import make_card
from learnbot.index import load_document
from learnbot.notebook import Notebook
from learnbot.pdf_check import FAIL, OK, WARNING
from learnbot.proof import shown_where
from learnbot.reading import ask_page, view_page
from learnbot.readers import check_file, detect_type, part_chunks, read_file
from learnbot.study import spread_pieces
from learnbot.upload import find_document

LONG = "This sentence has enough words in it so that the file does not look nearly empty at all today."


def write(folder, name, content):
    path = Path(folder) / name
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")
    return path


# --- Type from the content ------------------------------------------------------------
@pytest.mark.parametrize("name, content, kind", [
    ("a.txt", "plain text", readers.TXT),
    ("a.md", "# Title", readers.MD),
    ("a.csv", "a,b\n1,2", readers.CSV),
    ("a.html", "<p>hi</p>", readers.HTML),
    ("a.htm", "<p>hi</p>", readers.HTML),
    ("a.txt", "<!DOCTYPE html><html></html>", readers.HTML),
    ("renamed.txt", b"%PDF-1.7 rest", readers.PDF),
    ("a.png", b"\x89PNG\r\n\x1a\nrest", readers.IMAGE),
    ("renamed.txt", b"\xff\xd8\xffrest", readers.IMAGE),
    ("a.doc", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1rest", readers.OLD_OFFICE),
    ("a.exe", b"MZ\x00\x00rest", None),
    ("renamed.txt", b"MZ\x00\x00rest", None),
    ("a.mp3", b"ID3\x00rest", None),
    ("a.xyz", "text with an unknown extension", None),
    ("a.pdf", "text pretending to be a PDF", None),
])
def test_type_comes_from_the_content(tmp_path, name, content, kind):
    assert detect_type(write(tmp_path, name, content)) == kind


def make_zip(path, *names):
    with zipfile.ZipFile(path, "w") as z:
        for name in names:
            z.writestr(name, "x")
    return path


@pytest.mark.parametrize("names, kind", [
    (("[Content_Types].xml", "word/document.xml"), readers.DOCX),
    (("[Content_Types].xml", "ppt/presentation.xml"), readers.PPTX),
    (("[Content_Types].xml", "xl/workbook.xml"), readers.XLSX),
    (("[Content_Types].xml", "other/thing.xml"), None),
    (("holiday.jpg",), None),
])
def test_office_type_comes_from_inside_the_zip(tmp_path, names, kind):
    assert detect_type(make_zip(tmp_path / "file.zip", *names)) == kind


# --- Plain text and Markdown ----------------------------------------------------------
def test_text_has_one_part_per_paragraph_with_line_numbers(tmp_path):
    parts = read_file(write(tmp_path, "a.txt", "First line\nsecond line\n\nThird\n\n\nFourth\nfifth\nsixth\n"))
    assert [(p.text, p.label) for p in parts] == [("First line second line", "Lines 1-2"), ("Third", "Line 4"),
                                                  ("Fourth fifth sixth", "Lines 7-9")]


def test_text_in_windows_encoding_is_read(tmp_path):
    assert "café" in read_file(write(tmp_path, "a.txt", "café au lait".encode("cp1252")))[0].text


def test_text_with_a_byte_order_mark_is_clean(tmp_path):
    assert read_file(write(tmp_path, "a.txt", "﻿Hello".encode("utf-8")))[0].text == "Hello"


def test_markdown_headings_are_titles_not_parts(tmp_path):
    parts = read_file(write(tmp_path, "a.md", "# One\n\nText one\n\n## Two ##\nText two\n"))
    assert [(p.text, p.title, p.label) for p in parts] == [("Text one", "One", "Line 3"), ("Text two", "Two", "Line 6")]


def test_hash_in_plain_text_is_not_a_heading(tmp_path):
    assert read_file(write(tmp_path, "a.txt", "# not a title\n"))[0].text == "# not a title"


# --- CSV ------------------------------------------------------------------------------
def test_csv_rows_keep_their_column_names_and_row_numbers(tmp_path):
    parts = read_file(write(tmp_path, "a.csv", 'Light,Range\nmasthead,6 miles\n\nside,"3, or more miles"\n'))
    assert [(p.text, p.label) for p in parts] == [("Light: masthead; Range: 6 miles", "Row 2"),
                                                  ("Light: side; Range: 3, or more miles", "Row 4")]


@pytest.mark.parametrize("delimiter", [";", "\t", "|"])
def test_csv_other_delimiters(tmp_path, delimiter):
    parts = read_file(write(tmp_path, "a.csv", f"A{delimiter}B\n1{delimiter}2\n"))
    assert parts[0].text == "A: 1; B: 2"


def test_csv_empty_cells_and_extra_cells(tmp_path):
    assert read_file(write(tmp_path, "a.csv", "A,B\n1,,extra\n"))[0].text == "A: 1; extra"


def test_csv_with_only_a_header_has_no_parts(tmp_path):
    assert read_file(write(tmp_path, "a.csv", "A,B\n")) == []


# --- HTML -----------------------------------------------------------------------------
HTML = """<html><head><title>No</title></head><body><script>var a = "99 feet";</script><style>p{}</style>
<h1>First</h1><p>One   <b>bold</b> two.</p><ul><li>Item</li></ul>
<h2>Second</h2><p>Three.</p><table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr></table>
<div><p>Inside a div.</p></div><div>Bare div.</div></body></html>"""


def test_html_parts_have_heading_and_paragraph_number(tmp_path):
    parts = read_file(write(tmp_path, "a.html", HTML))
    assert [(p.text, p.label, p.title) for p in parts] == [
        ("One bold two.", "First, paragraph 1", "First"), ("Item", "First, paragraph 2", "First"),
        ("Three.", "Second, paragraph 1", "Second"), ("A | B", "Second, paragraph 2", "Second"),
        ("1 | 2", "Second, paragraph 3", "Second"), ("Inside a div.", "Second, paragraph 4", "Second"),
        ("Bare div.", "Second, paragraph 5", "Second"),
    ]


def test_html_never_reads_scripts_or_styles(tmp_path):
    text = " ".join(p.text for p in read_file(write(tmp_path, "a.html", HTML)))
    assert "99 feet" not in text and "p{}" not in text and "No" not in text


def test_html_without_a_heading_is_labelled_by_paragraph(tmp_path):
    assert read_file(write(tmp_path, "a.html", "<p>Only.</p>"))[0].label == "Paragraph 1"


# --- Parts as search pieces -----------------------------------------------------------
def test_parts_become_pieces_with_their_location(tmp_path):
    chunks = part_chunks("a.txt", read_file(write(tmp_path, "a.txt", "One\n\nTwo\n")))
    assert [(c.page, c.text, c.where) for c in chunks] == [(1, "One", "Line 1"), (2, "Two", "Line 3")]


def test_long_part_is_split_but_stays_one_location():
    part = readers.Part(" ".join(["Word word word word word."] * 60), "Line 1")
    chunks = part_chunks("a.txt", [part])
    assert len(chunks) > 1 and {c.page for c in chunks} == {1} and {c.where for c in chunks} == {"Line 1"}


def test_pdf_piece_has_no_label():
    assert Chunk("a.pdf", 3, "T", "text").where == ""


def test_load_document_works_for_text_and_is_cached(tmp_path):
    path = write(tmp_path, "a.md", "# T\n\nOne two\n")
    first = load_document(path, tmp_path / "store")
    again = load_document(path, tmp_path / "store")
    for doc in (first, again):
        assert doc.pages == {1: "One two"} and doc.labels == {1: "Line 3"}
        assert (doc.chunks[0].title, doc.chunks[0].where) == ("T", "Line 3")


# --- Self-check -----------------------------------------------------------------------
def test_good_file_is_ok(tmp_path):
    result = check_file(write(tmp_path, "a.txt", f"{LONG}\n\n{LONG}\n"))
    assert (result.verdict, result.page_count) == (OK, 2) and result.reasons == ["File looks good."]


def test_very_little_text_is_a_warning(tmp_path):
    assert check_file(write(tmp_path, "a.txt", "Just a few words.")).verdict == WARNING


@pytest.mark.parametrize("name, content, message", [
    ("a.txt", "", "No text"),
    ("a.txt", "   \n\n  \n", "No text"),
    ("a.csv", "A,B\n", "No text"),
    ("a.html", "<script>x</script>", "No text"),
    ("a.exe", b"MZ\x00\x00", "can't be read"),
    ("a.zip", b"PK\x03\x04broken", "can't be read"),
    ("a.xyz", "text", "can't be read"),
    ("a.doc", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", "save it as"),
    ("a.png", b"\x89PNG\r\n\x1a\n", "can't be read yet"),
])
def test_files_that_cannot_be_used_fail_with_a_clear_message(tmp_path, name, content, message):
    result = check_file(write(tmp_path, name, content))
    assert result.verdict == FAIL and message in result.reasons[0]


def test_file_too_big_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(readers, "check_size_limit", lambda size: "File is too big.")
    assert check_file(write(tmp_path, "a.txt", LONG)).reasons == ["File is too big."]


def test_library_error_text_is_never_shown(tmp_path, monkeypatch):
    def broken(path, kind):
        raise RuntimeError("secret library message")
    monkeypatch.setattr(readers, "read_parts", broken)
    result = check_file(write(tmp_path, "a.txt", LONG))
    assert result.verdict == FAIL and result.reasons == [readers.CORRUPTED]


def test_pdf_goes_to_the_pdf_self_check(tmp_path, monkeypatch):
    monkeypatch.setattr(readers, "check_pdf", lambda path: "pdf result")
    assert check_file(write(tmp_path, "a.pdf", b"%PDF-1.7")) == "pdf result"


def test_uploaded_file_is_found_by_its_name_for_any_type(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "UPLOAD_DIR", str(tmp_path))
    write(tmp_path, "a.md", "text")
    assert find_document("a.md") == tmp_path / "a.md"


# --- The location reaches every feature -----------------------------------------------
QUOTE = "Light: masthead; Range: 6 miles"
ROW = Chunk("a.csv", 1, "", QUOTE, "Row 2")


def chat_reply():
    return json.dumps({"found": True, "answer": "6 miles", "sources": [{"doc": "a.csv", "page": 1, "quote": QUOTE}]})


def card_reply():
    return json.dumps({"found": True, "question": "What is the masthead range?", "answer": "6 miles",
                       "source": {"doc": "a.csv", "page": 1, "quote": QUOTE}})


def test_chat_answer_shows_the_row_not_a_page():
    ans = answer_question("What is the masthead range?", FakeSearcher([ROW]), FakeChain(chat_reply()))
    assert ans.status == ANSWERED and shown_where(ans.sources[0]) == "Row 2"


def test_pdf_answer_still_shows_its_page():
    assert shown_where({"doc": "a.pdf", "page": 7, "where": ""}) == "p.7"
    assert shown_where({"doc": "a.pdf", "page": 7}) == "p.7"


def test_flashcard_shows_the_row():
    card = make_card("masthead", FakeSearcher([ROW]), FakeChain(card_reply()))
    assert card.status == ANSWERED and shown_where(card.sources[0]) == "Row 2"


def test_notebook_keeps_the_row_after_a_restart_and_answers_from_it(tmp_path):
    ans = answer_question("What is the masthead range?", FakeSearcher([ROW]), FakeChain(chat_reply()))
    Notebook(tmp_path).save("chat", ans, "What is the masthead range?")
    again = Notebook(tmp_path)
    assert shown_where(again.items[0]["sources"][0]) == "Row 2"
    assert shown_where(again.ask("What is the masthead range?", FakeChain(chat_reply())).sources[0]) == "Row 2"


def test_book_shows_the_row():
    fact = {"question": "What is the masthead range?", "answer": "6 miles",
            "source": {"doc": "a.csv", "page": 1, "quote": QUOTE}}
    chapter = make_chapter("masthead", FakeSearcher([ROW]), FakeChain(json.dumps({"found": True, "facts": [fact]})))
    text = render("a.csv", [chapter])
    assert "Row 2" in text and "Page 1" not in text


def test_reading_mode_works_without_a_pdf(tmp_path):
    path = write(tmp_path, "a.csv", "Light,Range\nmasthead,6 miles\nside,3 miles\n")
    document = load_document(path, tmp_path / "store")
    view = view_page(document, path, 2)
    assert (view.text, view.where, view.previous, view.next, view.warning) == ("Light: side; Range: 3 miles", "Row 3", 1, None, "")
    ans = ask_page("What is the side range?", document, 2, FakeChain(json.dumps(
        {"found": True, "answer": "3 miles", "sources": [{"doc": "a.csv", "page": 2, "quote": "Light: side; Range: 3 miles"}]})))
    assert ans.status == ANSWERED and shown_where(ans.sources[0]) == "Row 3"


def test_answer_from_the_wrong_row_is_refused():
    other = json.dumps({"found": True, "answer": "9 miles", "sources": [
        {"doc": "a.csv", "page": 1, "quote": "Light: masthead; Range: 9 miles"}]})
    ans = answer_question("What is the masthead range?", FakeSearcher([ROW]), FakeChain(other))
    assert ans.status != ANSWERED


def test_file_with_only_short_rows_can_still_be_self_tested():
    rows = [Chunk("a.csv", n, "", "Light: masthead; Range: 6 miles", f"Row {n}") for n in range(1, 11)]
    assert len(spread_pieces(rows, 3)) == 3


def test_long_pieces_are_still_preferred_over_short_rows():
    long_text = " ".join(["word"] * 30)
    chunks = [Chunk("a.txt", 1, "", "Light: masthead; Range: 6 miles"), Chunk("a.txt", 2, "", long_text)]
    assert [c.page for c in spread_pieces(chunks, 2)] == [2]


def test_every_test_file_type_is_accepted_by_the_checker():
    for name in ("a.pdf", "a.txt", "a.md", "a.csv", "a.html", "a.docx", "a.pptx", "a.xlsx"):
        assert is_plain_filename(name)
    assert not is_plain_filename("a.exe") and not is_plain_filename("folder/a.txt")


def test_type_gate_needs_two_of_three():
    assert feature_gate(["right", "right", "missed", "refused"], 1, config.FILE_TYPE_MIN_KEPT) == []
    assert feature_gate(["right", "missed", "missed", "refused"], 1, config.FILE_TYPE_MIN_KEPT) == ["only 1 kept (at least 2 needed)"]
    assert feature_gate(["right", "right", "right", "trap_answered"], 1, config.FILE_TYPE_MIN_KEPT) == ["traps answered 1"]
# --- Word, PowerPoint, Excel ----------------------------------------------------------
def make_docx(path):
    from docx import Document

    doc = Document()
    doc.add_paragraph("Before any heading.")
    doc.add_heading("Locks", level=1)
    doc.add_paragraph("First   paragraph.")
    doc.add_paragraph("")
    table = doc.add_table(rows=2, cols=2)
    table.rows[0].cells[0].text, table.rows[0].cells[1].text = "Item", "Limit"
    table.rows[1].cells[0].text, table.rows[1].cells[1].text = "Line", "50 feet"
    doc.add_heading("Fines", level=2)
    doc.add_paragraph("Second paragraph.")
    doc.save(path)
    return path


def test_docx_parts_have_heading_and_paragraph_number_in_order(tmp_path):
    parts = read_file(make_docx(tmp_path / "a.docx"))
    assert [(p.text, p.label, p.title) for p in parts] == [
        ("Before any heading.", "Paragraph 1", ""), ("First paragraph.", "Locks, paragraph 1", "Locks"),
        ("Item | Limit", "Locks, paragraph 2", "Locks"), ("Line | 50 feet", "Locks, paragraph 3", "Locks"),
        ("Second paragraph.", "Fines, paragraph 1", "Fines"),
    ]


def make_pptx(path):
    from pptx import Presentation
    from pptx.util import Inches

    deck = Presentation()
    first = deck.slides.add_slide(deck.slide_layouts[1])
    first.shapes.title.text = "Safety"
    first.placeholders[1].text = "Carry a whistle."
    first.notes_slide.notes_text_frame.text = "Secret speaker note."
    deck.slides.add_slide(deck.slide_layouts[6])  # a blank slide has no part, and keeps its number free
    third = deck.slides.add_slide(deck.slide_layouts[6])
    table = third.shapes.add_table(1, 2, Inches(1), Inches(1), Inches(4), Inches(1)).table
    table.cell(0, 0).text, table.cell(0, 1).text = "Flares", "42 months"
    deck.save(path)
    return path


def test_pptx_parts_are_slides_with_their_real_numbers(tmp_path):
    parts = read_file(make_pptx(tmp_path / "a.pptx"))
    assert [(p.text, p.label, p.title) for p in parts] == [
        ("Safety\nCarry a whistle.", "Slide 1", "Safety"), ("Flares | 42 months", "Slide 3", "")]


def test_pptx_speaker_notes_are_not_read(tmp_path):
    assert "Secret" not in " ".join(p.text for p in read_file(make_pptx(tmp_path / "a.pptx")))


def make_xlsx(path):
    from datetime import date

    from openpyxl import Workbook

    book = Workbook()
    sheet = book.active
    sheet.title = "Lights"
    sheet.append(["Light", "Range", "Share", "Date", "Note"])
    sheet.append(["masthead", 6.0, 0.5, date(2026, 11, 6), None])
    sheet.append([None, None, None, None, None])
    sheet.append(["side", 2.5, 0.125, None, "ok"])
    sheet["C2"].number_format = "0%"
    sheet["C4"].number_format = "0.0%"
    other = book.create_sheet("Empty")
    other.append([None])
    third = book.create_sheet("Stairs")
    third.append(["Item"])
    third.append(["Landing"])
    book.save(path)
    return path


def test_xlsx_parts_have_sheet_row_and_column_names_as_the_user_sees_them(tmp_path):
    parts = read_file(make_xlsx(tmp_path / "a.xlsx"))
    assert [(p.text, p.label, p.title) for p in parts] == [
        ("Light: masthead; Range: 6; Share: 50%; Date: 2026-11-06", "Lights, row 2", "Lights"),
        ("Light: side; Range: 2.5; Share: 12.5%; Note: ok", "Lights, row 4", "Lights"),
        ("Item: Landing", "Stairs, row 2", "Stairs"),
    ]


@pytest.mark.parametrize("state", ["hidden", "veryHidden"])
def test_xlsx_hidden_sheets_are_not_read(tmp_path, state):
    from openpyxl import Workbook

    book = Workbook()
    book.active.append(["Item", "Limit"])
    book.active.append(["Landing", "30 inches"])
    secret = book.create_sheet("Secret")
    secret.append(["Item", "Limit"])
    secret.append(["Landing", "99 inches"])
    secret.sheet_state = state
    book.save(tmp_path / "a.xlsx")
    assert [p.text for p in read_file(tmp_path / "a.xlsx")] == ["Item: Landing; Limit: 30 inches"]


def test_xlsx_with_only_hidden_sheets_has_no_text(tmp_path):
    from openpyxl import Workbook

    book = Workbook()
    book.active.append(["Item"])
    book.active.append(["Landing"])
    visible = book.create_sheet("Empty")
    book.active.sheet_state = "hidden"
    book.active = book.index(visible)
    book.save(tmp_path / "a.xlsx")
    assert check_file(tmp_path / "a.xlsx").reasons == [readers.NO_TEXT]


@pytest.mark.parametrize("name, inside", [
    ("a.docx", "word/document.xml"), ("a.pptx", "ppt/presentation.xml"), ("a.xlsx", "xl/workbook.xml"),
])
def test_damaged_office_file_fails_cleanly(tmp_path, name, inside):
    result = check_file(make_zip(tmp_path / name, "[Content_Types].xml", inside))
    assert result.verdict == FAIL and result.reasons == [readers.CORRUPTED]


@pytest.mark.parametrize("maker, name", [(make_docx, "a.docx"), (make_pptx, "a.pptx"), (make_xlsx, "a.xlsx")])
def test_office_files_pass_the_self_check_and_load(tmp_path, maker, name):
    path = maker(tmp_path / name)
    assert detect_type(path) == name.split(".")[1]
    assert check_file(path).verdict in (OK, WARNING)
    assert load_document(path, tmp_path / "store").labels


def test_office_file_with_no_text_fails(tmp_path):
    from docx import Document

    Document().save(tmp_path / "a.docx")
    assert check_file(tmp_path / "a.docx").reasons == [readers.NO_TEXT]
