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
