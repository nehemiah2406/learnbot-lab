"""Checks for the eval set (eval/explain_questions.csv, eval/trap_questions.csv).

Works for any document: each row names its PDF in the `doc` column, and quotes
are checked against the same column-aware reading the app uses (read_page_text).
No LLM calls.
"""

import csv
import re
from pathlib import Path

import pdfplumber

from learnbot.baseline import tokenize
from learnbot.pdf_text import read_page_text
from learnbot.units import measurements

DATA_DIR = Path("data/raw")
EXPLAIN_COLUMNS = [
    "doc", "id", "question", "type", "expected_answer",
    "rule", "rule_set", "page", "source_quote", "accepted_sources", "other_answers",
]
# other_answers (optional): another exact answer the document gives, as
# "doc.pdf:N=exact text from that page" (several: separated by ";"). The text is both the
# answer and its quote; the checker verifies it on that page. Example: a table page with
# "nautical mile - 1,852 meters / 6,076.12 feet" for "How long is a nautical mile?".
OPTIONAL_COLUMNS = {"other_answers"}
# accepted_sources: every "doc.pdf:page" where the row's quote text appears (filled by
# scripts/find_accepted_sources.py, verified by the checker). An answer from any of them
# counts as the right source.
SOURCE_SEPARATOR = ";"
# A leading paragraph marker ("(p)", "(12)", "§ 87.1") is a label, not text.
LEADING_MARKER = re.compile(r"^\s*(\([a-zA-Z0-9]{1,4}\)|§\s*[\d.]+)\s*")
# Shorter quotes ("[Reserved]") would match unrelated pages, so they are only accepted
# on their own page.
ACCEPT_MIN_WORDS = 6
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
    required = [c for c in EXPLAIN_COLUMNS if c not in OPTIONAL_COLUMNS]
    problems = [f"empty column: {c}" for c in empty_columns(row, required)]
    if problems:
        return problems
    if not is_plain_filename(row["doc"]):
        problems.append(f"doc must be a PDF file name in data/raw: {row['doc']}")
    if parse_other_answers(row.get("other_answers", "")) is None:
        problems.append(f"other_answers must be 'doc.pdf:N=exact text': {row['other_answers']}")
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
    # quiz_rules.md rule 8: the question must say which rule set it asks about.
    if row["rule_set"] in ("International", "Inland") and row["rule_set"].lower() not in row["question"].lower():
        problems.append(f"question must name its rule set ({row['rule_set']})")

    missing = missing_numbers(row["expected_answer"], " ".join(quotes))
    if missing:
        problems.append(f"numbers in answer not in source_quote: {', '.join(missing)}")

    sources = parse_sources(row["accepted_sources"])
    if sources is None:
        problems.append(f"accepted_sources must be 'doc.pdf:N;doc.pdf:M': {row['accepted_sources']}")
    elif pages is not None and not {(row["doc"], p) for p in pages} <= set(sources):
        problems.append("accepted_sources must include the row's own page(s)")
    return problems


def parse_sources(value):
    """[(doc, page)] from 'a.pdf:12;b.pdf:3', or None if the text is not valid."""
    sources = []
    for part in (value or "").split(SOURCE_SEPARATOR):
        doc, _, page = part.strip().rpartition(":")
        if not is_plain_filename(doc) or not page.isdigit():
            return None
        sources.append((doc, int(page)))
    return sources


def parse_other_answers(value):
    """[(doc, page, text)] from 'a.pdf:34=text;b.pdf:2=text' ([] if empty), or None if not valid."""
    answers = []
    for part in (value or "").split(SOURCE_SEPARATOR):
        if not part.strip():
            continue
        where, sep, text = part.partition("=")
        doc, _, page = where.strip().rpartition(":")
        if not sep or not text.strip() or not is_plain_filename(doc) or not page.isdigit():
            return None
        answers.append((doc, int(page), text.strip()))
    return answers


def format_sources(sources):
    return SOURCE_SEPARATOR.join(f"{doc}:{page}" for doc, page in sorted(set(sources)))


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

    def rule_sets(self, doc_names):
        """RuleSets (page labels from headings) of the given documents, as the app makes them."""
        from learnbot.chunking import chunk_pages
        from learnbot.rule_sets import RuleSets

        chunks = [c for doc in doc_names
                  for c in chunk_pages(doc, self.pages(doc, range(1, self.page_count(doc) + 1)))]
        return RuleSets(chunks)

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


def quote_core(quote):
    return LEADING_MARKER.sub("", quote)


