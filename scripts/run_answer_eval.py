"""Phase 4 eval: search + AI answer + proof check on the eval set -> eval/results.md.

Run:  .venv\\Scripts\\python scripts\\run_answer_eval.py              (all 37 questions)
      .venv\\Scripts\\python scripts\\run_answer_eval.py --ids NAV-04,BG-05,TRAP-NAV-02
      .venv\\Scripts\\python scripts\\run_answer_eval.py --dry-run    (count AI calls, call nothing)

Quota safety: answers are cached in cache/ (same question + same pieces = no new call).
Before calling, the script counts the questions that are not cached; if that is more
than --max-calls (default config.MAX_LLM_CALLS_WITHOUT_ASKING) it stops without calling.
It also stops calling once --max-calls real calls were made (Groq fallbacks count too).
Before the first real call, one tiny warm-up call checks the main AI; if it fails, the
run stops and shows the error kind (no quota is spent on a run without the main AI).
Only a full run (no --ids) writes eval/results.md.
"""

import argparse
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from learnbot import config  # noqa: E402
from learnbot.answer import ANSWERED, answer_question, build_prompt  # noqa: E402
from learnbot.baseline import NOT_FOUND, BM25Index, answer as baseline_answer  # noqa: E402
from learnbot.eval_check import load_rows  # noqa: E402
from learnbot.evaluate import (  # noqa: E402
    CORRECT_OTHER, MISSED, NOT_TESTED, REFUSED, RIGHT, TRAP_ANSWERED, WRONG,
    exact_answer_in, outcome, score_answer,
)
from learnbot.index import Embedder, Library, VectorStore  # noqa: E402
from learnbot.llm import CallLimitReached, LLMDailyLimit, LLMError, default_chain  # noqa: E402
from learnbot.proof import shown_quote  # noqa: E402
from learnbot.report import replace_section  # noqa: E402
from learnbot.search import default_searcher  # noqa: E402

DATA_DIR = Path("data/raw")
RESULTS = Path("eval/results.md")


def pct(n, total):
    return f"{n}/{total} ({100 * n / total:.0f}%)" if total else "0/0"


def short(text, n=150):
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[:n] + "..."


def baseline_records(library, explain, traps):
    """Phase 3 numbers on the same pieces, for the side-by-side table (no AI)."""
    index = BM25Index(library.chunks)
    records = []
    for row, trap in [(r, False) for r in explain] + [(r, True) for r in traps]:
        verdict, hits = baseline_answer(index, row["question"])
        exact = (not trap and verdict != NOT_FOUND and exact_answer_in(row["expected_answer"], hits[0].chunk.text))
        records.append({"trap": trap, "outcome": outcome(row, trap, verdict, hits), "exact": exact})
    return records


def summary(records):
    explain = [r for r in records if not r["trap"]]
    traps = [r for r in records if r["trap"]]
    c = Counter(r["outcome"] for r in records)
    return {
        "right": pct(c[RIGHT], len(explain)), "exact": pct(sum(r["exact"] for r in explain), len(explain)),
        "other": str(c[CORRECT_OTHER]), "refused": pct(c[REFUSED], len(traps)),
        "wrong": str(c[WRONG]), "trap_answered": str(c[TRAP_ANSWERED]), "missed": str(c[MISSED]),
        "not_tested": str(c[NOT_TESTED]),
    }


def where(sources):
    return "; ".join(f"{s['doc']} p.{s['page']} ({short(s['title'], 60)})" for s in sources)


