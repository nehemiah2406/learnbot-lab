"""Tests for learnbot.chunking with made-up page text."""

from learnbot.chunking import MAX_WORDS, chunk_page, is_heading, split_long

FULL = "x" * 70  # a full line on the made-up page is 70 characters


def page(*lines):
    return "\n".join(lines)


def test_chunks_keep_doc_and_page():
    chunks = chunk_page("book.pdf", 7, "(a) A vessel shall keep a proper look-out at all times by sight.")
    assert [(c.doc, c.page) for c in chunks] == [("book.pdf", 7)]


def test_split_at_paragraph_markers():
    text = page(
        "(a) The first paragraph has enough words to stand alone as a piece here.",
        "(b) The second paragraph also has enough words to stand alone as one.",
        "(12) A numbered paragraph with enough words to be its own separate piece.",
        "§ 83.22 A section paragraph with enough words to be its own separate piece.",
    )
    chunks = chunk_page("book.pdf", 1, text)
    assert [c.text[:4] for c in chunks] == ["(a) ", "(b) ", "(12)", "§ 83"]


def test_bullets_stay_with_their_paragraph():
    text = page(
        "(a) In vessels of 50 meters or more in length the lights are visible at:",
        "− a masthead light, 6 miles;",
        "− a sidelight, 3 miles;",
    )
    chunks = chunk_page("book.pdf", 1, text)
    assert len(chunks) == 1
    assert "50 meters" in chunks[0].text and "6 miles" in chunks[0].text


def test_heading_lines_become_title():
    text = page(
        "Rule 22",
        "Visibility of Lights",
        "The lights prescribed in these Rules shall be visible at minimum ranges given below in full.",
        FULL,
    )
    chunks = chunk_page("book.pdf", 3, text)
    assert chunks[0].title == "Rule 22 Visibility of Lights"
    assert chunks[0].text.startswith("The lights prescribed")
    assert "Rule 22" in chunks[0].search_text


def test_new_heading_starts_new_piece_with_new_title():
    text = page(
        "Fire Extinguishers",
        "Boats must carry approved fire extinguishers of the right size and type on board.",
        "Ventilation",
        "Boats with gasoline engines in closed compartments must have working ventilation systems.",
        FULL,
    )
    chunks = chunk_page("guide.pdf", 20, text)
    assert [c.title for c in chunks] == ["Fire Extinguishers", "Ventilation"]


def test_short_list_items_join_previous_piece():
    text = page(
        "(a) In a vessel of 50 meters or more in length these lights are required:",
        "(i) A masthead light, 6 miles;",
        "(ii) A sidelight, 3 miles;",
    )
    chunks = chunk_page("book.pdf", 1, text)
    assert len(chunks) == 1
    assert "50 meters" in chunks[0].text and "(ii) A sidelight, 3 miles;" in chunks[0].text


def test_paragraph_number_only_lines_are_skipped():
    text = page("(37)", "(38) These are in nautical miles unless otherwise stated in the text here.")
    chunks = chunk_page("pilot.pdf", 2, text)
    assert len(chunks) == 1 and chunks[0].text.startswith("(38)")


def test_short_prose_line_in_narrow_column_is_not_heading():
    # Narrow column: full line is ~50 chars; this 8-word line is prose, not a heading.
    assert not is_heading("a channel as determined by hydrographic surveys and", 52)
    assert not is_heading("and common sense are continuing requirements for", 52)
    assert is_heading("Cable ferries", 52)


def test_page_numbers_and_sentences_are_not_headings():
    assert not is_heading("36", 70)
    assert not is_heading("Same for International.", 70)


def test_long_piece_split_at_sentence_ends():
    sentence = "This sentence has exactly ten words in it for testing. "
    text = sentence * 40  # 400 words
    parts = split_long(text.strip())
    assert len(parts) > 1
    assert all(len(p.split()) <= MAX_WORDS for p in parts)
    assert all(p.endswith(".") for p in parts)


def test_pieces_never_cross_pages():
    first = chunk_page("book.pdf", 1, "(a) This sentence continues on the next page and is cut")
    second = chunk_page("book.pdf", 2, "here because pieces never cross a page boundary at all.")
    assert {c.page for c in first} == {1} and {c.page for c in second} == {2}
