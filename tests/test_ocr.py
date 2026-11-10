"""OCR for scanned PDF pages: detection, reading order, [unclear text], labels, proof, self-check.
Most tests use a fake OCR engine; one runs the real rapidocr on a small generated image."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image, ImageDraw, ImageFont

from learnbot import config, ocr, proof
from learnbot.index import load_document
from learnbot.pdf_check import FAIL, check_pdf
from learnbot.reading import view_page
from learnbot.rule_sets import RuleSets

LINE = "The ladder rungs must be spaced 12 inches apart along the side rails."


def scanned_pdf(path, pages=1):
    """An image-only PDF (no text layer), like a scan."""
    images = []
    for _ in range(pages):
        image = Image.new("RGB", (1000, 400), "white")
        ImageDraw.Draw(image).text((40, 150), "Scanned text", fill="black", font=ImageFont.load_default(size=48))
        images.append(image)
    images[0].save(path, "PDF", save_all=True, append_images=images[1:])
    return path


class FakeEngine:
    """Gives fixed lines: [(text, score, box)]."""

    def __init__(self, lines):
        self.lines = lines

    def __call__(self, image):
        return SimpleNamespace(txts=[t for t, _, _ in self.lines], scores=[s for _, s, _ in self.lines],
                               boxes=[b for _, _, b in self.lines])


def box(left, top, width=300, height=30):
    return [[left, top], [left + width, top], [left + width, top + height], [left, top + height]]


# --- Which pages -----------------------------------------------------------------------
def test_only_a_page_with_little_text_and_an_image_needs_ocr():
    scan = SimpleNamespace(images=[{"x0": 0}])
    assert ocr.needs_ocr("", scan) is True
    assert ocr.needs_ocr("x" * config.LOW_TEXT_CHARS, scan) is False  # real text layer
    assert ocr.needs_ocr("", SimpleNamespace(images=[])) is False  # blank page


# --- Reading order and unclear lines -------------------------------------------------
def test_lines_are_read_top_to_bottom_and_left_to_right():
    lines = [("second row", 0.99, 100, 50, 30), ("first row right", 0.99, 10, 400, 30), ("first row left", 0.99, 12, 50, 30)]
    assert ocr.page_text(lines, 0.9) == "first row left first row right\nsecond row"


def test_low_confidence_line_becomes_unclear_and_is_never_shown_as_text():
    lines = [("Carry 3 flares.", 0.99, 10, 0, 30), ("Carry 8 flares.", 0.50, 60, 0, 30)]
    text = ocr.page_text(lines, 0.9)
    assert text == f"Carry 3 flares.\n{proof.UNCLEAR}" and "8" not in text


def test_fake_engine_lines_become_page_text():
    engine = FakeEngine([(LINE, 0.98, box(10, 10)), ("noise", 0.2, box(10, 80))])
    assert ocr.page_text(ocr.ocr_lines("image", engine)) == f"{LINE}\n{proof.UNCLEAR}"


# --- Proof: unclear text is never proof ---------------------------------------------
def test_quote_that_touches_unclear_text_is_refused():
    page = f"Visual distress signals: {proof.UNCLEAR} must be carried on board at all times."
    piece = SimpleNamespace(doc="scan.pdf", page=1, title="", text=page, where=ocr.where(1), search_text=page)
    reply = {"answer": "unclear text", "sources": [{"doc": "scan.pdf", "page": 1, "quote": "[unclear text] must be carried on board at all times."}]}
    result = proof.check("What must be carried on board?", reply, [piece], lambda d, p: page, RuleSets([]))
    assert not result.ok and result.reason == "quote_unclear"


def test_clear_ocr_line_can_be_proof():
    piece = SimpleNamespace(doc="scan.pdf", page=1, title="", text=LINE, where=ocr.where(1), search_text=LINE)
    reply = {"answer": "12 inches apart", "sources": [{"doc": "scan.pdf", "page": 1, "quote": LINE}]}
    assert proof.check("How far apart must ladder rungs be spaced?", reply, [piece], lambda d, p: LINE, RuleSets([])).ok


# --- Index, labels and saved pieces -----------------------------------------------------
def test_scanned_page_is_read_by_ocr_once_and_labelled(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(ocr, "ocr_page", lambda path, number, engine=None: calls.append(number) or LINE)
    pdf = scanned_pdf(tmp_path / "scan.pdf")
    first = load_document(pdf, tmp_path / "storage")
    second = load_document(pdf, tmp_path / "storage")
    assert calls == [1] and first.ocr_pages == second.ocr_pages == [1]
    assert first.pages[1] == LINE and second.chunks[0].where == "p.1 (scanned, OCR)"
    saved = json.loads(next((tmp_path / "storage" / "pieces").glob("*.json")).read_text(encoding="utf-8"))
    assert saved["ocr_pages"] == [1]


def test_page_with_a_text_layer_is_not_ocrd(monkeypatch):
    pdf = Path("data/raw/osha3124.pdf")  # public test document, not committed
    if not pdf.is_file():
        pytest.skip("public test document not on this laptop")
    monkeypatch.setattr(ocr, "ocr_page", lambda *args, **kwargs: pytest.fail("OCR must not run"))
    pages, ocr_pages = ocr.read_pdf_pages(pdf)
    assert ocr_pages == [] and len(pages) == 15


def test_reading_mode_shows_the_ocr_note(tmp_path, monkeypatch):
    monkeypatch.setattr(ocr, "ocr_page", lambda path, number, engine=None: LINE)
    pdf = scanned_pdf(tmp_path / "scan.pdf")
    view = view_page(load_document(pdf, tmp_path / "storage"), pdf, 1)
    assert view.text == LINE and view.warning == ocr.OCR_NOTE


# --- Upload self-check ----------------------------------------------------------------
def test_scanned_pdf_is_no_longer_refused_and_the_check_says_ocr(tmp_path):
    result = check_pdf(scanned_pdf(tmp_path / "scan.pdf", pages=2))
    assert result.verdict != FAIL and result.ocr_pages == [1, 2]
    assert any("OCR" in note for note in result.notes)


# --- The real engine ----------------------------------------------------------------
def test_real_ocr_reads_a_clear_line(tmp_path):
    image = Image.new("RGB", (1400, 200), "white")
    ImageDraw.Draw(image).text((30, 60), "Rungs 12 inches apart", fill="black", font=ImageFont.load_default(size=64))
    import numpy

    lines = ocr.ocr_lines(numpy.array(image))
    text = ocr.page_text(lines)
    assert "12" in text and "inches" in text.lower()
    assert all(score >= config.OCR_MIN_CONFIDENCE for _, score, *_ in lines)
