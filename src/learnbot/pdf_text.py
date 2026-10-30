"""Read page text in reading order, for any PDF.

Multi-column pages are detected from word positions: a "gutter" is a vertical
strip in the middle of the page that (almost) no word crosses. Each column is
then read top to bottom, left column first, so sentences are not mixed.
Lines that cross the gutter (titles, headers) are kept full width in place.

Everything that reads page text (self-check, eval checker, later the app) must
use read_page_text(), so quotes always match the same reading.
"""

# Gutters are searched only in this middle part of the page width.
GUTTER_SEARCH = (0.20, 0.80)
# A gutter must be at least this wide (points). Word gaps are ~3 pt.
MIN_GUTTER_WIDTH = 6
# Words allowed to cross a gutter: full-width titles/headers (share of lines, at least 2).
MAX_CROSSING_SHARE = 0.05
MIN_CROSSING = 2
# Each column must hold at least this share of the page's words.
MIN_COLUMN_SHARE = 0.10
# Pages with fewer words are always read as one column.
MIN_WORDS_FOR_COLUMNS = 40
# Text columns have full lines; table columns have short cells ("0.3", "meters").
# Every column needs at least this median number of words per line, else the page
# is read row by row, which keeps table rows together.
MIN_WORDS_PER_COLUMN_LINE = 4
# Words whose tops differ by less than this are on the same line (points).
LINE_TOLERANCE = 3


def group_lines(words, tolerance=LINE_TOLERANCE):
    """Group words into lines (top to bottom), each line sorted left to right."""
    lines = []
    for word in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if lines and abs(word["top"] - lines[-1][0]["top"]) < tolerance:
            lines[-1].append(word)
        else:
            lines.append([word])
    return [sorted(line, key=lambda w: w["x0"]) for line in lines]


def line_text(line):
    return " ".join(w["text"] for w in line)


def find_gutters(words, page_width):
    """x-ranges [(start, end)] of column gutters, left to right; [] = one column."""
    if len(words) < MIN_WORDS_FOR_COLUMNS:
        return []
    width = int(page_width) + 1
    coverage = [0] * width
    for w in words:
        for x in range(max(0, int(w["x0"])), min(width, int(w["x1"]) + 1)):
            coverage[x] += 1
    max_crossing = max(MIN_CROSSING, int(MAX_CROSSING_SHARE * len(group_lines(words))))

    gutters, start = [], None
    lo, hi = int(width * GUTTER_SEARCH[0]), int(width * GUTTER_SEARCH[1])
    for x in range(lo, hi + 1):
        free = x < hi and coverage[x] <= max_crossing
        if free and start is None:
            start = x
        elif not free and start is not None:
            if x - start >= MIN_GUTTER_WIDTH:
                gutters.append((start, x - 1))
            start = None
    gutters = [g for g in gutters if columns_are_real(words, gutters, g)]
    return gutters if columns_are_text(words, gutters) else []


def median(values):
    values = sorted(values)
    return values[len(values) // 2] if values else 0


def columns_are_text(words, gutters):
    """Every column must read like prose (long lines), not like table cells."""
    if not gutters:
        return False
    inside = [w for w in words if not crosses(w, gutters)]
    for col in range(len(gutters) + 1):
        lines = group_lines([w for w in inside if column_index(w, gutters) == col])
        if median(len(line) for line in lines) < MIN_WORDS_PER_COLUMN_LINE:
            return False
    return True


def columns_are_real(words, gutters, gutter):
    """Both sides of a gutter must hold enough words (not a stray gap in a table)."""
    mid = (gutter[0] + gutter[1]) / 2
    left = sum(1 for w in words if w["x1"] <= mid)
    right = sum(1 for w in words if w["x0"] >= mid)
    need = MIN_COLUMN_SHARE * len(words)
    return left >= need and right >= need


def crosses(word, gutters):
    return any(word["x0"] < end and word["x1"] > start for start, end in gutters)


def column_index(word, gutters):
    """0 for the left-most column, 1 for the next, ..."""
    centre = (word["x0"] + word["x1"]) / 2
    return sum(1 for start, end in gutters if centre > (start + end) / 2)


def order_words(words, gutters):
    """Text of the words in reading order: columns one after another, between full-width lines."""
    if not gutters:
        return "\n".join(line_text(line) for line in group_lines(words))

    out, block = [], []

    def flush():
        for col in range(len(gutters) + 1):
            col_words = [w for w in block if column_index(w, gutters) == col]
            out.extend(line_text(line) for line in group_lines(col_words))
        block.clear()

    for line in group_lines(words):
        if any(crosses(w, gutters) for w in line):
            flush()
            out.append(line_text(line))
        else:
            block.extend(line)
    flush()
    return "\n".join(out)


def read_page(page):
    """(text in reading order, number of columns) for a pdfplumber page."""
    words = page.extract_words()
    gutters = find_gutters(words, page.width)
    if not gutters:
        return page.extract_text() or "", 1
    return order_words(words, gutters), len(gutters) + 1


def read_page_text(page):
    """Page text in reading order (column-aware). `page` is a pdfplumber page."""
    return read_page(page)[0]
