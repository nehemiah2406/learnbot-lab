"""Check the eval set against the real PDFs and print a summary.

Run:  .venv\\Scripts\\python scripts\\check_eval.py
Exit code 0 only if every row passes. No LLM calls.
"""

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from learnbot.eval_check import (  # noqa: E402
    DocumentPages,
    check_explain_row,
    check_trap_row,
    duplicate_ids,
    load_rows,
    verify_quotes,
    verify_trap,
)

EXPLAIN_CSV = Path("eval/explain_questions.csv")
TRAP_CSV = Path("eval/trap_questions.csv")


def check_all(explain, traps, docs):
    """(problems by row id, quotes verified, quotes checked, traps verified, missing docs)."""
    problems = {}
    verified = checked = traps_ok = 0
    missing_docs = set()
    for dup in duplicate_ids(explain + traps):
        problems.setdefault(dup, []).append("duplicate id")

    for row in explain:
        row_problems = check_explain_row(row)
        if not row_problems:
            if not docs.exists(row["doc"]):
                missing_docs.add(row["doc"])
                continue
            checked += 1
            row_problems = verify_quotes(row, docs)
            verified += not row_problems
        if row_problems:
            problems.setdefault(row.get("id", "?"), []).extend(row_problems)

    for row in traps:
        row_problems = check_trap_row(row)
        if not row_problems:
            if not docs.exists(row["doc"]):
                missing_docs.add(row["doc"])
                continue
            row_problems = verify_trap(row, docs)
            traps_ok += not row_problems
        if row_problems:
            problems.setdefault(row.get("id", "?"), []).extend(row_problems)
    return problems, verified, checked, traps_ok, missing_docs


def print_counts(explain, traps):
    types = ["fact", "number", "compare", "paraphrase", "annex"]
    docs = sorted({r["doc"] for r in explain + traps})
    by_doc = Counter((r["doc"], r["type"]) for r in explain)
    trap_by_doc = Counter(r["doc"] for r in traps)
    header = f"{'doc':<22}" + "".join(f"{t:>11}" for t in types) + f"{'total':>8}{'traps':>8}"
    print(header)
    print("-" * len(header))
    for doc in docs:
        counts = [by_doc[(doc, t)] for t in types]
        print(f"{doc:<22}" + "".join(f"{c:>11}" for c in counts) + f"{sum(counts):>8}{trap_by_doc[doc]:>8}")
    totals = [sum(by_doc[(d, t)] for d in docs) for t in types]
    print(f"{'TOTAL':<22}" + "".join(f"{c:>11}" for c in totals) + f"{len(explain):>8}{len(traps):>8}")


def main():
    sys.stdout.reconfigure(errors="replace")
    explain, traps = load_rows(EXPLAIN_CSV), load_rows(TRAP_CSV)
    print_counts(explain, traps)
    problems, verified, checked, traps_ok, missing_docs = check_all(explain, traps, DocumentPages())
    print()
    print(f"Quotes verified on their page: {verified}/{len(explain)}")
    print(f"Trap keywords absent from their document: {traps_ok}/{len(traps)}")
    for doc in sorted(missing_docs):
        print(f"SKIPPED: {doc} not found in data/raw (see PLAN.md Data section)")
    for row_id, row_problems in problems.items():
        for problem in row_problems:
            print(f"FAIL {row_id}: {problem}")
    ok = not problems and not missing_docs
    print("\nRESULT:", "ALL PASS" if ok else "PROBLEMS FOUND")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
