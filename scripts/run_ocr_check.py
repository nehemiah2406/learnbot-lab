"""OCR check on a scanned copy of a public page we already have (no downloads, no AI calls).

Run:  .venv\\Scripts\\python scripts\\run_ocr_check.py boaters_guide.pdf --page 16

1. Renders the page to an image and saves it as an image-only PDF (a "scan") in data/raw
   (gitignored): <name>_p<page>_scanned.pdf.
2. OCRs the scan and compares it with the page's real text layer: word accuracy, and EVERY
   misread number (Hari's rule: OCR can misread numbers, so each one is reported).
3. Does the same on a blurred, low-resolution copy, to see that unclear lines become
   [unclear text] (never proof) instead of wrong text.
"""

import argparse
import difflib
import re
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy  # noqa: E402
import pdfplumber  # noqa: E402
from PIL import Image, ImageFilter  # noqa: E402

from learnbot import config, ocr  # noqa: E402
from learnbot.pdf_text import read_page_text  # noqa: E402
from learnbot.proof import UNCLEAR  # noqa: E402

DATA_DIR = Path("data/raw")
NUMBER = re.compile(r"\d+(?:[.,:/-]\d+)*")
WORD = re.compile(r"[A-Za-z0-9]+(?:[.,:/-][A-Za-z0-9]+)*")


def words(text):
    return [w.lower() for w in WORD.findall(text.replace(UNCLEAR, " "))]


def make_scan(source, page, target):
    image = Image.fromarray(ocr.render(source, page))
    image.save(target, "PDF", resolution=config.OCR_DPI)
    return image


def report(title, truth, lines, seconds):
    text = ocr.page_text(lines)
    true_words, read_words = words(truth), words(text)
    matcher = difflib.SequenceMatcher(None, true_words, read_words, autojunk=False)
    same = sum(block.size for block in matcher.get_matching_blocks())
    true_numbers, read_numbers = Counter(NUMBER.findall(truth)), Counter(NUMBER.findall(text))
    unclear = [line for line in lines if line[1] < config.OCR_MIN_CONFIDENCE]
    print(f"\n=== {title} ===")
    print(f"OCR time: {seconds:.1f} s | lines: {len(lines)} | [unclear text] lines (score < {config.OCR_MIN_CONFIDENCE}): {len(unclear)}")
    print(f"words: {same} of {len(true_words)} read right ({same / max(len(true_words), 1):.1%})")
    print(f"numbers on the page: {sum(true_numbers.values())} | read right: {sum((true_numbers & read_numbers).values())}")
    missed = true_numbers - read_numbers
    extra = read_numbers - true_numbers
    print("numbers MISSED or misread:", dict(missed) or "none")
    print("numbers in the OCR text that are not on the page (misreads):", dict(extra) or "none")
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag != "equal" and any(NUMBER.fullmatch(w) for w in true_words[i1:i2] + read_words[j1:j2]):
            print(f"  number difference: page {' '.join(true_words[i1:i2])!r} -> OCR {' '.join(read_words[j1:j2])!r}")
    lowest = sorted(lines, key=lambda line: line[1])[:5]
    print("lowest scores:", [(round(score, 3), text[:40]) for text, score, *_ in lowest])
    wrong_clear = [(round(score, 3), text) for text, score, *_ in lines
                   if score >= config.OCR_MIN_CONFIDENCE and any(n not in truth for n in NUMBER.findall(text))]
    print("CLEAR lines with a number not on the page (would be proof!):", wrong_clear or "none")
    return text


def main():
    sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("document", help="a PDF in data/raw with a text layer")
    parser.add_argument("--page", type=int, default=1)
    args = parser.parse_args()

    source = DATA_DIR / args.document
    with pdfplumber.open(source) as pdf:
        truth = read_page_text(pdf.pages[args.page - 1])
    target = DATA_DIR / f"{source.stem}_p{args.page}_scanned.pdf"
    image = make_scan(source, args.page, target)
    with pdfplumber.open(target) as pdf:
        scanned_text = read_page_text(pdf.pages[0])
        print(f"scan saved: {target} | its text layer: {len(scanned_text)} characters | needs OCR: {ocr.needs_ocr(scanned_text, pdf.pages[0])}")

    engine = ocr.default_engine()
    start = time.perf_counter()
    lines = ocr.ocr_lines(ocr.render(target, 1), engine)
    report(f"clear scan, {config.OCR_DPI} dpi", truth, lines, time.perf_counter() - start)

    small = image.resize((image.width // 3, image.height // 3)).filter(ImageFilter.GaussianBlur(1.2))
    start = time.perf_counter()
    lines = ocr.ocr_lines(numpy.array(small.convert("RGB")), engine)
    report("blurred, one third size", truth, lines, time.perf_counter() - start)
    return 0


if __name__ == "__main__":
    sys.exit(main())
