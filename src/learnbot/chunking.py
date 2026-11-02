"""Split page text into small pieces (paragraphs) for search. Works for any PDF.

Rules (general, no file-specific code):
- Pieces never cross pages, so every piece has exactly one page number.
- A new piece starts at a paragraph marker at the start of a line: "(a)", "(iv)",
  "(12)", "§ 83.22", "1. ". Bullet lines ("•", "−") stay with their paragraph.
- Heading-like lines are not text: they become the piece's title (e.g.
  "—INTERNATIONAL— Lights and Shapes Rule 22 Visibility of Lights"). A heading starts
  with a capital letter or dash, has no end punctuation, and is clearly shorter than
  the page's typical line (narrow columns have short prose lines too).
- Lines with only a paragraph number ("(37)") carry no text and are skipped.
- Pieces under MIN_WORDS join the previous piece on the page (list items stay with
  their parent); pieces over MAX_WORDS are split at sentence ends.
"""

import re
from dataclasses import dataclass
from pathlib import Path

import pdfplumber

from learnbot.pdf_text import read_page_text

MIN_WORDS = 8
MAX_WORDS = 150
HEADING_MAX_WORDS = 8
# A heading is shorter than this share of a full line on the page.
HEADING_MAX_SHARE = 0.6
PARAGRAPH_START = re.compile(r"^\s*(\(([a-zA-Z]{1,4}|\d{1,3})\)|§\s*\d|\d{1,3}\.\s)")
MARKER_ONLY = re.compile(r"^\s*\(\d{1,4}\)\s*$")
END_PUNCTUATION = (".", ";", ":", ",", "?", "!")
SENTENCE_END = re.compile(r"(?<=[.;:?!])\s+")


@dataclass
class Chunk:
    doc: str
    page: int
    title: str
    text: str

    @property
    def search_text(self):
        return f"{self.title}\n{self.text}"


def full_line_length(lines):
    """Length of a full line on the page (90th percentile; short list lines don't pull it down)."""
    lengths = sorted(len(line.strip()) for line in lines if line.strip())
    return lengths[int(len(lengths) * 0.9)] if lengths else 0


def is_heading(line, typical_length):
    """Short line without end punctuation, starting with a capital letter or dash."""
    line = line.strip()
    if not line or PARAGRAPH_START.match(line) or line.endswith(END_PUNCTUATION):
        return False
    if len(line.split()) > HEADING_MAX_WORDS or len(line) >= HEADING_MAX_SHARE * typical_length:
        return False
    return line[0].isupper() or line[0] in "—-"


def word_count(text):
    return len(text.split())


def split_long(text, max_words=MAX_WORDS):
    """Split text at sentence ends into parts of at most max_words (a longer sentence stays whole)."""
    if word_count(text) <= max_words:
        return [text]
    parts, current = [], []
    for sentence in SENTENCE_END.split(text):
        if current and word_count(" ".join(current + [sentence])) > max_words:
            parts.append(" ".join(current))
            current = []
        current.append(sentence)
    if current:
        parts.append(" ".join(current))
    return parts


def paragraphs(page_text):
    """[(title, paragraph text)] for one page, before size rules."""
    result, lines, title, heading_run = [], [], "", []

    def close():
        if lines:
            result.append((title, " ".join(lines)))
            lines.clear()

    all_lines = page_text.splitlines()
    typical = full_line_length(all_lines)
    for line in all_lines:
        line = line.strip()
        if not line or MARKER_ONLY.match(line):
            continue
        if is_heading(line, typical):
            heading_run.append(line)
            continue
        if heading_run:  # a heading ends the paragraph and sets a new title
            close()
            title = " ".join(heading_run)
            heading_run = []
        if PARAGRAPH_START.match(line):
            close()
        lines.append(line)
    close()
    return result


def chunk_page(doc, page, page_text):
    """Chunks for one page, after merging short pieces and splitting long ones."""
    merged = []
    for title, text in paragraphs(page_text):
        if merged and word_count(text) < MIN_WORDS:
            merged[-1] = (merged[-1][0], merged[-1][1] + " " + text)
        else:
            merged.append((title, text))
    return [
        Chunk(doc=doc, page=page, title=title, text=part)
        for title, text in merged
        for part in split_long(text)
    ]


def read_pdf_pages(path):
    """{page number: text} for one PDF, using the column-aware page reading."""
    with pdfplumber.open(path) as pdf:
        return {n: read_page_text(page) for n, page in enumerate(pdf.pages, start=1)}


def chunk_pages(doc, pages):
    """All chunks of one document from its {page number: text}."""
    return [c for n, text in sorted(pages.items()) for c in chunk_page(doc, n, text)]


def chunk_pdf(path):
    """All chunks of one PDF (path may be a str or a Path)."""
    path = Path(path)
    return chunk_pages(path.name, read_pdf_pages(path))
