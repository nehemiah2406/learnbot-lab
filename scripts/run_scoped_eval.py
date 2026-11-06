"""Feature test for the notebook or reading mode: 5 questions + 2 traps -> eval/results.md.

Run:  .venv\\Scripts\\python scripts\\run_scoped_eval.py notebook --dry-run         (fake replies, no AI, writes nothing)
      .venv\\Scripts\\python scripts\\run_scoped_eval.py notebook --max-calls 15 --pause 6
      .venv\\Scripts\\python scripts\\run_scoped_eval.py page --max-calls 15 --pause 6

Notebook: the 5 questions' quotes are saved in a temporary notebook, plus each trap's typed note.
Traps have a real source_quote: the fact is in the document but not saved, or on another page.
Reading mode: the read_page column is the page being read. The gate: PLAN.md section 3.
"""

import argparse
import json
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from learnbot import config  # noqa: E402
from learnbot.answer import ANSWERED, Answer  # noqa: E402
from learnbot.eval_check import load_rows  # noqa: E402
from learnbot.evaluate import MISSED, NOT_TESTED, REFUSED, RIGHT, feature_gate, score_answer  # noqa: E402
from learnbot.index import load_document  # noqa: E402
from learnbot.llm import CallLimitReached, default_chain  # noqa: E402
from learnbot.notebook import Notebook  # noqa: E402
from learnbot.proof import shown_quote  # noqa: E402
from learnbot.report import replace_section  # noqa: E402

DATA_DIR = Path("data/raw")
RESULTS = Path("eval/results.md")
FEATURES = {
    "notebook": ("eval/notebook_questions.csv", "eval/notebook_traps.csv", "Notebook"),
    "page": ("eval/reading_questions.csv", "eval/reading_traps.csv", "Reading mode"),
}


class FakeChain:
    """--dry-run: answers each real question with its own expected answer + quote, and refuses
    each trap. It finds script and row bugs before any AI call."""

    calls = 0
    last_attempts = ()

    def __init__(self, rows):
        self.rows = rows

    def ask(self, prompt, budget_s=None):
        for row, trap in self.rows:
            if f"Question: {row['question']}" in prompt:
                if trap:
                    break
                return json.dumps({"found": True, "answer": row["expected_answer"], "sources": [
                    {"doc": row["doc"], "page": int(row["page"]), "quote": row["source_quote"]}]}), "fake", False
        return '{"found": false}', "fake", False


def build_notebook(rows, folder):
    """A temporary notebook, as the user would have it: never the real one."""
    notebook = Notebook(folder)
    for row, trap in rows:
        if trap and row.get("typed_note"):
            notebook.add_note(row["typed_note"])
        if not trap:
            source = {"doc": row["doc"], "page": int(row["page"]), "quote": row["source_quote"], "title": row["rule"]}
            notebook.save(row["kind"], Answer(ANSWERED, row["expected_answer"], [], sources=[source]), row["question"])
    return notebook


def build_report(name, records, calls, failures):
    real = [r for r in records if not r["trap"]]
    count = Counter(r["outcome"] for r in records)
    traps = len(records) - len(real)
    slowest = max(r["ans"].seconds for r in records)
    lines = [
        f"## Day 2: {name} ({len(real)} questions + {traps} traps, run once)",
        "",
        f"**Gate: {'PASS' if not failures else 'NOT PASSED: ' + '; '.join(failures)}**",
        "",
        "| Right | Wrong | Traps refused | Missed | Not tested | Slowest | AI calls |",
        "|---|---|---|---|---|---|---|",
        f"| {count[RIGHT]}/{len(real)} | {count['wrong']} | {count[REFUSED]}/{traps} | {count[MISSED]} "
        f"| {count[NOT_TESTED]} | {slowest:.1f} s | {calls} |",
        "",
        "| Id | Outcome | Shown | AI | Time | Reason |",
        "|---|---|---|---|---|---|",
    ]
    for r in records:
        ans = r["ans"]
        lines.append(f"| {r['row']['id']} | {r['outcome']} | {ans.text[:120]} | {ans.provider or 'none'} "
                     f"| {ans.seconds:.1f} s | {r['reason'] or ans.reason} |")
    lines += ["", "### Answers shown, for a person to read", ""]
    for r in records:
        for s in r["ans"].sources:
            lines.append(f"- **{r['row']['id']}** {r['row']['question']}  \n  {r['ans'].text}  \n"
                         f"  {s['doc']} p.{s['page']}: \"{shown_quote(s)}\"")
    return "\n".join(lines)


def main():
    sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("feature", choices=sorted(FEATURES))
    parser.add_argument("--max-calls", type=int, default=15)
    parser.add_argument("--pause", type=float, default=0, help="seconds to wait before each item")
    parser.add_argument("--dry-run", action="store_true", help="fake replies, no AI, nothing written")
    args = parser.parse_args()

    questions, traps, name = FEATURES[args.feature]
    rows = [(r, False) for r in load_rows(questions)] + [(r, True) for r in load_rows(traps)]
    missing = sorted({r["doc"] for r, _ in rows if not (DATA_DIR / r["doc"]).is_file()})
    if missing:
        print(f"SKIPPED: PDF(s) not in data/raw: {', '.join(missing)} (see PLAN.md Data section)")
        return 0
    chain = FakeChain(rows) if args.dry_run else default_chain()
    if not args.dry_run:
        chain.max_calls = args.max_calls  # checked before every real call: Gemini first, Groq as backup
        if not chain.providers:
            print("No AI key set (GEMINI_API_KEY / GROQ_API_KEY in .env). Nothing to run.")
            return 1

    documents = {doc: load_document(DATA_DIR / doc) for doc in {r["doc"] for r, _ in rows}}
    records = []
    with tempfile.TemporaryDirectory() as folder:
        notebook = build_notebook(rows, folder) if args.feature == "notebook" else None
        try:
            for row, trap in rows:
                if not args.dry_run:
                    time.sleep(args.pause)  # stay under the free per-minute limits
                if notebook is not None:
                    ans = notebook.ask(row["question"], chain)
                else:
                    from learnbot.reading import ask_page

                    ans = ask_page(row["question"], documents[row["doc"]], int(row["read_page"]), chain)
                outcome, reason = score_answer(row, trap, ans)
                records.append({"row": row, "trap": trap, "ans": ans, "outcome": outcome, "reason": reason})
                print(f"{row['id']}: {outcome} [{ans.seconds:.1f} s; {ans.attempts or ans.detail or '-'}] {reason or ans.reason}")
                print(f"   {ans.text}")
                for s in ans.sources:
                    print(f"   {s['doc']} p.{s['page']}: {shown_quote(s)}")
        except CallLimitReached:
            print(f"STOPPED: call limit {args.max_calls} reached ({chain.calls} real AI calls). "
                  "These numbers are not a valid result; results.md was not written.")
            return 2

    failures = feature_gate([r["outcome"] for r in records], max(r["ans"].seconds for r in records))
    print(f"Real AI calls this run: {chain.calls}")
    print(("DRY RUN " if args.dry_run else "") + ("GATE: PASS" if not failures else "GATE: NOT PASSED: " + "; ".join(failures)))
    if not args.dry_run:
        replace_section(RESULTS, f"day2-{args.feature}", build_report(name, records, chain.calls, failures))
        print(f"Saved {RESULTS.as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
