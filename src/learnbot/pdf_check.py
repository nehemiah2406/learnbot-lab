"""Self-check for any uploaded PDF: can we read it, is the text usable, how is it structured.

Main entry point: check_pdf(path) -> PdfCheckResult (with verdict OK / WARNING / FAIL).
build_report(result) turns a result into Markdown. No LLM calls.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber
from pdfminer.pdfdocument import PDFPasswordIncorrect
from pdfplumber.utils.exceptions import PdfminerException

from learnbot import config
from learnbot.pdf_text import read_page

OK, WARNING, FAIL = "OK", "WARNING", "FAIL"

# --- Heading patterns ---------------------------------------------------------
HEADING_KINDS = ["Rule", "Section", "Chapter", "Article", "Part", "Annex", "Appendix"]
# Keyword is case-insensitive ("RULE 5"); Roman numerals must be upper case,
# so ordinary words like "in" or "mix" are never read as numbers. Only I/V/X
# (1-39), so letter labels like "Part C" are not misread as 100.
LABEL_PATTERN = re.compile(
    r"^\s*(?P<kind>(?i:" + "|".join(HEADING_KINDS) + r"))"
    r"\s+(?P<num>\d{1,3}|[IVX]+)\b(?P<tail>.*)$"
)
# "1.2 Title" or "1.2. Title": at least one dot, title starts with a capital.
DOTTED_PATTERN = re.compile(r"^\s*(?P<num>\d{1,3}(?:\.\d{1,3})+)\.?\s+[A-Z]")
# A real heading has nothing after the label, a dash/colon, or a Capitalised title.
# "Rule 13." or "Annex III to these Regulations" are wrapped sentences, not headings.
HEADING_TAIL = re.compile(r"^(\s*|\s*[-–—:].*|\s+[A-Z].*)$")
# Table-of-contents lines have dot leaders: "Rule 5-Look-out ........ 12".
TOC_LINE = re.compile(r"\.{4,}")
TOC_PAGE_MIN_LINES = 5
# Gaps are only checked when a kind has at least this many headings.
MIN_HEADINGS_FOR_GAPS = 3
# Long lists of missing numbers are shortened to this many plus "+N more".
MAX_MISSING_SHOWN = 10
DOTTED_KIND = "Numbered"

MESSY_TEXT = re.compile(r"�|\(cid:\d+\)")


@dataclass
class PdfCheckResult:
    path: str
    size_mb: float = 0.0
    page_count: int = 0
    char_counts: list = field(default_factory=list)
    low_text_pages: list = field(default_factory=list)
    table_pages: list = field(default_factory=list)
    samples: list = field(default_factory=list)  # [(page, text)]
    messy_count: int = 0
    headings: dict = field(default_factory=dict)  # kind -> {number: [pages]}
    gaps: dict = field(default_factory=dict)  # kind -> [missing numbers]
    errors: list = field(default_factory=list)  # problems that stop the check
    verdict: str = OK
    reasons: list = field(default_factory=list)
    multi_column_pages: list = field(default_factory=list)
    ocr_pages: list = field(default_factory=list)  # scanned pages: read by OCR (learnbot.ocr)
    notes: list = field(default_factory=list)  # info only, never changes the verdict


# --- Roman numerals -------------------------------------------------------------
ROMAN_VALUES = [
    (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
    (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
]


def int_to_roman(n):
    out = ""
    for value, letters in ROMAN_VALUES:
        while n >= value:
            out += letters
            n -= value
    return out


def roman_to_int(text):
    """Value of a valid Roman numeral, or None (e.g. "IIII", "VX")."""
    total, i = 0, 0
    for value, letters in ROMAN_VALUES:
        while text.startswith(letters, i):
            total += value
            i += len(letters)
    if i != len(text) or total == 0 or int_to_roman(total) != text:
        return None
    return total


def number_value(num):
    """Integer value of "12" or "XII", or None if not a valid number."""
    return int(num) if num.isdigit() else roman_to_int(num)


# --- Small helpers --------------------------------------------------------------
def page_ranges(pages):
    """[5, 6, 7, 8, 12] -> "5-8, 12"."""
    parts, start, prev = [], None, None
    for p in sorted(pages):
        if start is None:
            start = prev = p
        elif p == prev + 1:
            prev = p
        else:
            parts.append(f"{start}-{prev}" if start != prev else str(start))
            start = prev = p
    if start is not None:
        parts.append(f"{start}-{prev}" if start != prev else str(start))
    return ", ".join(parts)


def char_stats(char_counts):
    """min / max / average characters per page."""
    if not char_counts:
        return {"min": 0, "max": 0, "avg": 0.0}
    return {
        "min": min(char_counts),
        "max": max(char_counts),
        "avg": round(sum(char_counts) / len(char_counts), 1),
    }


def find_low_text_pages(texts, limit=config.LOW_TEXT_CHARS):
    """1-based page numbers with fewer than `limit` characters (blank or scanned?)."""
    return [i for i, t in enumerate(texts, start=1) if len(t.strip()) < limit]


def pick_samples(texts, low_text_pages, n=config.SAMPLE_CHARS):
    """[(page, first n chars)] for the first and the middle page with real text.

    The first page is often a cover, so the middle page shows normal body text.
    """
    low = set(low_text_pages)
    text_pages = [p for p in range(1, len(texts) + 1) if p not in low]
    if not text_pages:
        return []
    pages = sorted({text_pages[0], text_pages[len(text_pages) // 2]})
    return [(p, texts[p - 1][:n]) for p in pages]


def count_messy_text(texts):
    return sum(len(MESSY_TEXT.findall(t)) for t in texts)


# --- Limits ---------------------------------------------------------------------
def check_size_limit(size_bytes, max_mb=config.MAX_FILE_MB):
    """Friendly message if the file is too big, else None."""
    size_mb = size_bytes / (1024 * 1024)
    if size_mb > max_mb:
        return f"File is {size_mb:.1f} MB. The limit is {max_mb} MB. Please upload a smaller file."
    return None


def check_page_limit(page_count, max_pages=config.MAX_PAGES):
    """Friendly message if the PDF has too many (or no) pages, else None."""
    if page_count == 0:
        return "The PDF has no pages."
    if page_count > max_pages:
        return (
            f"The PDF has {page_count} pages. The limit is {max_pages} pages. "
            "Please split it into smaller files."
        )
    return None


# --- Headings -------------------------------------------------------------------
def is_toc_page(text):
    return sum(1 for line in text.splitlines() if TOC_LINE.search(line)) >= TOC_PAGE_MIN_LINES


def parse_heading(line):
    """(kind, number) if the line starts with a heading label, else None."""
    if TOC_LINE.search(line):
        return None
    match = LABEL_PATTERN.match(line)
    if match:
        if number_value(match.group("num")) is None:
            return None
        if not HEADING_TAIL.match(match.group("tail")):
            return None
        return match.group("kind").capitalize(), match.group("num")
    match = DOTTED_PATTERN.match(line)
    if match:
        return DOTTED_KIND, match.group("num")
    return None


def find_headings(texts):
    """{kind: {number: [pages]}} for every heading label at the start of a line.

    Contents pages are skipped. Numbers keep their original style ("5", "IV", "1.2").
    """
    found = {}
    for page_no, text in enumerate(texts, start=1):
        if is_toc_page(text):
            continue
        for line in text.splitlines():
            heading = parse_heading(line)
            if heading is None:
                continue
            kind, num = heading
            pages = found.setdefault(kind, {}).setdefault(num, [])
            if page_no not in pages:
                pages.append(page_no)
    return {kind: dict(sorted(nums.items(), key=lambda kv: sort_key(kv[0])))
            for kind, nums in found.items()}


def sort_key(num):
    if "." in num:
        return tuple(int(part) for part in num.split("."))
    return (number_value(num) or 0,)


def missing_in_sequence(numbers, min_count=MIN_HEADINGS_FOR_GAPS):
    """Missing values between the smallest and largest, in the same style as found.

    Returns [] when there are too few numbers, or when more are missing than found:
    then the numbering is sparse on purpose (e.g. 80.105, 80.110, ...), not broken.
    """
    if len(numbers) < min_count:
        return []
    values = {number_value(n) for n in numbers}
    roman = all(not n.isdigit() for n in numbers)
    missing = [v for v in range(min(values), max(values) + 1) if v not in values]
    if len(missing) > len(values):
        return []
    return [int_to_roman(v) if roman else str(v) for v in missing]


def find_gaps(headings, min_count=MIN_HEADINGS_FOR_GAPS):
    """{kind: [missing numbers]} for kinds with gaps in their numbering.

    Dotted numbers are checked inside each parent: 1.1, 1.2, 1.4 -> 1.3 missing.
    """
    gaps = {}
    for kind, nums in headings.items():
        if kind == DOTTED_KIND:
            missing = dotted_gaps(list(nums), min_count)
        else:
            missing = missing_in_sequence(list(nums), min_count)
        if missing:
            gaps[kind] = missing
    return gaps


def dotted_gaps(numbers, min_count):
    groups = {}
    for num in numbers:
        parent, last = num.rsplit(".", 1)
        groups.setdefault(parent, []).append(last)
    missing = []
    for parent, children in groups.items():
        missing += [f"{parent}.{m}" for m in missing_in_sequence(children, min_count)]
    return missing


def short_list(items, limit=MAX_MISSING_SHOWN):
    """"1, 2, 3 ... (+5 more)" for long lists."""
    shown = ", ".join(items[:limit])
    return shown + (f" ... (+{len(items) - limit} more)" if len(items) > limit else "")


# --- Verdict --------------------------------------------------------------------
def decide_verdict(result):
    """(verdict, reasons) from the analysed result. Reasons are simple English."""
    if result.errors:
        return FAIL, list(result.errors)

    fail, warn = [], []
    # Scanned pages are read by OCR, so they no longer count as pages without text.
    low = [p for p in result.low_text_pages if p not in result.ocr_pages]
    ratio = len(low) / result.page_count if result.page_count else 0
    if low and ratio >= config.LOW_TEXT_FAIL_RATIO:
        fail.append(
            f"{len(low)} of {result.page_count} pages have almost no text "
            "and no scanned image to read. Please upload a PDF with text."
        )
    elif low and ratio >= config.LOW_TEXT_WARN_RATIO:
        warn.append(f"Pages {page_ranges(low)} have almost no text, maybe blank or scanned.")
    if result.messy_count >= config.MESSY_TEXT_WARN_COUNT:
        warn.append(f"Text has {result.messy_count} broken characters; answers may be less accurate.")
    for kind, missing in result.gaps.items():
        # Dotted numbers (legal codes like 161.1-161.6, 161.10) often skip on purpose,
        # so their gaps are shown in the report but do not change the verdict.
        if kind != DOTTED_KIND:
            warn.append(f"{kind} numbering has gaps, missing: {short_list(missing)}.")

    if fail:
        return FAIL, fail + warn
    if warn:
        return WARNING, warn
    return OK, ["File looks good."]


def make_notes(result):
    """Info notes for the user. They never change the verdict."""
    if result.errors:
        return []
    notes = []
    if not result.headings:
        notes.append("No numbered headings (Rule, Section, Chapter, 1.2 ...); normal for many books.")
    if result.ocr_pages:
        notes.append(f"Scanned pages read by OCR (check numbers on the page): {page_ranges(result.ocr_pages)}.")
    if result.multi_column_pages:
        notes.append(
            f"Multi-column pages read column by column: {page_ranges(result.multi_column_pages)}."
        )
    return notes


# --- Main check -----------------------------------------------------------------
def analyse_pages(result, texts, table_counts):
    """Fill text, table and heading fields of `result` from per-page data."""
    result.page_count = len(texts)
    result.char_counts = [len(t) for t in texts]
    result.low_text_pages = find_low_text_pages(texts)
    result.table_pages = [i for i, c in enumerate(table_counts, start=1) if c > 0]
    result.samples = pick_samples(texts, result.low_text_pages)
    result.messy_count = count_messy_text(texts)
    result.headings = find_headings(texts)
    result.gaps = find_gaps(result.headings)
    return result


def open_error_message(error):
    """Friendly message for a PDF that pdfplumber cannot open."""
    inner = error.args[0] if error.args else None
    if isinstance(inner, PDFPasswordIncorrect):
        return "The PDF is password protected. Please upload a version without a password."
    return "The file could not be opened. It may be damaged or not a real PDF."


def check_pdf(path):
    """Run every check on one PDF and return a PdfCheckResult with a verdict."""
    path = Path(path)
    result = PdfCheckResult(path=path.as_posix())
    if not path.is_file():
        result.errors.append("File not found.")
    else:
        result.size_mb = round(path.stat().st_size / (1024 * 1024), 2)
        size_error = check_size_limit(path.stat().st_size)
        if size_error:
            result.errors.append(size_error)
        else:
            read_pdf(path, result)
    result.verdict, result.reasons = decide_verdict(result)
    result.notes = make_notes(result)
    return result


def read_pdf(path, result):
    try:
        with pdfplumber.open(path) as pdf:
            page_error = check_page_limit(len(pdf.pages))
            if page_error:
                result.page_count = len(pdf.pages)
                result.errors.append(page_error)
                return
            texts, table_counts = [], []
            for page_no, page in enumerate(pdf.pages, start=1):
                text, columns = read_page(page)
                texts.append(text)
                if len(text.strip()) < config.LOW_TEXT_CHARS and page.images:
                    result.ocr_pages.append(page_no)
                if columns > 1:
                    result.multi_column_pages.append(page_no)
                table_counts.append(len(page.find_tables()))
                page.close()  # free memory on big files
    except PdfminerException as error:
        result.errors.append(open_error_message(error))
        return
    except Exception:
        result.errors.append("The file could not be read. It may be damaged.")
        return
    analyse_pages(result, texts, table_counts)


# --- Report ---------------------------------------------------------------------
def build_report(result):
    """Markdown report for one checked PDF."""
    lines = [
        f"# PDF check: {Path(result.path).name}",
        "",
        f"**Verdict: {result.verdict}**",
        "",
        *[f"- {reason}" for reason in result.reasons],
        *[f"- Note: {note}" for note in result.notes],
        "",
        "## File",
        "",
        f"- Path: `{result.path}`",
        f"- Size: {result.size_mb} MB",
        f"- Pages: {result.page_count}",
    ]
    if result.errors or not result.char_counts:
        return "\n".join(lines) + "\n"

    stats = char_stats(result.char_counts)
    low = result.low_text_pages
    lines += [
        "",
        "## Text",
        "",
        f"- Characters per page: min {stats['min']}, max {stats['max']}, average {stats['avg']}",
        f"- Pages under {config.LOW_TEXT_CHARS} characters ({len(low)}): {page_ranges(low) or 'none'}",
        f"- Pages with tables ({len(result.table_pages)}): {page_ranges(result.table_pages) or 'none'}",
        f"- Broken-text marks: {result.messy_count}",
        "",
        "## Headings",
        "",
    ]
    lines += heading_report_lines(result)
    lines += ["", f"## Sample text (first {config.SAMPLE_CHARS} characters)"]
    for page_no, text in result.samples:
        lines += ["", f"Page {page_no}:", "", "```text", text, "```"]
    return "\n".join(lines) + "\n"


def heading_report_lines(result):
    if not result.headings:
        return ["No numbered headings found."]
    lines = ["| Kind | Count | First | Last | Missing |", "|---|---|---|---|---|"]
    for kind, nums in result.headings.items():
        labels = list(nums)
        missing = short_list(result.gaps.get(kind, [])) or "none"
        lines.append(f"| {kind} | {len(labels)} | {labels[0]} | {labels[-1]} | {missing} |")
    for kind, nums in result.headings.items():
        lines += ["", f"### {kind}", ""]
        lines += [f"- {kind} {num}: pages {page_ranges(pages)}" for num, pages in nums.items()]
    return lines
