"""Feature test for quiz questions or flashcards: 5 topics + 2 traps -> eval/results.md.

Run:  .venv\\Scripts\\python scripts\\run_study_eval.py quiz --max-calls 17 --pause 5
      .venv\\Scripts\\python scripts\\run_study_eval.py quiz --dry-run    (count AI calls, call nothing)

Topics are in the eval format (the question column holds the topic), so scripts/check_eval.py
checks them. Each topic asks for one item. Scoring: same as chat answers, with the item's right answer as
the answer. The gate: PLAN.md section 3. Every kept item is printed in the report for a person to read.
"""

import argparse
import importlib
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from run_answer_eval import warm_up  # noqa: E402

from learnbot import config  # noqa: E402
from learnbot.eval_check import load_rows  # noqa: E402
from learnbot.evaluate import MISSED, NOT_TESTED, RIGHT, feature_gate, score_answer  # noqa: E402
from learnbot.index import Embedder, Library, VectorStore  # noqa: E402
from learnbot.llm import CallLimitReached, default_chain  # noqa: E402
from learnbot.proof import shown_quote  # noqa: E402
from learnbot.report import replace_section  # noqa: E402
from learnbot.search import default_searcher  # noqa: E402

DATA_DIR = Path("data/raw")
RESULTS = Path("eval/results.md")
# feature: (module, function that makes one item, topics, traps, name)
FEATURES = {
    "quiz": ("learnbot.quiz", "make_question", "eval/quiz_questions.csv", "eval/quiz_traps.csv", "Quiz"),
    "cards": ("learnbot.flashcards", "make_card", "eval/flashcard_questions.csv", "eval/flashcard_traps.csv",
              "Flashcards"),
}


def item_lines(item):
    """A kept item for a person to read: question, options (* = the right one), source."""
    lines = [f"  Q: {item.question}"]
    if item.options:
        lines += [f"  {'*' if i == item.correct else '-'} {option}" for i, option in enumerate(item.options)]
    else:
        lines.append(f"  A: {item.text}")
    s = item.sources[0]
    lines.append(f"  Source: {s['doc']} p.{s['page']} ({s['title'][:60]}); quote: \"{shown_quote(s)}\"")
    return lines


def build_report(name, records, chain, failures):
    real = [r for r in records if not r["trap"]]
    count = Counter(r["outcome"] for r in records)
    kept = [r for r in real if r["item"].status == "answered"]
    traps = [r for r in records if r["trap"]]
    refused = sum(r["item"].status == "not_found" for r in traps)
    slowest = max(r["item"].seconds for r in records)
    lines = [
        f"## Day 1: {name} ({len(real)} topics + {len(traps)} traps)",
        "",
        f"**Gate: {'PASS' if not failures else 'NOT PASSED: ' + '; '.join(failures)}**",
        "",
        "| Kept | Right page (not a gate) | Wrong | Traps refused | Missed (dropped) | Not tested | Slowest | AI calls |",
        "|---|---|---|---|---|---|---|---|",
        f"| {len(kept)}/{len(real)} | {count[RIGHT]}/{len(real)} | {count['wrong']} | {refused}/{len(traps)} "
        f"| {count[MISSED]} | {count[NOT_TESTED]} | {slowest:.1f} s | {chain.calls} |",
        "",
        "| Id | Outcome | AI that answered | Time | Reason |",
        "|---|---|---|---|---|",
    ]
    for r in records:
        item = r["item"]
        lines.append(f"| {r['row']['id']} | {r['outcome']} | {item.provider or 'none'} | {item.seconds:.1f} s "
                     f"| {r['reason'] or item.reason or ''} |")
    lines += ["", "### Kept items, for a person to read", ""]
    for r in records:
        if r["item"].status == "answered":
            lines += [f"- **{r['row']['id']}** ({r['outcome']}), topic: {r['row']['question']}", *item_lines(r["item"])]
    return "\n".join(lines)


def main():
    sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("feature", choices=sorted(FEATURES))
    parser.add_argument("--max-calls", type=int, default=config.MAX_LLM_CALLS_WITHOUT_ASKING)
    parser.add_argument("--pause", type=float, default=0, help="seconds to wait before each item")
    parser.add_argument("--dry-run", action="store_true", help="only check that everything loads; call no AI")
    parser.add_argument("--no-warm-up", action="store_true", help="skip the 1-call check of the main AI")
    parser.add_argument("--section", help="results.md section to write (default: the feature's own, day1-...)")
    parser.add_argument("--label", default="", help="added to the report's name")
    args = parser.parse_args()

    module, function, questions, traps, name = FEATURES[args.feature]
    make_one = getattr(importlib.import_module(module), function)
    rows = [(r, False) for r in load_rows(questions)] + [(r, True) for r in load_rows(traps)]
    missing = sorted({r["doc"] for r, _ in rows if not (DATA_DIR / r["doc"]).is_file()})
    if missing:
        print(f"SKIPPED: PDF(s) not in data/raw: {', '.join(missing)} (see PLAN.md Data section)")
        return 0
    pdfs = sorted(p for p in DATA_DIR.iterdir() if p.suffix.lower() == ".pdf")
    searcher = default_searcher(Library.load(pdfs, VectorStore(Embedder())))
    searcher.search("warm up")  # loads the models now, so no item pays for the loading
    chain = default_chain()
    chain.max_calls = args.max_calls  # checked before every real call
    if not chain.providers:
        print("No AI key set (GEMINI_API_KEY / GROQ_API_KEY in .env). Nothing to run.")
        return 1
    print(f"{name}: {len(rows)} items; at most {2 * len(rows) + 1} AI calls; call limit {args.max_calls}")
    if args.dry_run:
        return 0

    records = []
    try:
        if not args.no_warm_up:
            ok, status = warm_up(chain)
            print(f"Warm-up call: {status}" + ("" if ok else " (main AI switched off for now; the fallback answers)"))
        for row, trap in rows:
            time.sleep(args.pause)  # stay under the free per-minute limits
            item = make_one(row["question"], searcher.for_document(row["doc"]), chain)
            outcome, reason = score_answer(row, trap, item)
            records.append({"row": row, "trap": trap, "item": item, "outcome": outcome, "reason": reason})
            print(f"{row['id']}: {outcome} [{item.seconds:.1f} s; {item.attempts or item.detail or '-'}] "
                  f"{reason or item.reason}")
            if item.status == "answered":
                print("\n".join(item_lines(item)))
    except CallLimitReached:
        print(f"STOPPED: call limit {args.max_calls} reached ({chain.calls} real AI calls). "
              "These numbers are not a valid result; results.md was not written.")
        return 2

    slowest = max(r["item"].seconds for r in records)
    failures = feature_gate([r["outcome"] for r in records], slowest)
    print(f"Real AI calls this run: {chain.calls}")
    print("GATE: PASS" if not failures else "GATE: NOT PASSED: " + "; ".join(failures))
    replace_section(RESULTS, args.section or f"day1-{args.feature}", build_report(name + args.label, records, chain, failures))
    print(f"Saved {RESULTS.as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
