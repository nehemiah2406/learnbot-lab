"""Fill the accepted_sources column of an eval CSV from the real PDFs. No AI calls.

Run:  .venv\\Scripts\\python scripts\\find_accepted_sources.py [eval/explain_questions.csv]
For every row, the row's quote text (leading paragraph marker removed) is searched on
every page of every document named in the eval set; each page with the same text is an
accepted source; if the question names a rule set, only pages of that rule set (same rule
as the app). scripts/check_eval.py verifies the column afterwards.
"""

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from learnbot.eval_check import (  # noqa: E402
    EXPLAIN_COLUMNS, DocumentPages, find_accepted_sources, format_sources, load_rows,
)

TRAP_CSV = Path("eval/trap_questions.csv")


def main():
    sys.stdout.reconfigure(errors="replace")
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("eval/explain_questions.csv")
    rows = load_rows(path)
    docs = DocumentPages()
    # Search the same documents as the main eval set (all 3 test PDFs).
    doc_names = sorted({r["doc"] for r in rows + load_rows(TRAP_CSV)})
    missing = [d for d in doc_names if not docs.exists(d)]
    if missing:
        print(f"SKIPPED: PDF(s) not in data/raw: {', '.join(missing)}; {path} not changed")
        return 0
    rule_sets = docs.rule_sets(doc_names)
    for row in rows:
        sources = find_accepted_sources(row, docs, doc_names, rule_sets)
        row["accepted_sources"] = format_sources(sources)
        extra = [f"{d}:{p}" for d, p in sources if not (d == row["doc"] and str(p) in row["page"].split("|"))]
        print(f"{row['id']}: {row['accepted_sources']}" + (f"   (extra: {', '.join(extra)})" if extra else ""))
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=EXPLAIN_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows({c: row.get(c, "") for c in EXPLAIN_COLUMNS} for row in rows)
    print(f"Saved {path.as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