def find_accepted_sources(row, docs, doc_names, rule_sets=None):
    """Every (doc, page) where the row's quote text appears: the row's own page(s), plus
    any page of the given documents with the same text (leading marker removed). If the
    question names a rule set, only pages of that rule set (same rule as the app)."""
    found = {(row["doc"], p) for p in row_pages(row) or []}
    for quote in split_pair(row["source_quote"]):
        core = normalize(quote_core(quote))
        if len(core.split()) < ACCEPT_MIN_WORDS:
            continue
        for doc in doc_names:
            texts = docs.pages(doc, range(1, docs.page_count(doc) + 1))
            found |= {(doc, n) for n, text in texts.items() if text and core in normalize(text)
                      and (rule_sets is None or rule_sets.allowed(row["question"], doc, n))}
    return sorted(found)


# Same fact in other words: a page with the expected answer's number + unit near the
# question's key words may answer the question too. Real case (hold-out HO-CP-01): "every
# 4 to 6 minutes" is on one page AND, worded differently, on another; only the first was
# listed, so a right answer from p.28 was scored wrong. These pages are only listed for a
# person to review before a run (add them to other_answers or not); never added by code.
SAME_FACT_WINDOW = 400  # characters on each side of the number
SAME_FACT_MIN_WORDS = 2  # question key words (word stems) that must be in that window
STEM_LETTERS = 5  # same stems as the proof check ("repeat" / "repeated")


def question_stems(text):
    return {t[:STEM_LETTERS] for t in tokenize(text) if t.isalpha() and len(t) >= 3}


def listed_pages(row):
    """{(doc, page)} already named by the row: own page(s), accepted_sources, other_answers."""
    own = {(row["doc"], p) for p in row_pages(row) or []}
    others = {(d, p) for d, p, _ in parse_other_answers(row.get("other_answers", "")) or []}
    return own | set(parse_sources(row.get("accepted_sources", "")) or []) | others


def same_fact_snippet(text, wanted, stems):
    """Text around the first place where every wanted (number, unit) and at least
    SAME_FACT_MIN_WORDS of the stems are within SAME_FACT_WINDOW characters, or None."""
    first = min(wanted)[0]
    for m in DIGITS.finditer(text):
        if m.group().replace(",", "") != first:
            continue
        window = text[max(0, m.start() - SAME_FACT_WINDOW):m.end() + SAME_FACT_WINDOW]
        if wanted <= measurements(window) and len(stems & question_stems(window)) >= SAME_FACT_MIN_WORDS:
            return text[max(0, m.start() - 100):m.end() + 60]
    return None


def find_same_fact_pages(row, docs, doc_names, rule_sets=None):
    """[(doc, page, snippet)]: pages the row does not list yet that have every number +
    unit of the expected answer near the question's key words (rule-set pages only, as in
    the app). Rows whose expected answer has no number + unit: []."""
    wanted = measurements(normalize(row["expected_answer"]))
    if not wanted:
        return []
    stems = question_stems(row["question"])
    known = listed_pages(row)
    found = []
    for doc in doc_names:
        for n, text in docs.pages(doc, range(1, docs.page_count(doc) + 1)).items():
            if not text or (doc, n) in known:
                continue
            if rule_sets is not None and not rule_sets.allowed(row["question"], doc, n):
                continue
            snippet = same_fact_snippet(normalize(text), wanted, stems)
            if snippet:
                found.append((doc, n, snippet))
    return found


def verify_other_answers(row, docs):
    """Problems if an other answer's text is not on its page."""
    problems = []
    for doc, page, text in parse_other_answers(row.get("other_answers", "")) or []:
        if not docs.exists(doc):
            continue
        page_text = docs.pages(doc, [page])[page]
        if page_text is None or not quote_on_page(text, page_text):
            problems.append(f"other answer not found on {doc}:{page}: {text[:60]}")
    return problems


def verify_accepted_sources(row, docs, doc_names, rule_sets=None):
    """Problems if accepted_sources is not exactly the pages that have the quote text."""
    listed = set(parse_sources(row["accepted_sources"]) or [])
    found = set(find_accepted_sources(row, docs, doc_names, rule_sets))
    problems = [f"accepted source has no matching text: {d}:{p}" for d, p in sorted(listed - found)]
    problems += [f"page has the same text but is not listed: {d}:{p}" for d, p in sorted(found - listed)]
    return problems


def verify_trap(row, docs):
    found = found_keywords(trap_keywords(row), docs.full_text(row["doc"]))
    return [f"keyword found in {row['doc']}: {k}" for k in found]


# --- Overall result -----------------------------------------------------------------
ALL_PASS, SKIPPED, PROBLEMS = "ALL PASS", "SKIPPED", "PROBLEMS FOUND"


def overall_result(problems, missing_docs):
    """ALL PASS, SKIPPED (only PDFs missing, nothing wrong) or PROBLEMS FOUND."""
    if problems:
        return PROBLEMS
    if missing_docs:
        return SKIPPED
    return ALL_PASS
