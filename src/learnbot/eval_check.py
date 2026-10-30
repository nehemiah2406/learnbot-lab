"""Checks for the eval set (eval/explain_questions.csv, eval/trap_questions.csv).

Works for any document: each row names its PDF in the `doc` column, and quotes
are checked against the same column-aware reading the app uses (read_page_text).
No LLM calls.
"""

import csv
import re
from pathlib import Path

import pdfplumber

from learnbot.pdf_text import read_page_text

DATA_DIR = Path("data/raw")
EXPLAIN_COLUMNS = [
    "doc", "id", "question", "type", "expected_answer",
    "rule", "rule_set", "page", "source_quote",
]
TRAP_COLUMNS = ["doc", "id", "question", "type", "expected_answer", "keywords"]
EXPLAIN_TYPES = {"fact", "number", "compare", "paraphrase", "annex"}
TRAP_TYPES = {"maritime_outside", "off_topic"}
RULE_SETS = {"International", "Inland", "Both", "N/A"}
NOT_FOUND = "Not in this document"
PAIR_SEPARATOR = "|"  # compare rows: "107|108" and "International quote | Inland quote"

# Numbers written as words must also match exactly ("four to six seconds").
NUMBER_WORDS = {
    "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
    "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen",
    "eighteen", "nineteen", "twenty", "thirty", "forty", "fifty", "sixty",
    "seventy", "eighty", "ninety", "hundred", "thousand", "half",
}
DIGITS = re.compile(r"\d+(?:[.,]\d+)*")
WORDS = re.compile(r"[a-z]+")
# Typographic characters that PDFs and editors write in different ways.
SAME_CHARS = str.maketrans({
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", "−": "-", " ": " ",
})


# --- Loading ----------------------------------------------------------------------
def load_rows(path):
    """Rows of a CSV file as dicts (UTF-8, with or without BOM)."""
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


# --- Text helpers -------------------------------------------------------------------
def normalize(text):
    """Same characters, single spaces; a hyphen at a line end joins the next line."""
    text = text.translate(SAME_CHARS)
    text = re.sub(r"-\s*\n\s*", "-", text)
    return re.sub(r"\s+", " ", text).strip()


def quote_on_page(quote, page_text):
    return normalize(quote) in normalize(page_text)


def split_pair(value):
    return [part.strip() for part in value.split(PAIR_SEPARATOR)]


def numbers_in(text):
    """Number tokens: digits ("2,000" -> "2000") and number words ("four")."""
    text = text.lower()
    digits = {n.replace(",", "") for n in DIGITS.findall(text)}
    words = set(WORDS.findall(text)) & NUMBER_WORDS
    return digits | words


def missing_numbers(answer, quote):
    """Numbers in the answer that are not in the quote (must be [])."""
    return sorted(numbers_in(answer) - numbers_in(quote))


# --- Row checks (no PDF needed) -----------------------------------------------------
def empty_columns(row, columns):
    return [c for c in columns if not (row.get(c) or "").strip()]


def duplicate_ids(rows):
    seen, dups = set(), []
    for row in rows:
        if row["id"] in seen:
            dups.append(row["id"])
        seen.add(row["id"])
    return dups


def is_plain_filename(doc):
    return doc == Path(doc).name and doc.lower().endswith(".pdf")


def row_pages(row):
    """List of int pages, or None if the page column is not valid."""
    try:
        return [int(p) for p in split_pair(row["page"])]
    except ValueError:
        return None


def check_explain_row(row):
    """Problems in one explain row that can be found without the PDF."""
    problems = [f"empty column: {c}" for c in empty_columns(row, EXPLAIN_COLUMNS)]
    if problems:
        return problems
    if not is_plain_filename(row["doc"]):
        problems.append(f"doc must be a PDF file name in data/raw: {row['doc']}")
    if row["type"] not in EXPLAIN_TYPES:
        problems.append(f"unknown type: {row['type']}")
    if row["rule_set"] not in RULE_SETS:
        problems.append(f"unknown rule_set: {row['rule_set']}")

    pages = row_pages(row)
    quotes = split_pair(row["source_quote"])
    want = 2 if row["type"] == "compare" else 1
    if pages is None or any(p < 1 for p in pages):
        problems.append(f"page must be a number (compare: 'N|M'): {row['page']}")
    elif len(pages) != want or len(quotes) != want:
        problems.append(f"{row['type']} row needs {want} page(s) and {want} quote(s)")
    if row["type"] == "compare" and row["rule_set"] != "Both":
        problems.append("compare row must have rule_set Both")

    missing = missing_numbers(row["expected_answer"], " ".join(quotes))
    if missing:
        problems.append(f"numbers in answer not in source_quote: {', '.join(missing)}")
    return problems


def check_trap_row(row):
    problems = [f"empty column: {c}" for c in empty_columns(row, TRAP_COLUMNS)]
    if problems:
        return problems
    if not is_plain_filename(row["doc"]):
        problems.append(f"doc must be a PDF file name in data/raw: {row['doc']}")
    if row["type"] not in TRAP_TYPES:
        problems.append(f"unknown type: {row['type']}")
    if row["expected_answer"] != NOT_FOUND:
        problems.append(f"expected_answer must be '{NOT_FOUND}'")
    return problems


def trap_keywords(row):
    return [k.strip() for k in row["keywords"].split(";") if k.strip()]


def found_keywords(keywords, document_text):
    """Keywords that DO appear in the document (must be [] for a trap)."""
    text = normalize(document_text).lower()
    return [k for k in keywords if normalize(k).lower() in text]


# --- PDF access ---------------------------------------------------------------------
class DocumentPages:
    """Reads pages of the test PDFs once (column-aware) and keeps them in memory."""

    def __init__(self, data_dir=DATA_DIR):
        self.data_dir = Path(data_dir)
        self._pages = {}  # doc -> {page number: text}
        self._counts = {}

    def path(self, doc):
        return self.data_dir / doc

    def exists(self, doc):
        return self.path(doc).is_file()

    def page_count(self, doc):
        if doc not in self._counts:
            with pdfplumber.open(self.path(doc)) as pdf:
                self._counts[doc] = len(pdf.pages)
        return self._counts[doc]

    def pages(self, doc, numbers):
        """{n: text} for the given 1-based page numbers (missing pages -> None)."""
        cache = self._pages.setdefault(doc, {})
        todo = [n for n in numbers if n not in cache]
        if todo:
            with pdfplumber.open(self.path(doc)) as pdf:
                for n in todo:
                    cache[n] = read_page_text(pdf.pages[n - 1]) if 1 <= n <= len(pdf.pages) else None
        return {n: cache[n] for n in numbers}

    def full_text(self, doc):
        numbers = range(1, self.page_count(doc) + 1)
        return "\n".join(t or "" for t in self.pages(doc, numbers).values())


def verify_quotes(row, docs):
    """Problems with the row's quotes on its stated pages ([] = all verified)."""
    pages = row_pages(row) or []
    quotes = split_pair(row["source_quote"])
    texts = docs.pages(row["doc"], pages)
    problems = []
    for page, quote in zip(pages, quotes):
        if texts[page] is None:
            problems.append(f"page {page} does not exist in {row['doc']}")
        elif not quote_on_page(quote, texts[page]):
            problems.append(f"quote not found on page {page}: {quote[:60]}...")
    return problems


def verify_trap(row, docs):
    found = found_keywords(trap_keywords(row), docs.full_text(row["doc"]))
    return [f"keyword found in {row['doc']}: {k}" for k in found]
