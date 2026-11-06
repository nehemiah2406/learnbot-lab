"""Feature test for research mode: 5 questions + 2 traps -> eval/results.md.

Run:  .venv\\Scripts\\python scripts\\run_research_eval.py --max-calls 14 --pause 5

At most 7 Tavily searches and 2 AI calls per item. Web text changes, so these numbers are
for this run only. Every answer and link is printed for a person to read.
"""

import argparse
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from learnbot.eval_check import load_rows  # noqa: E402
from learnbot.evaluate import MISSED, NOT_TESTED, REFUSED, RIGHT, WRONG, feature_gate, score_web  # noqa: E402
from learnbot.llm import CallLimitReached, default_chain  # noqa: E402
from learnbot.report import replace_section  # noqa: E402
from learnbot.research import research, show  # noqa: E402

RESULTS = Path("eval/results.md")
QUESTIONS, TRAPS = "eval/research_questions.csv", "eval/research_traps.csv"


def build_report(records, calls, failures):
    count = Counter(r["outcome"] for r in records)
    real = [r for r in records if not r["trap"]]
    slowest = max(r["ans"].seconds for r in records)
    lines = [
        f"## Research mode ({len(real)} questions + {len(records) - len(real)} traps)",
        "",
        f"**Gate: {'PASS' if not failures else 'NOT PASSED: ' + '; '.join(failures)}**",
        "",
        "Web text changes, so these numbers are for this run only. \"Wrong\" means the numbers differ from "
        "the expected answer, or a trap got an answer.",
        "",
        "| Right | Wrong | Traps refused | Missed | Not tested | Slowest | AI calls |",
        "|---|---|---|---|---|---|---|",
        f"| {count[RIGHT]}/{len(real)} | {count[WRONG]} | {count[REFUSED]}/{len(records) - len(real)} | {count[MISSED]} "
        f"| {count[NOT_TESTED]} | {slowest:.1f} s | {calls} |",
        "",
        "| Id | Outcome | AI | Time | Reason |",
        "|---|---|---|---|---|",
    ]
    for r in records:
        ans = r["ans"]
        lines.append(f"| {r['row']['id']} | {r['outcome']} | {ans.provider or 'none'} | {ans.seconds:.1f} s "
                     f"| {r['reason'] or ans.reason} |")
    lines += ["", "### Answers shown, for a person to read", ""]
    for r in records:
        if r["ans"].sources:
            lines += [f"- **{r['row']['id']}** {r['row']['question']}", "  " + show(r["ans"]).replace("\n", "  \n  ")]
    return "\n".join(lines)


def main():
    sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-calls", type=int, default=14)
    parser.add_argument("--pause", type=float, default=0, help="seconds to wait before each item")
    args = parser.parse_args()
    chain = default_chain()
    chain.max_calls = args.max_calls  # checked before every real call
    if not chain.providers:
        print("No AI key set (GEMINI_API_KEY / GROQ_API_KEY in .env). Nothing to run.")
        return 1

    rows = [(r, False) for r in load_rows(QUESTIONS)] + [(r, True) for r in load_rows(TRAPS)]
    records = []
    try:
        for row, trap in rows:
            time.sleep(args.pause)  # stay under the free per-minute limits
            ans = research(row["question"], chain)
            outcome, reason = score_web(row, trap, ans)
            records.append({"row": row, "trap": trap, "ans": ans, "outcome": outcome, "reason": reason})
            print(f"{row['id']}: {outcome} [{ans.seconds:.1f} s; {ans.attempts or ans.detail or '-'}] {reason or ans.reason}")
            print("   " + show(ans).replace("\n", "\n   "))
    except CallLimitReached:
        print(f"STOPPED: call limit {args.max_calls} reached ({chain.calls} real AI calls). "
              "These numbers are not a valid result; results.md was not written.")
        return 2

    failures = feature_gate([r["outcome"] for r in records], max(r["ans"].seconds for r in records))
    print(f"Real AI calls this run: {chain.calls}")
    print("GATE: PASS" if not failures else "GATE: NOT PASSED: " + "; ".join(failures))
    replace_section(RESULTS, "research", build_report(records, chain.calls, failures))
    print(f"Saved {RESULTS.as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
