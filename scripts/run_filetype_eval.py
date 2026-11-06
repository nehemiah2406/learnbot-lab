"""Feature test per file type: 3 questions + 1 trap per type -> eval/results.md.

Run:  .venv\\Scripts\\python scripts\\make_sample_files.py
      .venv\\Scripts\\python scripts\\run_filetype_eval.py --group 1 --dry-run     (fake replies, no AI, writes nothing)
      .venv\\Scripts\\python scripts\\run_filetype_eval.py --group 1 --max-calls 32 --pause 6

Each file is asked through the chat pipeline, inside that file only. The gate per type: wrong 0,
the trap refused, under 10 s, at least 2 of 3 kept: PLAN.md section 3.
"""

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from learnbot import config  # noqa: E402
from learnbot.answer import answer_question  # noqa: E402
from learnbot.eval_check import load_rows  # noqa: E402
from learnbot.evaluate import MISSED, NOT_TESTED, REFUSED, RIGHT, feature_gate, score_answer  # noqa: E402
from learnbot.index import Embedder, Library, VectorStore  # noqa: E402
from learnbot.llm import CallLimitReached, default_chain  # noqa: E402
from learnbot.proof import shown_quote, shown_where  # noqa: E402
from learnbot.report import replace_section  # noqa: E402
from learnbot.search import default_searcher  # noqa: E402

DATA_DIR = Path("data/raw")
RESULTS = Path("eval/results.md")
GROUPS = {"1": (".txt", ".md", ".csv", ".html"), "2": (".docx", ".pptx", ".xlsx")}
QUESTIONS, TRAPS = "eval/filetype_questions.csv", "eval/filetype_traps.csv"


class FakeChain:
    """--dry-run: answers each question with its expected answer + quote, and refuses each trap."""

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


def type_gate(records):
    """The gate of one file type's records."""
    return feature_gate([r["outcome"] for r in records], max(r["ans"].seconds for r in records),
                        config.FILE_TYPE_MIN_KEPT)


def build_report(group, records, calls):
    types = sorted({Path(r["row"]["doc"]).suffix for r in records})
    lines = [f"## File types, group {group} ({', '.join(types)}): 3 questions + 1 trap per type, run once", "",
             "| Type | Right | Wrong | Trap refused | Missed | Not tested | Slowest | Gate |",
             "|---|---|---|---|---|---|---|---|"]
    for kind in types:
        part = [r for r in records if Path(r["row"]["doc"]).suffix == kind]
        count = Counter(r["outcome"] for r in part)
        failures = type_gate(part)
        lines.append(f"| {kind} | {count[RIGHT]}/{sum(not r['trap'] for r in part)} | {count['wrong']} | "
                     f"{count[REFUSED]}/{sum(r['trap'] for r in part)} | {count[MISSED]} | {count[NOT_TESTED]} | "
                     f"{max(r['ans'].seconds for r in part):.1f} s | {'PASS' if not failures else 'NOT PASSED: ' + '; '.join(failures)} |")
    lines += ["", f"{calls} AI calls.", "", "| Id | Outcome | Location | AI | Time | Reason |", "|---|---|---|---|---|---|"]
    for r in records:
        ans = r["ans"]
        where = shown_where(ans.sources[0]) if ans.sources else ""
        lines.append(f"| {r['row']['id']} | {r['outcome']} | {where} | {ans.provider or 'none'} | {ans.seconds:.1f} s "
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
    parser.add_argument("--group", choices=sorted(GROUPS), required=True)
    parser.add_argument("--max-calls", type=int, default=config.MAX_LLM_CALLS_WITHOUT_ASKING)
    parser.add_argument("--pause", type=float, default=0, help="seconds to wait before each item")
    parser.add_argument("--dry-run", action="store_true", help="fake replies, no AI, nothing written")
    args = parser.parse_args()

    wanted = GROUPS[args.group]
    questions = [r for r in load_rows(QUESTIONS) if Path(r["doc"]).suffix in wanted]
    rows = [(r, False) for r in questions] + [(r, True) for r in load_rows(TRAPS) if Path(r["doc"]).suffix in wanted]
    docs = sorted({r["doc"] for r, _ in rows})
    missing = [d for d in docs if not (DATA_DIR / d).is_file()]
    if missing:
        print(f"SKIPPED: not in data/raw: {', '.join(missing)} (run scripts/make_sample_files.py)")
        return 0
    chain = FakeChain(questions) if args.dry_run else default_chain()
    if not args.dry_run:
        chain.max_calls = args.max_calls  # checked before every real call: Gemini first, Groq as backup
        if not chain.providers:
            print("No AI key set (GEMINI_API_KEY / GROQ_API_KEY in .env). Nothing to run.")
            return 1
    searcher = default_searcher(Library.load([DATA_DIR / d for d in docs], VectorStore(Embedder())))

    records = []
    try:
        for row, trap in sorted(rows, key=lambda item: (item[0]["doc"], item[1])):
            if not args.dry_run:
                time.sleep(args.pause)  # stay under the free per-minute limits
            ans = answer_question(row["question"], searcher.for_document(row["doc"]), chain)
            outcome, reason = score_answer(row, trap, ans)
            records.append({"row": row, "trap": trap, "ans": ans, "outcome": outcome, "reason": reason})
            print(f"{row['id']}: {outcome} [{ans.seconds:.1f} s; {ans.attempts or ans.detail or '-'}] {reason or ans.reason}")
            print(f"   {ans.text}")
            for s in ans.sources:
                print(f"   {s['doc']}, {shown_where(s)}: {shown_quote(s)}")
    except CallLimitReached:
        print(f"STOPPED: call limit {args.max_calls} reached ({chain.calls} real AI calls). "
              "These numbers are not a valid result; results.md was not written.")
        return 2

    failed = {}
    for kind in wanted:
        part = [r for r in records if Path(r["row"]["doc"]).suffix == kind]
        failed[kind] = type_gate(part)
        print(f"{kind}: " + ("GATE: PASS" if not failed[kind] else "GATE: NOT PASSED: " + "; ".join(failed[kind])))
    print(f"Real AI calls this run: {chain.calls}")
    if not args.dry_run:
        replace_section(RESULTS, f"filetypes-group{args.group}", build_report(args.group, records, chain.calls))
        print(f"Saved {RESULTS.as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
