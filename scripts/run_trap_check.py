"""Ask chat only the hard traps (all the words are in the document, the answer is not).

Run:  .venv\\Scripts\\python scripts\\run_trap_check.py --max-calls 14

Each trap is asked inside its own document. At most 2 AI calls per trap. A trap that gets an
answer is printed with its quote, for a person to read. The numbers go to eval/results.md.
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from learnbot.answer import answer_question  # noqa: E402
from learnbot.eval_check import load_rows  # noqa: E402
from learnbot.evaluate import NOT_TESTED, REFUSED, TRAP_ANSWERED, score_answer  # noqa: E402
from learnbot.index import Embedder, Library, VectorStore  # noqa: E402
from learnbot.llm import CallLimitReached, default_chain  # noqa: E402
from learnbot.proof import shown_quote  # noqa: E402
from learnbot.report import replace_section  # noqa: E402
from learnbot.search import default_searcher  # noqa: E402

DATA_DIR = Path("data/raw")
RESULTS = Path("eval/results.md")
TRAP_FILES = ["eval/selftest_traps.csv", "eval/hard_traps.csv"]


def build_report(records, calls, title):
    count = [r["outcome"] for r in records]
    lines = [
        title,
        "",
        f"Refused {count.count(REFUSED)}/{len(records)}; answered {count.count(TRAP_ANSWERED)}; "
        f"not tested (AI busy) {count.count(NOT_TESTED)}; {calls} AI calls; "
        f"slowest {max(r['item'].seconds for r in records):.1f} s.",
        "",
        "| Trap | Question | Outcome | Why refused | AI calls | Time |",
        "|---|---|---|---|---|---|",
    ]
    for r in records:
        item = r["item"]
        lines.append(f"| {r['row']['id']} | {r['row']['question']} | {r['outcome']} | {item.reason} "
                     f"| {item.attempts or item.detail or 'none'} | {item.seconds:.1f} s |")
    answered = [r for r in records if r["outcome"] == TRAP_ANSWERED]
    if answered:
        lines += ["", "### Traps that got an answer", ""]
    for r in answered:
        s = r["item"].sources[0]
        lines.append(f"- **{r['row']['id']}**: \"{r['item'].text}\" from {s['doc']} p.{s['page']}; "
                     f"quote: \"{shown_quote(s)}\"")
    return "\n".join(lines)


def main():
    sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-calls", type=int, default=14)
    parser.add_argument("--traps", nargs="+", default=TRAP_FILES, help="trap CSV files")
    parser.add_argument("--section", default="day2-hard-traps", help="results.md section to write")
    parser.add_argument("--title", default="## Hard traps in chat, with the \"exact thing\" rule (prompt version 5)")
    parser.add_argument("--provider", help="ask only this AI (gemini or groq)")
    parser.add_argument("--pause", type=float, default=0, help="seconds to wait before each trap")
    args = parser.parse_args()

    rows = [r for name in args.traps for r in load_rows(name)]
    docs = sorted({r["doc"] for r in rows})
    missing = [d for d in docs if not (DATA_DIR / d).is_file()]
    if missing:
        print(f"SKIPPED: PDF(s) not in data/raw: {', '.join(missing)} (see PLAN.md Data section)")
        return 0
    searcher = default_searcher(Library.load([DATA_DIR / d for d in docs], VectorStore(Embedder())))
    chain = default_chain()
    chain.max_calls = args.max_calls  # checked before every real call
    if args.provider:
        chain.providers = [p for p in chain.providers if p.name == args.provider]
    if not chain.providers:
        print("No AI key set (GEMINI_API_KEY / GROQ_API_KEY in .env). Nothing to run.")
        return 1

    records = []
    try:
        for row in rows:
            time.sleep(args.pause)  # stay under the free per-minute limits
            item = answer_question(row["question"], searcher.for_document(row["doc"]), chain)
            outcome, _ = score_answer(row, True, item)
            records.append({"row": row, "item": item, "outcome": outcome})
            print(f"{row['id']}: {outcome} [{item.seconds:.1f} s; {item.attempts or item.detail or '-'}] {item.reason}")
            if outcome == TRAP_ANSWERED:
                print(f"   Shown: {item.text}\n   Quote: {shown_quote(item.sources[0])} (p.{item.sources[0]['page']})")
    except CallLimitReached:
        print(f"STOPPED: call limit {args.max_calls} reached ({chain.calls} real AI calls). "
              "These numbers are not a valid result; results.md was not written.")
        return 2
    print(f"Real AI calls this run: {chain.calls}")
    replace_section(RESULTS, args.section, build_report(records, chain.calls, args.title))
    print(f"Saved {RESULTS.as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
