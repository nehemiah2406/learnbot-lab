"""Check one PDF or every PDF in a folder, and save a report for each.

Run:  .venv\\Scripts\\python scripts\\data_check.py data\\raw
      .venv\\Scripts\\python scripts\\data_check.py data\\raw\\nav_rules.pdf
Reports are saved as reports/data_check_<filename>.md. No LLM calls.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from learnbot.pdf_check import FAIL, build_report, check_pdf  # noqa: E402

REPORTS_DIR = Path("reports")


def find_pdfs(path):
    """The PDF itself, or every PDF in the folder (sorted)."""
    path = Path(path)
    if path.is_dir():
        return sorted(p for p in path.iterdir() if p.suffix.lower() == ".pdf")
    return [path]


def report_path(pdf_path):
    return REPORTS_DIR / f"data_check_{Path(pdf_path).stem}.md"


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print("Usage: python scripts/data_check.py <file.pdf or folder>")
        return 2
    pdfs = find_pdfs(argv[0])
    if not pdfs:
        print(f"No PDF files found in {argv[0]}")
        return 1

    # Windows consoles may not support every PDF character; replace instead of crashing.
    sys.stdout.reconfigure(errors="replace")
    REPORTS_DIR.mkdir(exist_ok=True)
    any_fail = False
    for pdf in pdfs:
        result = check_pdf(pdf)
        out = report_path(pdf)
        out.write_text(build_report(result), encoding="utf-8")
        any_fail = any_fail or result.verdict == FAIL
        print(f"{pdf.name}: {result.verdict} ({result.page_count} pages)")
        for reason in result.reasons:
            print(f"  - {reason}")
        print(f"  Report: {out.as_posix()}")
    return 1 if any_fail else 0


if __name__ == "__main__":
    sys.exit(main())
