"""Read any supported file into numbered parts, each with an exact location label.

The real type comes from the file's content, not only its extension. A part plays the role a
page plays in a PDF: search, the proof check, chat, quiz, flashcards, notebook, reading mode
and book maker all work on it the same way. The label says where it is ("Lines 3-5", "Row 4").
PDFs are read by learnbot.pdf_text and checked by learnbot.pdf_check; images and scanned files
need OCR, which is planned (PLAN.md section 3).
"""

import csv
import io
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

from learnbot import config
from learnbot.chunking import Chunk, split_long
from learnbot.pdf_check import FAIL, OK, WARNING, check_pdf, check_size_limit

PDF, TXT, MD, CSV, HTML, DOCX, PPTX, XLSX = "pdf", "txt", "md", "csv", "html", "docx", "pptx", "xlsx"
OLD_OFFICE, IMAGE = "old_office", "image"
TEXT_EXTENSIONS = {".txt": TXT, ".md": MD, ".csv": CSV, ".html": HTML, ".htm": HTML}
OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"  # old Office files, and any password-protected Office file
IMAGE_MAGIC = (b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff")

CANT_READ = "This file type can't be read."
OLD_FORMAT = ("This file is an old Office format (.doc, .xls, .ppt) or is password protected. "
              "Please save it as .docx, .xlsx or .pptx without a password and try again.")
NO_OCR_YET = "Images can't be read yet."
CORRUPTED = "This file could not be read. It may be damaged."
NO_TEXT = "No text was found in this file."
FEW_WORDS = "This file has very little text, so many questions may have no answer."
LOOKS_GOOD = "File looks good."

MD_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$")
CSV_DELIMITERS = ",;\t|"


class ReadError(Exception):
    """A friendly message for the user; never the library's own error text."""


@dataclass
class Part:
    text: str
    label: str
    title: str = ""


def detect_type(path):
    """The file's real type from its content, or None if it can't be read."""
    path = Path(path)
    with open(path, "rb") as f:
        head = f.read(4096)
    if head.startswith(b"%PDF-"):
        return PDF
    if head.startswith(OLE_MAGIC):
        return OLD_OFFICE
    if head.startswith(IMAGE_MAGIC):
        return IMAGE
    if head.startswith(b"PK"):
        return office_type(path)
    if b"\x00" in head:
        return None
    return text_type(path, head)


def office_type(path):
    """docx, pptx or xlsx from the names inside the zip file, or None for any other zip."""
    try:
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
    except zipfile.BadZipFile:
        return None
    if "[Content_Types].xml" not in names:
        return None
    for prefix, kind in (("word/", DOCX), ("ppt/", PPTX), ("xl/", XLSX)):
        if any(name.startswith(prefix) for name in names):
            return kind
    return None


def text_type(path, head):
    """A text file's type from its extension; a page that starts like HTML is HTML."""
    kind = TEXT_EXTENSIONS.get(path.suffix.lower())
    start = head.lstrip(b"\xef\xbb\xbf \r\n\t").lower()
    if kind and (start.startswith(b"<!doctype html") or start.startswith(b"<html")):
        return HTML
    return kind


def read_text(path):
    data = Path(path).read_bytes()
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def line_label(first, last):
    return f"Line {first}" if first == last else f"Lines {first}-{last}"


def read_plain(path, markdown=False):
    """One part per paragraph (blank lines between). Markdown headings become titles."""
    parts, lines, first, title = [], [], 0, ""

    def close(last):
        if lines:
            parts.append(Part(" ".join(lines), line_label(first, last), title))
            lines.clear()

    all_lines = read_text(path).splitlines()
    for number, line in enumerate(all_lines, start=1):
        heading = MD_HEADING.match(line) if markdown else None
        if heading or not line.strip():
            close(number - 1)
            if heading:
                title = heading.group(1)
            continue
        if not lines:
            first = number
        lines.append(line.strip())
    close(len(all_lines))
    return parts


def row_text(headers, cells):
    """ "Name: value; Name: value", leaving out empty cells."""
    pairs = []
    for i, cell in enumerate(cells):
        if str(cell).strip():
            name = headers[i].strip() if i < len(headers) else ""
            pairs.append(f"{name}: {str(cell).strip()}" if name else str(cell).strip())
    return "; ".join(pairs)


def csv_delimiter(text):
    first_line = next((line for line in text.splitlines() if line.strip()), "")
    return max(CSV_DELIMITERS, key=first_line.count)


def read_csv(path):
    """One part per row after the header row. The label is the row number in the file."""
    text = read_text(path)
    rows = list(csv.reader(io.StringIO(text), delimiter=csv_delimiter(text)))
    filled = [(n, row) for n, row in enumerate(rows, start=1) if any(cell.strip() for cell in row)]
    if not filled:
        return []
    headers = filled[0][1]
    return [Part(row_text(headers, row), f"Row {n}") for n, row in filled[1:]]


HTML_BLOCKS = ("h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "tr", "pre", "blockquote", "dd", "dt", "div")
HTML_HEADINGS = ("h1", "h2", "h3", "h4", "h5", "h6")


def tree_label(heading, number):
    return f"{heading}, paragraph {number}" if heading else f"Paragraph {number}"


def read_html(path):
    """One part per paragraph, list item or table row, under its heading."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(read_text(path), "html.parser")
    for tag in soup(["script", "style", "noscript", "head", "template"]):
        tag.decompose()
    parts, heading, number = [], "", 0
    for block in soup.find_all(HTML_BLOCKS):
        if block.find(HTML_BLOCKS):  # only the innermost block, so no text is read twice
            continue
        if block.name == "tr":
            text = " | ".join(cell.get_text(" ", strip=True) for cell in block.find_all(["td", "th"]))
        else:
            text = block.get_text(" ", strip=True)
        text = " ".join(text.split())
        if not text:
            continue
        if block.name in HTML_HEADINGS:
            heading, number = text, 0
            continue
        number += 1
        parts.append(Part(text, tree_label(heading, number), heading))
    return parts


def table_row_text(row):
    """A Word or PowerPoint table row, with merged cells read once."""
    cells = []
    for cell in row.cells:
        text = " ".join(cell.text.split())
        if text and (not cells or cells[-1] != text):
            cells.append(text)
    return " | ".join(cells)


def read_docx(path):
    """One part per paragraph or table row, under its heading."""
    from docx import Document

    parts, heading, number = [], "", 0
    for block in Document(str(path)).iter_inner_content():
        if hasattr(block, "rows"):
            texts = [table_row_text(row) for row in block.rows]
        else:
            text = " ".join(block.text.split())
            style = block.style.name if block.style is not None else ""
            if text and style and (style.startswith("Heading") or style == "Title"):
                heading, number = text, 0
                continue
            texts = [text]
        for text in texts:
            if text:
                number += 1
                parts.append(Part(text, tree_label(heading, number), heading))
    return parts


def shape_lines(shape):
    """The visible text of one shape: text boxes, tables, and shapes inside a group."""
    if hasattr(shape, "shapes"):
        return [line for inner in shape.shapes for line in shape_lines(inner)]
    if getattr(shape, "has_table", False):
        return [table_row_text(row) for row in shape.table.rows]
    if getattr(shape, "has_text_frame", False):
        return [" ".join(p.text.split()) for p in shape.text_frame.paragraphs]
    return []


def read_pptx(path):
    """One part per slide that has text. Speaker notes are not on the slide, so they are left out."""
    from pptx import Presentation

    parts = []
    for number, slide in enumerate(Presentation(str(path)).slides, start=1):
        lines = [line for shape in slide.shapes for line in shape_lines(shape) if line]
        title = slide.shapes.title.text.strip() if slide.shapes.title is not None else ""
        if lines:
            parts.append(Part("\n".join(lines), f"Slide {number}", title))
    return parts


def cell_text(cell):
    """A cell as the user sees it: 12.0 as 12, 0.5 with a percent format as 50%, a date as a date."""
    value = cell.value
    if value is None:
        return ""
    if hasattr(value, "isoformat"):  # a date with no time of day shows only the date
        return value.isoformat().removesuffix("T00:00:00")
    if isinstance(value, bool):
        return str(value).upper()
    if isinstance(value, (int, float)):
        form = cell.number_format or ""
        if "%" in form:
            decimals = len(form.split(".")[1].split("%")[0]) if "." in form else 0
            return f"{value * 100:.{decimals}f}%"
        return str(int(value)) if value == int(value) else str(value)
    return str(value)


def read_xlsx(path):
    """One part per row after each sheet's header row. Formulas show their last saved value."""
    from openpyxl import load_workbook

    parts = []
    book = load_workbook(path, read_only=True, data_only=True)
    for sheet in book.worksheets:
        headers = None
        for number, row in enumerate(sheet.iter_rows(min_row=1), start=1):
            cells = [cell_text(cell) for cell in row]
            if not any(cell.strip() for cell in cells):
                continue
            if headers is None:
                headers = cells
                continue
            parts.append(Part(row_text(headers, cells), f"{sheet.title}, row {number}", sheet.title))
    book.close()
    return parts


def read_parts(path, kind):
    readers = {TXT: read_plain, MD: lambda p: read_plain(p, markdown=True), CSV: read_csv, HTML: read_html,
               DOCX: read_docx, PPTX: read_pptx, XLSX: read_xlsx}
    return readers[kind](path)


def read_file(path, kind=None):
    """[Part] of any supported file except a PDF. Raises ReadError with a friendly message."""
    kind = kind or detect_type(path)
    if kind == OLD_OFFICE:
        raise ReadError(OLD_FORMAT)
    if kind == IMAGE:
        raise ReadError(NO_OCR_YET)
    if kind is None or kind == PDF:
        raise ReadError(CANT_READ)
    try:
        return read_parts(path, kind)
    except Exception:  # noqa: BLE001 - a damaged file must never crash; the error text is not shown
        raise ReadError(CORRUPTED) from None


def part_chunks(doc, parts):
    """Search pieces of the parts. A part's number is its position, starting at 1."""
    return [Chunk(doc, number, part.title, piece, part.label)
            for number, part in enumerate(parts, start=1)
            for piece in split_long(part.text)]


@dataclass
class FileCheck:
    """The same verdict as the PDF self-check, for any other file."""

    verdict: str
    reasons: list
    page_count: int = 0  # parts


def check_file(path):
    """Self-check of any file: OK / WARNING / FAIL. PDFs use the PDF self-check."""
    path = Path(path)
    too_big = check_size_limit(path.stat().st_size)
    if too_big:
        return FileCheck(FAIL, [too_big])
    kind = detect_type(path)
    if kind == PDF:
        return check_pdf(path)
    try:
        parts = read_file(path, kind)
    except ReadError as problem:
        return FileCheck(FAIL, [str(problem)])
    if not parts:
        return FileCheck(FAIL, [NO_TEXT])
    words = sum(len(part.text.split()) for part in parts)
    if words < config.LOW_TEXT_WORDS:
        return FileCheck(WARNING, [FEW_WORDS], len(parts))
    return FileCheck(OK, [LOOKS_GOOD], len(parts))
