"""Run the keyword-search baseline on the eval set and save eval/results.md.

Run:  .venv\\Scripts\\python scripts\\run_baseline.py
Uses every PDF in data/raw as one search index (like one user who uploaded them all).
No LLM calls.
"""

import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from learnbot import config  # noqa: E402
from learnbot.baseline import NOT_FOUND, BM25Index, answer  # noqa: E402
from learnbot.chunking import chunk_pdf  # noqa: E402
from learnbot.eval_check import load_rows  # noqa: E402
from learnbot.evaluate import (  # noqa: E402
    MISSED, REFUSED, RIGHT, TRAP_ANSWERED, WRONG,
    choose_threshold, exact_answer_in, on_right_page, outcome, sweep,
)

DATA_DIR = Path("data/raw")
RESULTS = Path("eval/results.md")
SWEEP_STEPS = [round(0.5 * i, 1) for i in range(0, 41)]  # 0.0 .. 20.0


def pct(n, total):
    return f"{n}/{total} ({100 * n / total:.0f}%)" if total else "0/0"


def short(text, n=120):
    text = " ".join(text.split())
    return text if len(text) <= n else text[:n] + "..."


def run(index, explain, traps):
    """Answer every question once; return per-question records and timing."""
    records, times = [], []
    for row, is_trap in [(r, False) for r in explain] + [(r, True) for r in traps]:
        start = time.perf_counter()
        verdict, hits = answer(index, row["question"])
        times.append(time.perf_counter() - start)
        record = {
            "row": row, "trap": is_trap, "hits": hits, "verdict": verdict,
            "outcome": outcome(row, is_trap, verdict, hits),
        }
        if not is_trap:
            record["top3"] = any(on_right_page(row, h) for h in hits)
            record["exact"] = verdict != NOT_FOUND and exact_answer_in(row["expected_answer"], hits[0].chunk.text)
        records.append(record)
    return records, times


def group_table(records, key, title):
    groups = defaultdict(list)
    for r in records:
        groups[key(r)].append(r)
    lines = [f"| {title} | Questions | Right page top 1 | Right page top 3 | Exact answer top 1 | Wrong | Missed |",
             "|---|---|---|---|---|---|---|"]
    for name in sorted(groups):
        g = groups[name]
        n = len(g)
        lines.append(
            f"| {name} | {n} | {pct(sum(r['outcome'] == RIGHT for r in g), n)} "
            f"| {pct(sum(r['top3'] for r in g), n)} | {pct(sum(r['exact'] for r in g), n)} "
            f"| {sum(r['outcome'] == WRONG for r in g)} | {sum(r['outcome'] == MISSED for r in g)} |"
        )
    return lines


def returned(record):
    hits = record["hits"]
    if not hits:
        return "no matching piece"
    top = hits[0]
    said = NOT_FOUND if record["verdict"] == NOT_FOUND else "answered"
    others = ", ".join(f"{h.chunk.doc} p.{h.chunk.page} ({h.score:.1f})" for h in hits[1:])
    return (f"{said}; top 1: {top.chunk.doc} p.{top.chunk.page}, score {top.score:.1f}: "
            f"\"{short(top.chunk.text)}\"" + (f"; also: {others}" if others else ""))


