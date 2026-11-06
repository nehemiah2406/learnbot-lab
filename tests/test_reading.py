"""Reading mode and the mixed-page check, with a fake AI and fake pages (no network, no PDF)."""

import json

import pytest
from test_quiz import FakeChain

from learnbot import reading
from learnbot.answer import AI_BUSY_STATUS, ANSWERED, REFUSED
from learnbot.chunking import Chunk
from learnbot.index import Document
from learnbot.pdf_text import page_is_mixed
from learnbot.reading import MIXED_WARNING, NOT_ON_PAGE, ask_page, view_page

PAGE_1 = "Flares expire 42 months after the date of manufacture."
PAGE_2 = "Extinguishers expire 12 years from the date stamped on the bottom."
PAGE_3 = "A third page about anchors and chains in harbors."
PIECES = [Chunk("g.pdf", 1, "Flares", PAGE_1), Chunk("g.pdf", 2, "Extinguishers", PAGE_2), Chunk("g.pdf", 3, "Anchors", PAGE_3)]
DOCUMENT = Document("g.pdf", "hash", {1: PAGE_1, 2: PAGE_2, 3: PAGE_3}, PIECES)


def reply(answer="42 months", page=1, quote=PAGE_1):
    return json.dumps({"found": True, "answer": answer, "sources": [{"doc": "g.pdf", "page": page, "quote": quote}]})


class FakePdf:
    def __init__(self, mixed):
        self.pages = [mixed] * 3

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


@pytest.fixture
def clean_layout(monkeypatch):
    monkeypatch.setattr(reading.pdfplumber, "open", lambda path: FakePdf("page"))
    monkeypatch.setattr(reading, "page_is_mixed", lambda page: False)


# --- Reading --------------------------------------------------------------------------
def test_page_shows_exact_text_number_and_next_previous(clean_layout):
    view = view_page(DOCUMENT, "g.pdf", 2)
    assert (view.text, view.page, view.total, view.previous, view.next, view.warning) == (PAGE_2, 2, 3, 1, 3, "")


def test_first_page_has_no_previous_and_last_no_next(clean_layout):
    assert view_page(DOCUMENT, "g.pdf", 1).previous is None
    assert view_page(DOCUMENT, "g.pdf", 3).next is None


@pytest.mark.parametrize("page", [0, 4, -1])
def test_page_outside_the_document_is_a_clear_error(page):
    with pytest.raises(ValueError, match="pages 1 to 3"):
        view_page(DOCUMENT, "g.pdf", page)
    with pytest.raises(ValueError, match="pages 1 to 3"):
        ask_page("q", DOCUMENT, page, FakeChain())


def test_mixed_page_shows_the_warning(monkeypatch):
    monkeypatch.setattr(reading.pdfplumber, "open", lambda path: FakePdf("page"))
    monkeypatch.setattr(reading, "page_is_mixed", lambda page: True)
    assert view_page(DOCUMENT, "g.pdf", 2).warning == MIXED_WARNING
    assert "mixed columns" in MIXED_WARNING


def test_reading_asks_no_ai():
    assert not hasattr(reading, "default_chain")


# --- Questions about the page ---------------------------------------------------------
def test_question_is_answered_from_this_page():
    ans = ask_page("When do flares expire?", DOCUMENT, 1, FakeChain(reply()))
    assert ans.status == ANSWERED and ans.text == "42 months" and ans.sources[0]["page"] == 1


def test_only_this_pages_pieces_are_sent():
    chain = FakeChain('{"found": false}')
    ask_page("When do flares expire?", DOCUMENT, 1, chain)
    assert PAGE_1 in chain.prompts[0] and PAGE_2 not in chain.prompts[0]


def test_answer_from_another_page_is_refused():
    other = reply(answer="12 years", page=2, quote=PAGE_2)
    ans = ask_page("When do extinguishers expire?", DOCUMENT, 1, FakeChain(other))
    assert (ans.status, ans.text, ans.reason) == (REFUSED, NOT_ON_PAGE, "proof:page_not_sent")


def test_question_with_no_word_on_this_page_asks_no_ai():
    chain = FakeChain()
    assert ask_page("How heavy is an anchor?", DOCUMENT, 1, chain).text == NOT_ON_PAGE and chain.prompts == []


@pytest.mark.parametrize("text, reason", [
    (reply(answer="50 months"), "proof:number_not_in_quote"),
    (reply(quote="Flares expire 50 months after the date of manufacture."), "proof:quote_not_on_page"),
    ('{"found": false}', "llm_not_found"),
    ("not json", "bad_json"),
])
def test_anything_unproved_says_not_on_this_page(text, reason):
    ans = ask_page("When do flares expire?", DOCUMENT, 1, FakeChain(text))
    assert (ans.status, ans.text, ans.reason) == (REFUSED, NOT_ON_PAGE, reason)


def test_busy_ai_is_a_friendly_message():
    ans = ask_page("When do flares expire?", DOCUMENT, 1, FakeChain(fail=True))
    assert ans.status == AI_BUSY_STATUS and "try again" in ans.text and not ans.sources


# --- Mixed-page check -----------------------------------------------------------------
class FakePage:
    width = 612

    def __init__(self, lines):
        self.lines = lines

    def extract_words(self):
        words = []
        for row, (left, right) in enumerate(self.lines):
            for count, start in ((left, 40), (right, 340)):
                words += [{"text": "word", "x0": start + 30 * i, "x1": start + 26 + 30 * i, "top": row * 14.0}
                          for i in range(count)]
        return words


def test_two_sides_on_many_lines_is_mixed():
    # Under 40 words, so no columns are found and the page is read row by row.
    assert page_is_mixed(FakePage([(3, 3)] * 6))


def test_page_read_column_by_column_is_not_mixed():
    assert not page_is_mixed(FakePage([(5, 5)] * 20))


def test_full_lines_with_no_wide_gap_are_not_mixed():
    assert not page_is_mixed(FakePage([(9, 0)] * 20))


def test_table_with_short_cells_is_not_mixed():
    assert not page_is_mixed(FakePage([(2, 1)] * 20))


def test_a_few_gaps_on_a_long_page_are_not_mixed():
    assert not page_is_mixed(FakePage([(4, 4)] * 2 + [(9, 0)] * 30))
