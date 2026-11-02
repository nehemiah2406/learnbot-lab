"""Choose config.TOPIC_MIN_SCORE: the re-ranker score a paraphrased question and its quote
need when they share no word (proof check, off_topic). No AI calls; local re-ranker only.

  Right quotes:  each eval question with its expected source_quote (29 questions).
  Bad quotes:    every sentence / list item of the pieces sent for each TRAP question (no
                 answer exists, so any quote is wrong), and every sentence / list item of the
                 pieces sent for an eval question whose numbers are NOT the expected answer's
                 (the wrong item of a list, like the sidelight for a masthead question).
  Threshold:     just above the highest bad-quote score (never let a bad quote through).

Run:  .venv\\Scripts\\python scripts\\choose_topic_threshold.py   -> eval/results.md section
"""

import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from learnbot import config  # noqa: E402
from learnbot.eval_check import load_rows, split_pair  # noqa: E402
from learnbot.index import Embedder, Library, VectorStore  # noqa: E402
from learnbot.proof import ITEM_BREAK, key_words, quote_numbers  # noqa: E402
from learnbot.report import replace_section  # noqa: E402
from learnbot.search import default_searcher  # noqa: E402
from learnbot.units import number_values  # noqa: E402

SENTENCE_END = re.compile(r"(?<=[.?!])\s+(?=[A-Z(•−–-])")


def segments(text):
    """Sentences and list items of a piece (the kinds of quote the AI gives)."""
    parts = []
    for sentence in SENTENCE_END.split(text):
        parts += [p.strip(" ;") for p in ITEM_BREAK.split(sentence)]
    return [p for p in parts if len(p.split()) >= config.MIN_QUOTE_WORDS]


def main():
    sys.stdout.reconfigure(errors="replace")
    explain, traps = load_rows("eval/explain_questions.csv"), load_rows("eval/trap_questions.csv")
    library = Library.load(sorted(Path("data/raw").glob("*.pdf")), VectorStore(Embedder()))
    searcher = default_searcher(library)
    score = searcher.reranker.scores

    right = []  # (id, score, shares a word with the question?)
    for row in explain:
        words = key_words(row["question"], ignore=searcher.rule_sets.words)
        for quote in split_pair(row["source_quote"]):
            right.append((row["id"], float(score(row["question"], [quote])[0]), bool(words & key_words(quote))))

    bad = []  # (id, score, quote)
    for row, trap in [(r, False) for r in explain] + [(r, True) for r in traps]:
        expected = number_values(row["expected_answer"]) | number_values(row["question"])
        quotes = {q for c in searcher.search(row["question"]) for q in segments(c.text)}
        if not trap:  # only quotes with a number that is not in the expected answer
            quotes = {q for q in quotes if quote_numbers(q) - expected}
        if quotes:
            qs = sorted(quotes)
            scores = score(row["question"], qs)
            best = max(zip(scores, qs))
            bad.append((row["id"], float(best[0]), best[1]))

    worst_bad = max(s for _, s, _ in bad)
    threshold = math.floor(worst_bad * 100 + 1) / 100  # just above the highest bad score
    passed = [r for r in right if r[1] >= threshold]
    no_word = [r for r in right if not r[2]]
    rescued = sum(r[1] >= threshold for r in no_word)
    decision = (f"Decision: `TOPIC_MIN_SCORE = {threshold:.2f}` (lets {rescued} paraphrased quote(s) pass)."
                if rescued else
                "Decision: **no safe threshold**. Every right quote that shares no word with its question "
                "scores below the bad quotes, so any threshold that lets it pass would also let bad quotes "
                "pass. `TOPIC_MIN_SCORE` stays `None` (off): such answers stay \"Not in this document\".")
    lines = [
        "## Phase 4: topic threshold for paraphrased questions",
        "",
        f"Re-ranker `{config.RERANK_MODEL}` score of (question, quote). Used only when the quote "
        "shares no word with the question. Chosen by `scripts/choose_topic_threshold.py` (no AI calls).",
        "",
        f"- Highest bad-quote score (trap quotes + wrong-number quotes): **{worst_bad:.2f}** "
        f"({max(bad, key=lambda b: b[1])[0]})",
        f"- Lowest safe threshold: **{threshold:.2f}**",
        f"- Right quotes at or above it: {len(passed)}/{len(right)}; of the right quotes that share no "
        f"word with their question: {rescued}/{len(no_word)}",
        "",
        decision,
        "",
        "| Right quote (question) | Score | Shares a word | Passes threshold |",
        "|---|---|---|---|",
    ]
    lines += [f"| {i} | {s:.2f} | {'yes' if w else 'no'} | {'yes' if s >= threshold else 'no'} |"
              for i, s, w in right]
    lines += ["", "| Highest bad quote per question | Score | Quote |", "|---|---|---|"]
    lines += [f"| {i} | {s:.2f} | {q[:80]} |" for i, s, q in sorted(bad, key=lambda b: -b[1])[:12]]
    replace_section(Path("eval/results.md"), "phase4-topic-threshold", "\n".join(lines))
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
