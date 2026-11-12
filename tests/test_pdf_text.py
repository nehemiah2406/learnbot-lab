"""Tests for column-aware reading (learnbot.pdf_text) with made-up word positions."""

from learnbot.pdf_text import find_gutters, group_lines, order_words

PAGE_WIDTH = 600
LINE_HEIGHT = 12


def words_line(text, x0, top, word_width=30, gap=4):
    """Fake pdfplumber words for one line of text starting at x0."""
    words, x = [], x0
    for token in text.split():
        words.append({"text": token, "x0": x, "x1": x + word_width, "top": top})
        x += word_width + gap
    return words


def two_column_page(rows=12, header=None):
    """Left column says 'left a1 a2 ...', right column 'right b1 b2 ...' on each line."""
    words, top = [], 50
    if header:
        words += words_line(header, 150, 20, word_width=60)
    for i in range(rows):
        words += words_line(f"left{i} a b c d e", 40, top + i * LINE_HEIGHT)  # x 40..240
        words += words_line(f"right{i} f g h i j", 330, top + i * LINE_HEIGHT)  # x 330..530
    return words


def test_single_column_page_has_no_gutter():
    words = []
    for i in range(12):
        # Word gaps fall in different places on each line, like real prose.
        words += words_line("one two three four five six seven eight", 40 + (i % 5) * 7, 50 + i * 12, word_width=50)
    assert find_gutters(words, PAGE_WIDTH) == []


def test_two_column_page_has_one_gutter():
    gutters = find_gutters(two_column_page(), PAGE_WIDTH)
    assert len(gutters) == 1
    start, end = gutters[0]
    assert 240 <= start and end < 330


def test_columns_read_left_then_right():
    words = two_column_page(rows=3)
    text = order_words(words, find_gutters(two_column_page(), PAGE_WIDTH))
    assert text.splitlines() == [
        "left0 a b c d e", "left1 a b c d e", "left2 a b c d e",
        "right0 f g h i j", "right1 f g h i j", "right2 f g h i j",
    ]


def test_full_width_header_stays_on_top():
    words = two_column_page(header="Chapter Title Spans The Page")
    gutters = find_gutters(words, PAGE_WIDTH)
    assert len(gutters) == 1  # one crossing line is allowed
    lines = order_words(words, gutters).splitlines()
    assert lines[0] == "Chapter Title Spans The Page"
    assert lines[1].startswith("left0") and lines[-1].startswith("right11")


def test_table_with_short_cells_is_not_split_into_columns():
    # Like "0.3 meters | 1.0 feet": short cells, should be read row by row.
    words = []
    for i in range(20):
        words += words_line(f"{i}.5 meters", 40, 50 + i * 12)
        words += words_line(f"{i}.9 feet", 400, 50 + i * 12)
    assert find_gutters(words, PAGE_WIDTH) == []


def test_small_page_is_one_column():
    assert find_gutters(two_column_page(rows=2), PAGE_WIDTH) == []


def test_group_lines_sorts_words_left_to_right():
    words = [
        {"text": "world", "x0": 100, "x1": 140, "top": 51},
        {"text": "hello", "x0": 40, "x1": 80, "top": 50},
        {"text": "next", "x0": 40, "x1": 80, "top": 70},
    ]
    assert [[w["text"] for w in line] for line in group_lines(words)] == [["hello", "world"], ["next"]]


# --- 2-page spreads (bug #24): read half by half, left page first ----------------------
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402

from learnbot import config  # noqa: E402
from learnbot.pdf_text import (  # noqa: E402
    crossing_allowed, page_is_mixed, page_is_spread, read_layout, read_page_text, spread_cut, spread_halves,
)

SPREAD_W, SPREAD_H = 1200, 800


class FakePage:
    """Just enough of a pdfplumber page for the reader."""

    def __init__(self, words, width=SPREAD_W, height=SPREAD_H):
        self.words, self.width, self.height = words, width, height

    def extract_words(self):
        return [dict(w) for w in self.words]

    def extract_text(self):
        return "\n".join(" ".join(w["text"] for w in line) for line in group_lines(self.words))


def spread_page(rows=12, right_offset=0):
    """Left printed page: columns A (x 40..240) and B (330..530). Right printed page: columns C
    (640..840) and D (930..1130). right_offset moves the right page's lines down a little."""
    words = []
    for i in range(rows):
        top = 50 + i * LINE_HEIGHT
        words += words_line(f"A{i} a a a a a", 40, top)
        words += words_line(f"B{i} b b b b b", 330, top)
        words += words_line(f"C{i} c c c c c", 640, top + right_offset)
        words += words_line(f"D{i} d d d d d", 930, top + right_offset)
    return words


def order_of(text, labels):
    tokens = text.split()
    return [tokens.index(label) for label in labels]


def test_spread_is_read_left_page_then_right_page_each_column_in_order():
    text, columns, spread = read_layout(FakePage(spread_page()))
    assert spread and columns == 4
    positions = order_of(text, ["A0", "A11", "B0", "B11", "C0", "C11", "D0", "D11"])
    assert positions == sorted(positions)


def test_spread_keeps_every_word_once():
    page = FakePage(spread_page())
    assert sorted(read_page_text(page).split()) == sorted(w["text"] for w in page.words)