def build_report(records, base, chain, k, title):
    explain = [r for r in records if not r["trap"]]
    fresh = [r["ans"].seconds for r in records if not r["ans"].cached and r["ans"].provider]
    s4, s3 = summary(records), summary(base)
    providers = Counter(r["ans"].provider or "none (no AI answer)" for r in records)
    lines = [
        title,
        "",
        f"- Search: `{config.SEARCH_METHOD}` (BM25 + `{config.EMBED_MODEL}`, RRF), rule-set filter on, "
        f"re-ranker `{config.RERANK_MODEL}`; top {k} pieces sent to the AI",
        f"- AI: {', '.join(p.label for p in chain.providers)} (in this order), timeout "
        f"{config.MAIN_LLM_TIMEOUT_S} s (main) / {config.FALLBACK_LLM_TIMEOUT_S} s (fallback), all within "
        f"{config.QUESTION_TIME_BUDGET_S} s per question, no retries; prompt version {config.PROMPT_VERSION}",
        "- Every answer passed the proof check (quote on its page, numbers + units in the quote, "
        "page was sent, rule set, topic, one source unless comparing, every number of the quote "
        "in the answer) or was replaced by \"Not in this document\"",
        "- **Wrong** = answer shown is not supported by the expected source, OR its numbers differ "
        "from the expected answer's numbers",
        "",
        "| Measure | Phase 3 baseline | Phase 4 | Target |",
        "|---|---|---|---|",
        f"| Right doc + page | {s3['right']} | {s4['right']} | reported (aim 9 of 10, not a gate) |",
        f"| Exact answer (all numbers + key words) | {s3['exact']} | {s4['exact']} | (tracked) |",
        f"| Correct, other source | {s3['other']} | {s4['other']} | |",
        f"| Traps \"{NOT_FOUND}\" | {s3['refused']} | {s4['refused']} | all |",
        f"| **Wrong** | {s3['wrong']} | **{s4['wrong']}** | **0** |",
        f"| **Traps answered** | {s3['trap_answered']} | **{s4['trap_answered']}** | **0** |",
        f"| Missed (real question, said \"{NOT_FOUND}\") | {s3['missed']} | {s4['missed']} | |",
        f"| Not tested (AI busy; the run is incomplete if > 0) | n/a | {s4['not_tested']} | 0 |",
    ]
    if fresh:
        lines.append(f"| Answer time (search + AI + check), new answers | ~2 ms (search only) "
                     f"| avg {sum(fresh) / len(fresh):.1f} s, max {max(fresh):.1f} s | under 10 s |")
    else:
        lines.append("| Answer time | ~2 ms (search only) | all answers from cache this run | under 10 s |")
    lines += ["", "Which AI answered: " + ", ".join(f"{name} {n}" for name, n in providers.most_common()), ""]

    groups = defaultdict(list)
    for r in explain:
        groups[r["row"]["doc"]].append(r)
    lines += ["#### Per document", "", "| Document | Questions | Right page | Correct, other source | Wrong | Missed |",
              "|---|---|---|---|---|---|"]
    for doc in sorted(groups):
        g = groups[doc]
        c = Counter(r["outcome"] for r in g)
        lines.append(f"| {doc} | {len(g)} | {pct(c[RIGHT], len(g))} | {c[CORRECT_OTHER]} | {c[WRONG]} | {c[MISSED]} |")

    lines += ["", "### Per question: outcome and which AI answered", "",
              "| Question | Outcome | AI that answered | Time (new answers) |", "|---|---|---|---|"]
    for r in records:
        ans = r["ans"]
        ai = ans.provider or "none (AI busy)"
        took = "from cache" if ans.cached else f"{ans.seconds:.1f} s"
        lines.append(f"| {r['row']['id']} | {r['outcome']} | {ai} | {took} |")
    lines += ["", "### Failed questions", ""]
    failed = [r for r in records if r["outcome"] in (WRONG, MISSED, TRAP_ANSWERED, NOT_TESTED)]
    for r in failed:
        row, ans = r["row"], r["ans"]
        expected = f"\"{NOT_FOUND}\"" if r["trap"] else f"{row['doc']} p.{row['page']}"
        shown = f"\"{short(ans.text)}\" from {where(ans.sources)}" if ans.status == ANSWERED else ans.text
        lines.append(f"- **{row['id']}** ({r['outcome']}) expected {expected}: {row['question']}  \n"
                     f"  Reason: {r['reason']}  \n  Shown: {shown}"
                     + (f"  \n  AI calls: {ans.attempts}" if ans.attempts and not ans.cached else ""))
    if not failed:
        lines.append("None.")

    lines += ["", "### All answers shown", ""]
    for r in records:
        ans = r["ans"]
        if ans.status == ANSWERED:
            quotes = " | ".join(f"\"{short(shown_quote(s), 160)}\"" for s in ans.sources)
            lines.append(f"- **{r['row']['id']}** ({r['outcome']}): {short(ans.text)}  \n"
                         f"  Source: {where(ans.sources)}; quote: {quotes}")
    return "\n".join(lines)


WARM_UP_PROMPT = 'Reply with JSON only: {"ok": true}'


def warm_up(chain):
    """(ok?, "label ok/kind seconds"): one tiny call to the main AI (counts as a call).
    If it fails, the run starts with the main AI switched off, exactly as after
    config.MAX_FAILURES_IN_A_ROW failures: it is tried again every
    config.RETRY_SWITCHED_OFF_EVERY questions (a daily limit: never again this run)."""
    main = chain.providers[0]
    chain.count_call()  # raises CallLimitReached if the limit is used up
    start = time.perf_counter()
    try:
        main.ask(WARM_UP_PROMPT)
    except LLMError as err:
        chain.switched_off.add(main.label)
        if isinstance(err, LLMDailyLimit):
            chain.daily_limit.add(main.label)
        return False, f"{main.label} {err.kind} {time.perf_counter() - start:.1f} s"
    return True, f"{main.label} ok {time.perf_counter() - start:.1f} s"


