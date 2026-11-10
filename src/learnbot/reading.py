"""Reading mode: the exact text of one page, and questions answered only from that page.

Reading needs no AI and shows no summaries. A question goes through the chat pipeline and proof
check (learnbot.answer), with only that page's pieces; anything else is "Not on this page".
A page whose columns may be mixed (learnbot.pdf_text.page_is_mixed) shows a warning.
"""

from dataclasses import dataclass

import pdfplumber

from learnbot.answer import answer_within
from learnbot.ocr import OCR_NOTE
from learnbot.pdf_text import page_is_mixed
from learnbot.rule_sets import RuleSets
from learnbot.search import ScopedSearcher

NOT_ON_PAGE = "Not on this page"
MIXED_WARNING = "Warning: this page has mixed columns, so its lines may be out of order."


@dataclass
class PageView:
    doc: str
    page: int
    total: int
    text: str
    previous: int = None  # page number, None on the first page
    next: int = None  # page number, None on the last page
    warning: str = ""
    where: str = ""  # location in a file with no pages ("Row 4")


def check_page(document, page):
    if page not in document.pages:
        raise ValueError(f"{document.name} has pages 1 to {len(document.pages)}.")


def view_page(document, path, page):
    """The page's exact text. path: the file itself, for the layout check (PDFs only).
    Raises ValueError."""
    check_page(document, page)
    warning = ""
    if page in getattr(document, "ocr_pages", []):
        warning = OCR_NOTE
    elif not document.labels:
        with pdfplumber.open(path) as pdf:
            warning = MIXED_WARNING if page_is_mixed(pdf.pages[page - 1]) else ""
    total = len(document.pages)
    return PageView(document.name, page, total, document.pages[page], page - 1 if page > 1 else None,
                    page + 1 if page < total else None, warning, document.labels.get(page, ""))


def page_searcher(document, page):
    pieces = [c for c in document.chunks if c.page == page]

    def page_text(doc, number):
        return document.pages[page] if (doc, number) == (document.name, page) else None
    return ScopedSearcher(pieces, page_text, RuleSets(document.chunks))


def ask_page(question, document, page, chain):
    """An Answer from this page only, or "Not on this page". Raises ValueError for a bad page."""
    check_page(document, page)
    return answer_within(question, page_searcher(document, page), chain, NOT_ON_PAGE)
