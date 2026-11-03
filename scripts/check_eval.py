"""Check the eval set against the real PDFs and print a summary.

Run:  .venv\\Scripts\\python scripts\\check_eval.py
      .venv\\Scripts\\python scripts\\check_eval.py --explain eval/holdout_questions.csv --traps eval/holdout_traps.csv
Exit code 0 only if every row passes. No LLM calls.
"""

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from learnbot.eval_check import (  # noqa: E402
    PROBLEMS,
    SKIPPED,
    DocumentPages,
    check_explain_row,
    check_trap_row,
    duplicate_ids,
    find_same_fact_pages,
    load_rows,
    overall_result,
    verify_accepted_sources,
    verify_other_answers,
    verify_quotes,
    verify_trap,
)

EXPLAIN_CSV = Path("eval/explain_questions.csv")
TRAP_CSV = Path("eval/trap_questions.csv")


def same_fact_reviews(explain, docs):
    """{row id: [(doc, page, snippet)]}: pages with the same number + unit near the
    question's key words that the row does not list (to review by hand, not a failure)."""
    doc_names = sorted({r["doc"] for r in explain})
    if not all(docs.exists(d) for d in doc_names):
        return {}
    rule_sets = docs.rule_sets(doc_names)
    reviews = {}
    for row in explain:
        if not check_explain_row(row):
            found = find_same_fact_pages(row, docs, doc_names, rule_sets)
            if found:
                reviews[row["id"]] = found
    return reviews


def check_all(explain, traps, docs):
    """(problems by row id, quotes verified, quotes checked, traps verified, missing docs)."""
    problems = {}
    verified = checked = traps_ok = 0
    missing_docs = set()
    for dup in duplicate_ids(explain + traps):
        problems.setdefault(dup, []).append("duplicate id")

    doc_names = sorted({r["doc"] for r in explain + traps})
    all_docs_here = all(docs.exists(d) for d in doc_names)
    rule_sets = docs.rule_sets(doc_names) if all_docs_here else None
    for row in explain:
        row_problems = check_explain_row(row)
        if not row_problems:
            if not docs.exists(row["doc"]):
                missing_docs.add(row["doc"])
                continue
            checked += 1
            row_problems = verify_quotes(row, docs) + verify_other_answers(row, docs)
            if all_docs_here:  # accepted sources can only be checked with every PDF present
                row_problems += verify_accepted_sources(row, docs, doc_names, rule_sets)
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--explain", default=str(EXPLAIN_CSV))
    parser.add_argument("--traps", default=str(TRAP_CSV))
    args = parser.parse_args()
    explain, traps = load_rows(args.explain), load_rows(args.traps)
    print_counts(explain, traps)
    docs = DocumentPages()
    problems, verified, checked, traps_ok, missing_docs = check_all(explain, traps, docs)
    reviews = same_fact_reviews(explain, docs)
    print()
    print(f"Quotes verified on their page (and accepted sources complete): {verified}/{len(explain)}")
    print(f"Trap keywords absent from their document: {traps_ok}/{len(traps)}")
    for doc in sorted(missing_docs):
        print(f"SKIPPED: {doc} not found in data/raw (see PLAN.md Data section)")
    for row_id, row_problems in problems.items():
        for problem in row_problems:
            print(f"FAIL {row_id}: {problem}")
    print("\nPages with the same number + unit near the question words, not listed "
          f"(review by hand; add to other_answers only if they answer the same question): "
          f"{sum(len(v) for v in reviews.values())}")
    for row_id, found in reviews.items():
        for doc, page, snippet in found:
            print(f"REVIEW {row_id}: {doc}:{page}: ...{snippet}...")
    result = overall_result(problems, missing_docs)
    if result == SKIPPED:
        print(f"\nRESULT: SKIPPED ({len(missing_docs)} PDF(s) not in data/raw; nothing wrong found)")
    else:
        print("\nRESULT:", result)
    return 1 if result == PROBLEMS else 0


if __name__ == "__main__":
    sys.exit(main())
