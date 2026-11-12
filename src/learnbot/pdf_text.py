"""Read page text in reading order, for any PDF.

Multi-column pages are detected from word positions: a "gutter" is a vertical
strip in the middle of the page that (almost) no word crosses. Each column is
then read top to bottom, left column first, so sentences are not mixed.
Lines that cross the gutter (titles, headers) are kept full width in place.

A 2-page spread (two printed pages side by side on one wide PDF page, bug #24) is
cut at its empty middle strip and read half by half: the left page, then the right
page, each with the column reader. Inside a half, a line is a full-width title only
if a word covers the middle of a column gap (a body line whose last word pokes into
a narrow gap stays in its column). Pages that are not spreads are read as before.

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
# A page read row by row is "mixed" if this many lines (and this share of its lines) have a
# wide gap near the middle with at least MIN_WORDS_PER_SIDE words on both sides.
MIN_WORDS_PER_SIDE = 3
MIN_MIXED_LINES = 5
MIN_MIXED_SHARE = 0.15
# A 2-page spread: the page is at least this many times as wide as it is tall, an empty
# strip (as for a gutter) lies in this middle part of the width, and each half holds at
# least this share of the words. Shape alone is not enough: a landscape page (a wide
# table, a diagram) has no empty middle strip and is read as one page.
SPREAD_MIN_RATIO = 1.25
SPREAD_MIDDLE = (0.45, 0.55)
SPREAD_MIN_HALF_SHARE = 0.20


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


def crossing_allowed(words):
    """How many words may cross a gutter: full-width titles/headers."""
    return max(MIN_CROSSING, int(MAX_CROSSING_SHARE * len(group_lines(words))))


def find_gutters(words, page_width, max_crossing=None):
    """x-ranges [(start, end)] of column gutters, left to right; [] = one column.
    max_crossing: words allowed to cross (default: from this page's lines; a spread half
    keeps the whole page's number, so it is exactly as tolerant as before the split)."""
    if len(words) < MIN_WORDS_FOR_COLUMNS:
        return []
    width = int(page_width) + 1
    coverage = [0] * width
    for w in words:
        for x in range(max(0, int(w["x0"])), min(width, int(w["x1"]) + 1)):
            coverage[x] += 1
    if max_crossing is None:
        max_crossing = crossing_allowed(words)

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


def covers_middle(word, gutters):
    """True if the word covers the middle of a gutter (a real full-width title does)."""
    return any(word["x0"] < (start + end) / 2 < word["x1"] for start, end in gutters)


def order_words(words, gutters, full_width=crosses):
    """Text of the words in reading order: columns one after another, between full-width lines.
    full_width(word, gutters): True if that word makes its line a full-width line."""
    if not gutters:
        return "\n".join(line_text(line) for line in group_lines(words))

    out, block = [], []

    def flush():
        for col in range(len(gutters) + 1):
            col_words = [w for w in block if column_index(w, gutters) == col]
            out.extend(line_text(line) for line in group_lines(col_words))
        block.clear()

    for line in group_lines(words):
        if any(full_width(w, gutters) for w in line):
            flush()
            out.append(line_text(line))
        else:
            block.extend(line)
    flush()
    return "\n".join(out)


def spread_cut(words, width, height):
    """x where a 2-page spread is cut (middle of its empty middle strip), or None."""
    if width < SPREAD_MIN_RATIO * height or len(words) < MIN_WORDS_FOR_COLUMNS:
        return None
    size = int(width) + 1
    coverage = [0] * size
    for w in words:
        for x in range(max(0, int(w["x0"])), min(size, int(w["x1"]) + 1)):
            coverage[x] += 1
    max_crossing = crossing_allowed(words)
    lo, hi = int(width * SPREAD_MIDDLE[0]), int(width * SPREAD_MIDDLE[1])
    strips, start = [], None
    for x in range(lo, hi + 1):
        free = x < hi and coverage[x] <= max_crossing
        if free and start is None:
            start = x
        elif not free and start is not None:
            if x - start >= MIN_GUTTER_WIDTH:
                strips.append((start, x - 1))
            start = None
    if not strips:
        return None
    first, last = max(strips, key=lambda s: s[1] - s[0])
    cut = (first + last) / 2
    left = sum(1 for w in words if (w["x0"] + w["x1"]) / 2 < cut)
    need = SPREAD_MIN_HALF_SHARE * len(words)
    return cut if left >= need and len(words) - left >= need else None


def spread_halves(words, cut):
    """(left words, right words), the right ones moved so the right half starts at x = 0."""
    left = [w for w in words if (w["x0"] + w["x1"]) / 2 < cut]
    right = [{**w, "x0": w["x0"] - cut, "x1": w["x1"] - cut} for w in words if (w["x0"] + w["x1"]) / 2 >= cut]
    return left, right


def read_half(words, width, max_crossing):
    """(text, columns) of one half of a spread, with the stricter full-width line rule."""
    gutters = find_gutters(words, width, max_crossing)
    return order_words(words, gutters, full_width=covers_middle), len(gutters) + 1


def read_layout(page):
    """(text in reading order, number of columns, 2-page spread?) for a pdfplumber page."""
    words = page.extract_words()
    cut = spread_cut(words, page.width, page.height)
    if cut is not None:
        left, right = spread_halves(words, cut)
        allowed = crossing_allowed(words)
        (left_text, left_cols), (right_text, right_cols) = (read_half(left, cut, allowed),
                                                            read_half(right, page.width - cut, allowed))
        return "\n".join(t for t in (left_text, right_text) if t), left_cols + right_cols, True
    gutters = find_gutters(words, page.width)
    if not gutters:
        return page.extract_text() or "", 1, False
    return order_words(words, gutters), len(gutters) + 1, False


def read_page(page):
    """(text in reading order, number of columns) for a pdfplumber page."""
    text, columns, _ = read_layout(page)
    return text, columns


def read_page_text(page):
    """Page text in reading order (column-aware). `page` is a pdfplumber page."""
    return read_page(page)[0]


def line_has_two_sides(line, page_width):
    """True if a wide gap near the middle of the line has enough words on both sides."""
    for i in range(MIN_WORDS_PER_SIDE, len(line) - MIN_WORDS_PER_SIDE + 1):
        gap_start, gap_end = line[i - 1]["x1"], line[i]["x0"]
        middle = GUTTER_SEARCH[0] * page_width <= gap_start <= GUTTER_SEARCH[1] * page_width
        if middle and gap_end - gap_start >= MIN_GUTTER_WIDTH * 2:
            return True
    return False


def page_is_spread(page):
    """True if the page is a 2-page spread, read half by half (left page, then right page)."""
    return spread_cut(page.extract_words(), page.width, page.height) is not None


def page_is_mixed(page):
    """True if the page looks like two columns but was read row by row, so its lines may be
    out of order. A page read column by column is not mixed; table rows have short cells."""
    words = page.extract_words()
    cut = spread_cut(words, page.width, page.height)
    if cut is not None:  # a spread: each half is checked as its own page
        left, right = spread_halves(words, cut)
        allowed = crossing_allowed(words)
        return words_are_mixed(left, cut, allowed) or words_are_mixed(right, page.width - cut, allowed)
    return words_are_mixed(words, page.width)


def words_are_mixed(words, width, max_crossing=None):
    if find_gutters(words, width, max_crossing):
        return False
    lines = group_lines(words)
    sides = sum(line_has_two_sides(line, width) for line in lines)
    return sides >= MIN_MIXED_LINES and sides >= MIN_MIXED_SHARE * len(lines)