def build_report(records, times, table, recommended, n_chunks, index_seconds, docs):
    explain = [r for r in records if not r["trap"]]
    traps = [r for r in records if r["trap"]]
    n, t = len(explain), len(traps)
    count = lambda rs, o: sum(r["outcome"] == o for r in rs)  # noqa: E731
    lines = [
        "# Results",
        "",
        "## Phase 3 baseline: keyword search (BM25), no AI",
        "",
        f"- Documents in one index: {', '.join(docs)} ({n_chunks} pieces)",
        f"- Threshold `BASELINE_MIN_SCORE` = **{config.BASELINE_MIN_SCORE}** "
        f"(sweep recommends {recommended}; rule below)",
        f"- Reading + chunking the PDFs: {index_seconds:.1f} s (once, at upload). "
        f"Average search time per question: **{1000 * sum(times) / len(times):.1f} ms**",
        "",
        "| Measure | Result |",
        "|---|---|",
        f"| Right doc + page, top 1 | {pct(count(explain, RIGHT), n)} |",
        f"| Right doc + page, top 3 | {pct(sum(r['top3'] for r in explain), n)} |",
        f"| Exact answer in top-1 piece (all numbers + key words) | {pct(sum(r['exact'] for r in explain), n)} |",
        f"| Traps correctly \"{NOT_FOUND}\" | {pct(count(traps, REFUSED), t)} |",
        f"| **Wrong: answered from a wrong page** (must be 0 in Phase 4) | **{count(explain, WRONG)}** |",
        f"| **Traps answered** (also wrong) | **{count(traps, TRAP_ANSWERED)}** |",
        f"| Missed: real question but said \"{NOT_FOUND}\" | {count(explain, MISSED)} |",
        "",
        "Compare rows count as right page if the top piece is on either of their two pages. "
        "\"Exact answer\" is strict: a compare answer needs both pages, so it cannot be in one piece.",
        "",
        "### Per document",
        "",
        *group_table(explain, lambda r: r["row"]["doc"], "Document"),
        "",
        "### Per type",
        "",
        *group_table(explain, lambda r: r["row"]["type"], "Type"),
        "",
        "## Threshold",
        "",
        "If the best BM25 score is below the threshold, the answer is \"Not in this document\".",
        "",
        "- **Too high:** real questions get \"Not in this document\" (missed answers).",
        "- **Too low:** trap questions get an answer from some unrelated piece (a wrong answer, worse).",
        "",
        "Rule, fixed before looking at single questions: pick the threshold with the most correct "
        "outcomes (right page + traps refused); on a tie pick the higher one (\"never guess\"). "
        f"With only {n} questions and {t} traps this is a first estimate, not a final value.",
        "",
        "| Threshold | Right | Wrong | Missed | Traps refused | Traps answered | Correct total |",
        "|---|---|---|---|---|---|---|",
    ]
    for thr, c, correct in table:
        mark = " ← chosen" if thr == config.BASELINE_MIN_SCORE else ""
        lines.append(f"| {thr} | {c[RIGHT]} | {c[WRONG]} | {c[MISSED]} | {c[REFUSED]} | {c[TRAP_ANSWERED]} | {correct}{mark} |")
    lines += ["", "## Failed questions", ""]
    failed = [r for r in records if r["outcome"] in (WRONG, MISSED, TRAP_ANSWERED)]
    for r in failed:
        row = r["row"]
        expected = f"\"{NOT_FOUND}\"" if r["trap"] else f"{row['doc']} p.{row['page']}"
        lines.append(f"- **{row['id']}** ({r['outcome']}) expected {expected}: "
                     f"{row['question']}  \n  Returned: {returned(r)}")
    if not failed:
        lines.append("None.")
    not_exact = [r for r in explain if r["outcome"] == RIGHT and not r["exact"]]
    lines += ["", "## Right page, but exact answer not in the top-1 piece", ""]
    for r in not_exact:
        row = r["row"]
        lines.append(f"- **{row['id']}** expected \"{row['expected_answer']}\"  \n  Top-1 piece: \"{short(r['hits'][0].chunk.text, 160)}\"")
    if not not_exact:
        lines.append("None.")
    return "\n".join(lines) + "\n"


def main():
    sys.stdout.reconfigure(errors="replace")
    explain, traps = load_rows("eval/explain_questions.csv"), load_rows("eval/trap_questions.csv")
    needed = sorted({r["doc"] for r in explain + traps})
    missing = [d for d in needed if not (DATA_DIR / d).is_file()]
    if missing:
        print(f"SKIPPED: PDF(s) not in data/raw: {', '.join(missing)} (see PLAN.md Data section)")
        return 0

    start = time.perf_counter()
    pdfs = sorted(p for p in DATA_DIR.iterdir() if p.suffix.lower() == ".pdf")
    chunks = [c for pdf in pdfs for c in chunk_pdf(pdf)]
    index = BM25Index(chunks)
    index_seconds = time.perf_counter() - start

    records, times = run(index, explain, traps)
    table = sweep([(r["row"], r["trap"], r["hits"]) for r in records], SWEEP_STEPS)
    recommended = choose_threshold(table)
    report = build_report(records, times, table, recommended, len(chunks), index_seconds, [p.name for p in pdfs])
    RESULTS.write_text(report, encoding="utf-8")

    explain_r = [r for r in records if not r["trap"]]
    trap_r = [r for r in records if r["trap"]]
    print(f"Pieces: {len(chunks)} from {len(pdfs)} PDFs (read in {index_seconds:.1f} s)")
    print(f"Threshold: {config.BASELINE_MIN_SCORE} (sweep recommends {recommended})")
    print(f"Right page top 1: {pct(sum(r['outcome'] == RIGHT for r in explain_r), len(explain_r))}")
    print(f"Right page top 3: {pct(sum(r['top3'] for r in explain_r), len(explain_r))}")
    print(f"Exact answer top 1: {pct(sum(r['exact'] for r in explain_r), len(explain_r))}")
    print(f"Traps refused: {pct(sum(r['outcome'] == REFUSED for r in trap_r), len(trap_r))}")
    print(f"Wrong (answered, wrong page): {sum(r['outcome'] == WRONG for r in explain_r)}"
          f"  Traps answered: {sum(r['outcome'] == TRAP_ANSWERED for r in trap_r)}"
          f"  Missed: {sum(r['outcome'] == MISSED for r in explain_r)}")
    print(f"Saved {RESULTS.as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
