"""Make flashcards from one document and print them (the screens come later, PLAN.md Day 5).

Run:  .venv\\Scripts\\python scripts\\make_flashcards.py osha3124.pdf --topic "fixed ladders" --count 3
      .venv\\Scripts\\python scripts\\make_flashcards.py osha3124.pdf --count 3     (no topic: facts from across the document)

Uses about 1-2 AI calls per card. The first run takes a minute or two to load the models.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from learnbot.baseline import NOT_FOUND  # noqa: E402
from learnbot.flashcards import make_cards  # noqa: E402
from learnbot.index import Embedder, Library, VectorStore  # noqa: E402
from learnbot.llm import default_chain  # noqa: E402
from learnbot.proof import shown_quote  # noqa: E402
from learnbot.search import default_searcher  # noqa: E402
from learnbot.study import AI_BUSY_ITEM  # noqa: E402

DATA_DIR = Path("data/raw")


def main():
    sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("document", help="file name in data/raw")
    parser.add_argument("--topic", help="what the cards are about (default: facts from across the document)")
    parser.add_argument("--count", type=int, default=5)
    args = parser.parse_args()

    path = DATA_DIR / args.document
    if not path.is_file():
        print(f"{args.document} is not in data/raw.")
        return 1
    searcher = default_searcher(Library.load([path], VectorStore(Embedder())))
    chain = default_chain()
    if not chain.providers:
        print("No AI key set (GEMINI_API_KEY / GROQ_API_KEY in .env).")
        return 1
    cards, dropped, busy = make_cards(args.topic, searcher, chain, args.count)
    for number, card in enumerate(cards, start=1):
        s = card.sources[0]
        print(f"\nCard {number}")
        print(f"   Front: {card.question}")
        print(f"   Back: {card.text}")
        print(f"   Source: {s['doc']} p.{s['page']} ({s['title'][:60]})")
        print(f"   Quote: \"{shown_quote(s)}\"")
    if not cards and not busy:
        print(NOT_FOUND)
    if busy:
        print(AI_BUSY_ITEM)
    print(f"\n{len(cards)} cards kept, {dropped} dropped by the checks, {chain.calls} AI calls.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
