"""Make a quiz from one document and print it (the screens come later, PLAN.md Day 5).

Run:  .venv\\Scripts\\python scripts\\make_quiz.py osha3124.pdf --topic "fixed ladders" --count 3
      .venv\\Scripts\\python scripts\\make_quiz.py osha3124.pdf --count 3     (no topic: facts from across the document)

Uses about 1-2 AI calls per question. The first run takes a minute or two to load the models.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from learnbot.index import Embedder, Library, VectorStore  # noqa: E402
from learnbot.llm import default_chain  # noqa: E402
from learnbot.notebook import Notebook  # noqa: E402
from learnbot.proof import shown_quote, shown_where  # noqa: E402
from learnbot.quiz import make_quiz  # noqa: E402
from learnbot.search import default_searcher  # noqa: E402
from learnbot.study import AI_BUSY_ITEM, nothing_kept  # noqa: E402
from learnbot.upload import find_document  # noqa: E402


def main():
    sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("document", help="file name in data/uploads or data/raw")
    parser.add_argument("--topic", help="what to ask about (default: facts from across the document)")
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument("--save", action="store_true", help="save what is kept in your notebook")
    args = parser.parse_args()

    path = find_document(args.document)
    if path is None:
        print(f"{args.document} was not found in data/uploads or data/raw.")
        return 1
    searcher = default_searcher(Library.load([path], VectorStore(Embedder())))
    chain = default_chain()
    if not chain.providers:
        print("No AI key set (GEMINI_API_KEY / GROQ_API_KEY in .env).")
        return 1
    questions, dropped, busy = make_quiz(args.topic, searcher, chain, args.count)
    for number, q in enumerate(questions, start=1):
        print(f"\n{number}. {q.question}")
        for letter, option in zip("ABCD", q.options):
            print(f"   {letter}) {option}")
        s = q.sources[0]
        print(f"   Right answer: {'ABCD'[q.correct]}")
        print(f"   Source: {s['doc']}, {shown_where(s)} ({s['title'][:60]})")
        print(f"   Quote: \"{shown_quote(s)}\"")
    if not questions and not busy:
        print(nothing_kept(args.topic, dropped, "question"))
    if busy:
        print(AI_BUSY_ITEM)
    if args.save:
        notebook = Notebook()
        for item in questions:
            notebook.save("quiz", item)
        print(f"Saved {len(questions)} in your notebook.")
    print(f"\n{len(questions)} questions kept, {dropped} dropped by the checks, {chain.calls} AI calls.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
