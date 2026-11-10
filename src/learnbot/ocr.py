"""OCR for scanned PDF pages with rapidocr: local, no AI, no internet (its models are in the package).

A PDF page is read by OCR only if its text layer has fewer than config.LOW_TEXT_CHARS
characters AND it holds an image (a scan). Blank pages and pages with real text are never
OCR'd. OCR runs once per file, when its pieces are first made; the text is saved with the
pieces (learnbot.index), so it is never repeated.

Hari's lessons:
- Low-confidence OCR text is never proof. Each OCR line has a confidence score; a line below
  config.OCR_MIN_CONFIDENCE becomes UNCLEAR in the page text, so it cannot be quoted, and the
  proof check refuses any quote that touches UNCLEAR (learnbot.proof).
- OCR can misread numbers. Answers from an OCR page say so in their location
  ("p.3 (scanned, OCR)"), and the OCR test reports every misread number.

Known limit: lines are put in reading order top to bottom, left to right, so a scanned page
with two columns may mix them.
"""

import threading

import pdfplumber

from learnbot import config
from learnbot.pdf_text import read_page_text
from learnbot.proof import UNCLEAR

OCR_NOTE = "This page was read from a scanned image (OCR). Unclear parts show as [unclear text]; check numbers on the page."

_engine = None
_engine_lock = threading.Lock()


def default_engine():
    """The rapidocr engine, loaded once (its models are in the package; nothing is downloaded)."""
    global _engine
    with _engine_lock:
        if _engine is None:
            from rapidocr import RapidOCR

            _engine = RapidOCR(params={"Global.log_level": "critical"})
    return _engine


def needs_ocr(text, page):
    """True for a page with almost no text layer but an image: a scanned page."""
    return len(text.strip()) < config.LOW_TEXT_CHARS and bool(page.images)


def where(page_number):
    """The location shown for a piece from an OCR page."""
    return f"p.{page_number} (scanned, OCR)"


def render(path, page_number, dpi=None):
    """One PDF page as an RGB image (numpy array), with pypdfium2 (already used by pdfplumber)."""
    import numpy
    import pypdfium2

    pdf = pypdfium2.PdfDocument(str(path))
    try:
        image = pdf[page_number - 1].render(scale=(dpi or config.OCR_DPI) / 72).to_pil().convert("RGB")
    finally:
        pdf.close()
    return numpy.array(image)


def ocr_lines(image, engine=None):
    """[(text, score, top, left, height)] for each line rapidocr finds."""
    out = (engine or default_engine())(image)
    if not out.txts:
        return []
    lines = []
    for text, score, box in zip(out.txts, out.scores, out.boxes):
        ys, xs = [float(p[1]) for p in box], [float(p[0]) for p in box]
        lines.append((str(text), float(score), min(ys), min(xs), max(ys) - min(ys)))
    return lines


def page_text(lines, min_confidence=None):
    """The page text in reading order: boxes on the same row joined with spaces, rows with
    new lines. A box below the confidence limit becomes UNCLEAR (never proof)."""
    limit = config.OCR_MIN_CONFIDENCE if min_confidence is None else min_confidence
    rows = []
    for line in sorted(lines, key=lambda line: (line[2], line[3])):
        text, score, top, left, height = line
        if rows and abs(top - rows[-1][0][2]) < max(rows[-1][0][4], height) / 2:
            rows[-1].append(line)
        else:
            rows.append([line])
    shown = []
    for row in rows:
        parts = [text if score >= limit else UNCLEAR for text, score, *_ in sorted(row, key=lambda line: line[3])]
        shown.append(" ".join(parts))
    return "\n".join(shown)


def ocr_page(path, page_number, engine=None):
    return page_text(ocr_lines(render(path, page_number), engine))


def read_pdf_pages(path, engine=None):
    """({page number: text}, [OCR page numbers]): the text layer, or OCR for scanned pages."""
    pages, ocr_pages = {}, []
    with pdfplumber.open(path) as pdf:
        for number, page in enumerate(pdf.pages, start=1):
            text = read_page_text(page)
            if needs_ocr(text, page):
                text = ocr_page(path, number, engine)
                ocr_pages.append(number)
            pages[number] = text
            page.close()
    return pages, ocr_pages