def main():
    sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--ids", help="comma-separated question ids (smoke test; results.md is not written)")
    parser.add_argument("--max-calls", type=int, default=config.MAX_LLM_CALLS_WITHOUT_ASKING)
    parser.add_argument("--dry-run", action="store_true", help="only count the AI calls needed")
    parser.add_argument("--pause", type=float, default=0, help="seconds to wait before each new AI call")
    parser.add_argument("--fresh", action="store_true",
                        help="ignore saved AI replies and ask again (new replies are still saved)")
    parser.add_argument("--explain", default="eval/explain_questions.csv")
    parser.add_argument("--traps", default="eval/trap_questions.csv")
    parser.add_argument("--section", default="phase4-answers", help="results.md section to write")
    parser.add_argument("--title", default="## Phase 4: hybrid search + AI answer + proof check")
    args = parser.parse_args()

    explain, traps = load_rows(args.explain), load_rows(args.traps)
    needed = sorted({r["doc"] for r in explain + traps})
    missing = [d for d in needed if not (DATA_DIR / d).is_file()]
    if missing:
        print(f"SKIPPED: PDF(s) not in data/raw: {', '.join(missing)} (see PLAN.md Data section)")
        return 0
    pdfs = sorted(p for p in DATA_DIR.iterdir() if p.suffix.lower() == ".pdf")
    library = Library.load(pdfs, VectorStore(Embedder()))
    searcher = default_searcher(library)
    chain = default_chain()
    chain.read_cache = not args.fresh
    chain.max_calls = args.max_calls  # checked before every real call (warm-up, Gemini, Groq)
    if not chain.providers:
        print("No AI key set (GEMINI_API_KEY / GROQ_API_KEY in .env). Nothing to run.")
        return 1

    rows = [(r, False) for r in explain] + [(r, True) for r in traps]
    if args.ids:
        wanted = {i.strip() for i in args.ids.split(",")}
        rows = [(r, t) for r, t in rows if r["id"] in wanted]
    uncached = sum(not chain.is_cached(build_prompt(r["question"], searcher.search(r["question"])))
                   for r, _ in rows)
    print(f"Questions: {len(rows)}; not cached (need an AI call): {uncached}; call limit: {args.max_calls}")
    if args.dry_run:
        return 0
    if uncached > args.max_calls:
        print(f"STOPPED: {uncached} AI calls needed, more than the limit {args.max_calls}. "
              "Ask Hari, then run again with --max-calls N.")
        return 2

    if uncached:
        try:
            ok, status = warm_up(chain)
        except CallLimitReached:
            print(f"STOPPED: call limit {args.max_calls} reached before the warm-up call. Nothing was asked.")
            return 2
        print(f"Warm-up call: {status}")
        if not ok:
            print(f"Main AI switched off from the start (tried again every "
                  f"{config.RETRY_SWITCHED_OFF_EVERY} questions); the fallback answers meanwhile.")

    records = []
    for row, trap in rows:
        cached = chain.is_cached(build_prompt(row["question"], searcher.search(row["question"])))
        if not cached and chain.calls and args.pause:
            time.sleep(args.pause)  # stay under the free per-minute limits
        try:
            ans = answer_question(row["question"], searcher, chain)
        except CallLimitReached:
            print(f"STOPPED at {row['id']}: call limit {args.max_calls} reached ({chain.calls} real AI calls). "
                  "No more calls were made. These numbers are not a valid result; results.md was not written. "
                  "Ask Hari, then run again with --max-calls N.")
            return 2
        result, reason = score_answer(row, trap, ans)
        exact = (not trap and ans.status == ANSWERED and exact_answer_in(
            row["expected_answer"], ans.text + " " + " ".join(shown_quote(s) for s in ans.sources)))
        records.append({"row": row, "trap": trap, "ans": ans, "outcome": result, "reason": reason, "exact": exact})
        tag = "cache" if ans.cached else (ans.attempts or ans.detail or "-")
        print(f"{row['id']}: {result} [{ans.seconds:.1f} s; {tag}] {reason}")

    print(f"Real AI calls this run: {chain.calls}")
    s = summary(records)
    print(f"Right page: {s['right']}  Exact: {s['exact']}  Correct other source: {s['other']}  "
          f"Traps refused: {s['refused']}  Wrong: {s['wrong']}  Traps answered: {s['trap_answered']}  "
          f"Missed: {s['missed']}  Not tested (AI busy): {s['not_tested']}")
    if s["not_tested"] != "0":
        print("INCOMPLETE: some questions were not tested (AI busy). These numbers are not a valid result.")
    if not args.ids:
        base = baseline_records(library, explain, traps)
        replace_section(RESULTS, args.section, build_report(records, base, chain, config.PIECES_TO_LLM, args.title))
        print(f"Saved {RESULTS.as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
