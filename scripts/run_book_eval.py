"""Feature test for the book maker: 5 topics + 2 normal traps -> eval/results.md.

Run:  .venv\\Scripts\\python scripts\\run_book_eval.py --dry-run     (fake replies, no AI, writes nothing)
      .venv\\Scripts\\python scripts\\run_book_eval.py --max-calls 15 --pause 6

Right: the chapter holds the expected fact. Traps: the chapter has no facts. Hard traps are only
reported: PLAN.md section 0. Every fact kept is printed, for a person to read: a fact that a person
finds false counts as wrong. The gate: PLAN.md section 3.
"""

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from learnbot import config  # noqa: E402
from learnbot.answer import AI_BUSY_STATUS, ANSWERED  # noqa: E402
from learnbot.book import make_chapter  # noqa: E402
from learnbot.eval_check import load_rows  # noqa: E402
from learnbot.evaluate import (  # noqa: E402
    CORRECT_OTHER, MISSED, NOT_TESTED, REFUSED, RIGHT, TRAP_ANSWERED, feature_gate, score_answer,
)
from learnbot.index import Embedder, Library, VectorStore  # noqa: E402
from learnbot.llm import CallLimitReached, default_chain  # noqa: E402
from learnbot.proof import shown_quote  # noqa: E402
from learnbot.report import replace_section  # noqa: E402
from learnbot.search import default_searcher  # noqa: E402

DATA_DIR = Path("data/raw")
RESULTS = Path("eval/results.md")
QUESTIONS, TRAPS, HARD_TRAPS = "eval/book_questions.csv", "eval/book_traps.csv", "eval/book_hard_traps.csv"


class FakeChain:
    """--dry-run: writes each topic's expected fact, and finds nothing for a trap."""

    calls = 0
    last_attempts = ()

    def __init__(self, rows):
        self.rows = rows

    def ask(self, prompt, budget_s=None):
        for row in self.rows:
            if f"Topic: {row['question']}\n" in prompt:
                fact = {"question": f"What does the document say about {row['question']}?",
                        "answer": row["expected_answer"],
                        "source": {"doc": row["doc"], "page": int(row["page"]), "quote": row["source_quote"]}}
                return json.dumps({"found": True, "facts": [fact]}), "fake", False
        return '{"found": false}', "fake", False


def score_chapter(row, is_trap, chapter):
    """(outcome, reason). A trap must have no facts; a topic must hold its expected fact."""
    if chapter.status == AI_BUSY_STATUS:
        return NOT_TESTED, chapter.detail
    if is_trap:
        return (TRAP_ANSWERED, f"{len(chapter.facts)} facts") if chapter.facts else (REFUSED, "")
    if not chapter.facts:
        return MISSED, chapter.reason
    if any(score_answer(row, False, fact)[0] in (RIGHT, CORRECT_OTHER) for fact in chapter.facts):
        return RIGHT, ""
    return MISSED, "expected fact not in the chapter"


def fact_lines(chapter):
    lines = []
    for fact in chapter.facts:
        s = fact.sources[0]
        lines += [f"  Q: {fact.question}", f"  A: {fact.text}", f"  {s['doc']} p.{s['page']}: \"{shown_quote(s)}\""]
    return lines