def test_spread_is_cut_in_the_empty_middle_strip():
    cut = spread_cut(spread_page(), SPREAD_W, SPREAD_H)
    assert 530 < cut < 640
    left, right = spread_halves(spread_page(), cut)
    assert {w["text"][0] for w in left if w["text"][0] in "ABCD"} == {"A", "B"}
    assert min(w["x0"] for w in right) >= 0  # the right page starts at x = 0


def test_line_poking_into_a_column_gap_keeps_the_column_order():
    words = spread_page()
    words.append({"text": "poke", "x0": 244, "x1": 270, "top": 50 + 5 * LINE_HEIGHT})  # after A5, into the gap
    text = read_page_text(FakePage(words))
    assert order_of(text, ["A0", "A5", "poke", "A6", "A11", "B0"]) == sorted(order_of(text, ["A0", "A5", "poke", "A6", "A11", "B0"]))


def test_real_title_across_a_column_gap_stays_in_place():
    words = spread_page()
    words.append({"text": "CHAIR'S-REVIEW", "x0": 200, "x1": 370, "top": 30})  # covers the gap middle (about 285)
    text = read_page_text(FakePage(words))
    assert order_of(text, ["CHAIR'S-REVIEW", "A0", "B0"]) == sorted(order_of(text, ["CHAIR'S-REVIEW", "A0", "B0"]))
    assert text.split().index("C0") > text.split().index("B11")


def test_half_keeps_the_whole_page_crossing_allowance():
    # Right page lines sit 6 pt lower, so the whole page has twice the lines of one half.
    words = spread_page(rows=40, right_offset=6)
    for i in range(3):  # three words lying across the left page's column gap (title-like)
        words.append({"text": f"wide{i}", "x0": 236, "x1": 336, "top": 50 + (10 + i) * LINE_HEIGHT})
    cut = spread_cut(words, SPREAD_W, SPREAD_H)
    left, _ = spread_halves(words, cut)
    assert find_gutters(left, cut) == []  # its own (smaller) allowance would lose the gap
    assert find_gutters(left, cut, crossing_allowed(words)) != []
    text = read_page_text(FakePage(words))
    assert text.split().index("A39") < text.split().index("B39")


def test_wide_page_without_an_empty_middle_is_not_split():
    words = []
    for i in range(12):  # full-width prose, gaps in different places on each line
        words += words_line("one two three four five six seven eight nine ten eleven twelve", 40 + (i % 5) * 9,
                            50 + i * 12, word_width=80, gap=6)
    page = FakePage(words)
    assert spread_cut(words, SPREAD_W, SPREAD_H) is None
    assert not page_is_spread(page) and read_layout(page)[2] is False


def test_wide_page_with_a_gap_away_from_the_middle_is_not_split():
    words = []
    for i in range(12):
        words += words_line(f"L{i} a a a a", 40, 50 + i * 12, word_width=40)  # x 40..260
        words += words_line(f"R{i} b b b b b b b b b b b b b", 400, 50 + i * 12, word_width=40)  # x 400..1100
    assert spread_cut(words, SPREAD_W, SPREAD_H) is None  # the gap (260..400) is at 22-33%


def test_wide_page_with_almost_nothing_on_one_side_is_not_split():
    words = [w for w in spread_page() if w["text"][0] not in "CD" and w["text"] not in "cd"]
    words += words_line("page 12", 900, 760)
    assert spread_cut(words, SPREAD_W, SPREAD_H) is None


def test_portrait_two_column_page_is_not_a_spread():
    page = FakePage(two_column_page(), width=PAGE_WIDTH, height=800)
    assert not page_is_spread(page)
    text, columns, spread = read_layout(page)
    assert (columns, spread) == (2, False)
    assert text == order_words(two_column_page(), find_gutters(two_column_page(), PAGE_WIDTH))  # as before


def test_spread_with_clean_columns_is_not_mixed():
    assert not page_is_mixed(FakePage(spread_page()))


def test_pieces_are_rebuilt_for_the_new_reading():
    assert config.PIECES_VERSION == 3


# --- Real files (skipped when the public test PDFs are not present) ---------------------
RAW = Path("data/raw")
TEST_PDFS = ["nav_rules.pdf", "boaters_guide.pdf", "coast_pilot4_ch1.pdf", "osha3124.pdf"]


@pytest.mark.parametrize("name", TEST_PDFS)
def test_test_pdfs_have_no_spread_page_so_their_reading_is_unchanged(name):
    path = RAW / name
    if not path.is_file():
        pytest.skip(f"{name} not downloaded")
    import pdfplumber
    with pdfplumber.open(path) as pdf:
        spreads = [n for n, page in enumerate(pdf.pages, start=1) if page_is_spread(page)]
    assert spreads == []  # nav_rules p.1 and 196-199 are wide, but single pages


def test_bug_24_synergy_page_9_sentence_is_in_one_piece():
    """The CEO sentence on a 2-page spread (bug #24) is read in one run of text."""
    path = Path("data/uploads/Synergy Annual Report 2026.pdf")
    if not path.is_file():
        pytest.skip("Synergy Annual Report 2026.pdf not uploaded")
    import pdfplumber
    with pdfplumber.open(path) as pdf:
        page = pdf.pages[8]
        assert page_is_spread(page)
        text = " ".join(read_page_text(page).split())
    assert ("outages at our Collie assets are an important milestone. These complex outages require the "
            "coordinated efforts of more than 770 employees and contractors over almost 290,000 hours and "
            "support the reliability of the system during the transition.") in text
