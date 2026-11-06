"""Feature test for the upload self-test: 5 questions + 2 normal traps -> eval/results.md.

Run:  .venv\\Scripts\\python scripts\\run_selftest_eval.py coast_pilot4_ch1.pdf --max-calls 6 --pause 5

The 5 questions are the ones the self-test made from the file. If the file was uploaded, its
saved result is used (no AI calls); otherwise the test runs now and is saved, as an upload does.
Traps are asked through chat on the same file. Normal traps (not in the file) are in the gate.
Hard traps (all their words are in the file, their answer is not) are only reported: PLAN.md
section 0. The gate: PLAN.md section 3.
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from learnbot import config  # noqa: E402
from learnbot.answer import answer_question  # noqa: E402
from learnbot.eval_check import load_rows  # noqa: E402
from learnbot.evaluate import MISSED, NOT_TESTED, RIGHT, WRONG, feature_gate, score_answer  # noqa: E402
from learnbot.index import Embedder, Library, VectorStore, file_hash  # noqa: E402
from learnbot.llm import CallLimitReached, default_chain  # noqa: E402
from learnbot.report import replace_section  # noqa: E402
from learnbot.search import default_searcher  # noqa: E402
from learnbot.selftest import BUSY, DIFFERENT, SAME, self_test_once  # noqa: E402

DATA_DIR = Path("data/raw")
RESULTS = Path("eval/results.md")
NORMAL_TRAPS = "eval/selftest_normal_traps.csv"
HARD_TRAPS = "eval/selftest_traps.csv"


def outcome(result):
    """Gate outcome of one self-test question."""
    return {SAME: RIGHT, DIFFERENT: WRONG, BUSY: NOT_TESTED}.get(result, MISSED)


def build_report(doc, test, traps, failures, calls):
    asked = [t["item"].seconds for t in traps if t["item"] is not None]
    slowest = max([q["seconds"] for q in test.questions] + asked)
    lines = [
        f"## Day 2: upload self-test under the new gate ({doc}, {test.wanted} questions + "
        f"{sum(not t['hard'] for t in traps)} normal traps; hard traps reported, not a gate)",
        "",
        f"**Gate: {'PASS' if not failures else 'NOT PASSED: ' + '; '.join(failures)}**",
        "",
        f"Self-test verdict: {test.verdict}. Passed {test.passed}/{test.wanted}; {test.dropped} flashcards dropped "
        f"while making the test; slowest {slowest:.1f} s; {calls} AI calls in this step"
        + (" (self-test result saved by the upload, so its AI calls were made there)." if test.from_saved else "."),
        "",
        "| Question | Expected (p.) | Chat's answer (p.) | Result | Time |",
        "|---|---|---|---|---|",
    ]
    for q in test.questions:
        lines.append(f"| {q['question']} | {q['expected']} (p.{q['page']}) | {q['answer']} (p.{q['answer_page']}) "
                     f"| {q['result']} | {q['seconds']:.1f} s |")
    lines += ["", "| Trap | Kind | Outcome | What was shown | Why | Time |", "|---|---|---|---|---|---|"]
    for t in traps:
        item, kind = t["item"], "hard (not a gate)" if t["hard"] else "normal"
        if item is None:
            lines.append(f"| {t['row']['question']} | {kind} | not asked (call limit) |  |  |  |")
            continue
        lines.append(f"| {t['row']['question']} | {kind} | {t['outcome']} | {item.text} | {item.reason or t['reason']} "
                     f"| {item.seconds:.1f} s |")
    return "\n".join(lines)


def ask_trap(row, hard, searcher, chain, pause):
    time.sleep(pause)  # stay under the free per-minute limits
    item = answer_question(row["question"], searcher, chain)
    result, reason = score_answer(row, True, item)
    print(f"{row['id']}: {result}{' (hard)' if hard else ''} [{item.seconds:.1f} s; "
          f"{item.attempts or item.detail or '-'}] {item.text[:150]} {item.reason}")
    return {"row": row, "hard": hard, "item": item, "outcome": result, "reason": reason}


def main():
    sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("document")
    parser.add_argument("--max-calls", type=int, default=config.MAX_LLM_CALLS_WITHOUT_ASKING)
    parser.add_argument("--pause", type=float, default=0, help="seconds to wait before each trap")
    args = parser.parse_args()

    path = DATA_DIR / args.document
    if not path.is_file():
        print(f"SKIPPED: {args.document} not in data/raw (see PLAN.md Data section)")
        return 0
    searcher = default_searcher(Library.load([path], VectorStore(Embedder())))
    searcher.search("warm up")  # loads the models now, so no item pays for the loading
    chain = default_chain()
    chain.max_calls = args.max_calls  # checked before every real call
    if not chain.providers:
        print("No AI key set (GEMINI_API_KEY / GROQ_API_KEY in .env). Nothing to run.")
        return 1

    try:
        test = self_test_once(args.document, file_hash(path), searcher, chain)
        print(test.message + (" (saved result, no AI calls)" if test.from_saved else ""))
        for q in test.questions:
            print(f"[{q['result']}] {q['seconds']:.1f} s p.{q['page']} {q['question']}\n"
                  f"   card: {q['expected']}\n   chat: {q['answer']} (p.{q['answer_page']})")
        traps = []
        for row in load_rows(NORMAL_TRAPS):
            traps.append(ask_trap(row, False, searcher, chain, args.pause))
        for row in load_rows(HARD_TRAPS):
            try:
                traps.append(ask_trap(row, True, searcher, chain, args.pause))
            except CallLimitReached:  # hard traps are only reported, so this run stays valid
                traps.append({"row": row, "hard": True, "item": None, "outcome": "not asked", "reason": ""})
                print(f"{row['id']}: not asked (call limit)")
    except CallLimitReached:
        print(f"STOPPED: call limit {args.max_calls} reached ({chain.calls} real AI calls). "
              "These numbers are not a valid result; results.md was not written.")
        return 2

    outcomes = [outcome(q["result"]) for q in test.questions] + [t["outcome"] for t in traps if not t["hard"]]
    gated = [t["item"].seconds for t in traps if not t["hard"]]
    slowest = max([q["seconds"] for q in test.questions] + gated)
    failures = feature_gate(outcomes, slowest)
    print(f"Real AI calls this run: {chain.calls}")
    print("GATE: PASS" if not failures else "GATE: NOT PASSED: " + "; ".join(failures))
    replace_section(RESULTS, "day2-selftest-new-gate", build_report(args.document, test, traps, failures, chain.calls))
    print(f"Saved {RESULTS.as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