def build_report(records, calls, failures, label=""):
    gated = [r for r in records if not r["hard"]]
    real = [r for r in gated if not r["trap"]]
    count = Counter(r["outcome"] for r in gated)
    traps = len(gated) - len(real)
    slowest = max(r["chapter"].seconds for r in gated)
    lines = [
        f"## Day 3: book maker{label} ({len(real)} topics + {traps} normal traps, run once; hard traps reported, not a gate)",
        "",
        f"**Gate: {'PASS' if not failures else 'NOT PASSED: ' + '; '.join(failures)}**",
        "",
        "| Right | Wrong | Traps refused | Missed | Not tested | Slowest chapter | AI calls |",
        "|---|---|---|---|---|---|---|",
        f"| {count[RIGHT]}/{len(real)} | {count['wrong']} | {count[REFUSED]}/{traps} | {count[MISSED]} "
        f"| {count[NOT_TESTED]} | {slowest:.1f} s | {calls} |",
        "",
        "| Id | Kind | Outcome | Facts kept | Dropped | AI | Time | Reason |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in records:
        c = r["chapter"]
        kind = "hard trap" if r["hard"] else "trap" if r["trap"] else "topic"
        lines.append(f"| {r['row']['id']} | {kind} | {r['outcome']} | {len(c.facts)} | {c.dropped} | {c.provider or 'none'} "
                     f"| {c.seconds:.1f} s | {r['reason'] or c.reason} |")
    lines += ["", "### Facts kept, for a person to read", ""]
    for r in records:
        if r["chapter"].facts:
            lines += [f"- **{r['row']['id']}** topic: {r['row']['question']}", *fact_lines(r["chapter"])]
    return "\n".join(lines)


def main():
    sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-calls", type=int, default=15)
    parser.add_argument("--pause", type=float, default=0, help="seconds to wait before each chapter")
    parser.add_argument("--dry-run", action="store_true", help="fake replies, no AI, nothing written")
    parser.add_argument("--questions", default=QUESTIONS)
    parser.add_argument("--traps", default=TRAPS)
    parser.add_argument("--section", default="day3-book", help="results.md section to write")
    parser.add_argument("--label", default="", help="added to the report's title")
    args = parser.parse_args()

    questions, traps, hard = load_rows(args.questions), load_rows(args.traps), load_rows(HARD_TRAPS)
    rows = [(r, False, False) for r in questions] + [(r, True, False) for r in traps] + [(r, True, True) for r in hard]
    docs = sorted({r["doc"] for r, _, _ in rows})
    missing = [d for d in docs if not (DATA_DIR / d).is_file()]
    if missing:
        print(f"SKIPPED: PDF(s) not in data/raw: {', '.join(missing)} (see PLAN.md Data section)")
        return 0
    chain = FakeChain(questions) if args.dry_run else default_chain()
    if not args.dry_run:
        chain.max_calls = args.max_calls  # checked before every real call: Gemini first, Groq as backup
        if not chain.providers:
            print("No AI key set (GEMINI_API_KEY / GROQ_API_KEY in .env). Nothing to run.")
            return 1
    searcher = default_searcher(Library.load([DATA_DIR / d for d in docs], VectorStore(Embedder())))

    records = []
    for row, trap, is_hard in rows:
        if not args.dry_run:
            time.sleep(args.pause)  # stay under the free per-minute limits
        try:
            chapter = make_chapter(row["question"], searcher.for_document(row["doc"]), chain)
        except CallLimitReached:
            if is_hard:  # hard traps are only reported, so the run stays valid
                print(f"{row['id']}: not asked (call limit)")
                continue
            print(f"STOPPED: call limit {args.max_calls} reached ({chain.calls} real AI calls). "
                  "These numbers are not a valid result; results.md was not written.")
            return 2
        outcome, reason = score_chapter(row, trap, chapter)
        records.append({"row": row, "trap": trap, "hard": is_hard, "chapter": chapter, "outcome": outcome, "reason": reason})
        print(f"{row['id']}: {outcome}{' (hard)' if is_hard else ''} [{chapter.seconds:.1f} s; "
              f"{chapter.attempts or chapter.detail or '-'}] {len(chapter.facts)} facts, {chapter.dropped} dropped "
              f"{reason or chapter.reason}")
        print("\n".join(fact_lines(chapter)) or f"  {chapter.text}")

    gated = [r for r in records if not r["hard"]]
    failures = feature_gate([r["outcome"] for r in gated], max(r["chapter"].seconds for r in gated))
    print(f"Real AI calls this run: {chain.calls}")
    print(("DRY RUN " if args.dry_run else "") + ("GATE: PASS" if not failures else "GATE: NOT PASSED: " + "; ".join(failures)))
    if not args.dry_run:
        replace_section(RESULTS, args.section, build_report(records, chain.calls, failures, args.label))
        print(f"Saved {RESULTS.as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
