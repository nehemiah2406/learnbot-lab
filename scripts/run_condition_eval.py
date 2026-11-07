"""Feature test for the conditions rule: 5 questions + 2 traps -> eval/results.md.

Run:  .venv\\Scripts\\python scripts\\run_condition_eval.py --dry-run     (fake short answers, no AI, writes nothing)
      .venv\\Scripts\\python scripts\\run_condition_eval.py --max-calls 14 --pause 6

Every question's quote has a condition. An answer shown without the condition's words (the
condition column) counts as wrong. The gate: PLAN.md section 3.
"""

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from learnbot.answer import ANSWERED, answer_is_quote, answer_question  # noqa: E402
from learnbot.baseline import tokenize  # noqa: E402
from learnbot.eval_check import load_rows  # noqa: E402
from learnbot.evaluate import MISSED, NOT_TESTED, REFUSED, RIGHT, WRONG, feature_gate, score_answer  # noqa: E402
from learnbot.index import Embedder, Library, VectorStore  # noqa: E402
from learnbot.llm import CallLimitReached, default_chain  # noqa: E402
from learnbot.proof import shown_quote, shown_where  # noqa: E402
from learnbot.report import replace_section  # noqa: E402
from learnbot.search import default_searcher  # noqa: E402

DATA_DIR = Path("data/raw")
RESULTS = Path("eval/results.md")
QUESTIONS, TRAPS = "eval/condition_questions.csv", "eval/condition_traps.csv"


class FakeChain:
    """--dry-run: gives each question its short expected answer, and refuses each trap."""

    calls = 0
    last_attempts = ()

    def __init__(self, questions):
        self.questions = questions

    def ask(self, prompt, budget_s=None):
        for row in self.questions:
            if f"Question: {row['question']}" in prompt:
                return json.dumps({"found": True, "answer": row["expected_answer"], "sources": [
                    {"doc": row["doc"], "page": int(row["page"]), "quote": row["source_quote"]}]}), "fake", False
        return '{"found": false}', "fake", False


def score_condition(row, trap, ans):
    """score_answer, and an answer shown without its condition's words is wrong."""
    outcome, reason = score_answer(row, trap, ans)
    if not trap and ans.status == ANSWERED and outcome == RIGHT:
        shown = set(tokenize(ans.text + " " + row["question"]))
        missing = [w for w in row["condition"].split(";") if w.lower() not in shown]
        if missing:
            return WRONG, f"condition dropped: {', '.join(missing)}"
    return outcome, reason


def build_report(records, calls, failures):
    real = [r for r in records if not r["trap"]]
    count = Counter(r["outcome"] for r in records)
    traps = len(records) - len(real)
    lines = [
        f"## Conditions rule ({len(real)} questions + {traps} traps, run once)", "",
        f"**Gate: {'PASS' if not failures else 'NOT PASSED: ' + '; '.join(failures)}**", "",
        "| Right | Wrong | Traps refused | Missed | Not tested | Slowest | AI calls |", "|---|---|---|---|---|---|---|",
        f"| {count[RIGHT]}/{len(real)} | {count[WRONG]} | {count[REFUSED]}/{traps} | {count[MISSED]} | {count[NOT_TESTED]} "
        f"| {max(r['ans'].seconds for r in records):.1f} s | {calls} |", "",
        "| Id | Outcome | Exact sentence shown? | AI | Time | Reason |", "|---|---|---|---|---|---|",
    ]
    for r in records:
        ans = r["ans"]
        sentence = "yes" if ans.sources and answer_is_quote(ans) else ""
        lines.append(f"| {r['row']['id']} | {r['outcome']} | {sentence} | {ans.provider or 'none'} | {ans.seconds:.1f} s "
                     f"| {r['reason'] or ans.reason} |")
    lines += ["", "### Answers shown, for a person to read", ""]
    for r in records:
        for s in r["ans"].sources:
            lines.append(f"- **{r['row']['id']}** {r['row']['question']}  \n  {r['ans'].text}  \n"
                         f"  {s['doc']}, {shown_where(s)}: \"{shown_quote(s)}\"")
    return "\n".join(lines)


def main():
    sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-calls", type=int, default=14)
    parser.add_argument("--pause", type=float, default=0, help="seconds to wait before each item")
    parser.add_argument("--dry-run", action="store_true", help="fake replies, no AI, nothing written")
    args = parser.parse_args()

    questions = load_rows(QUESTIONS)
    rows = [(r, False) for r in questions] + [(r, True) for r in load_rows(TRAPS)]
    docs = sorted({r["doc"] for r, _ in rows})
    chain = FakeChain(questions) if args.dry_run else default_chain()
    if not args.dry_run:
        chain.max_calls = args.max_calls  # checked before every real call: Gemini first, Groq as backup
    searcher = default_searcher(Library.load([DATA_DIR / d for d in docs], VectorStore(Embedder())))

    records = []
    try:
        for row, trap in rows:
            if not args.dry_run:
                time.sleep(args.pause)  # stay under the free per-minute limits
            ans = answer_question(row["question"], searcher.for_document(row["doc"]), chain)
            outcome, reason = score_condition(row, trap, ans)
            records.append({"row": row, "trap": trap, "ans": ans, "outcome": outcome, "reason": reason})
            print(f"{row['id']}: {outcome} [{ans.seconds:.1f} s; {ans.attempts or ans.detail or '-'}] {reason or ans.reason}")
            print(f"   {ans.text}")
    except CallLimitReached:
        print(f"STOPPED: call limit {args.max_calls} reached ({chain.calls} real AI calls). "
              "These numbers are not a valid result; results.md was not written.")
        return 2
    failures = feature_gate([r["outcome"] for r in records], max(r["ans"].seconds for r in records))
    print(f"Real AI calls this run: {chain.calls}")
    print(("DRY RUN " if args.dry_run else "") + ("GATE: PASS" if not failures else "GATE: NOT PASSED: " + "; ".join(failures)))
    if not args.dry_run:
        replace_section(RESULTS, "conditions-rule", build_report(records, chain.calls, failures))
        print(f"Saved {RESULTS.as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
