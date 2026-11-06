"""Make a study book from one document, one chapter per topic, and save it as a Markdown file.

Run:  .venv\\Scripts\\python scripts\\make_book.py boaters_guide.pdf "fire extinguisher maintenance" "life jacket label"

Uses 1-2 AI calls per chapter (none if the same book was made before). The book is saved in
storage/books. It takes a minute or two to load the models.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from learnbot.book import make_book, save_book  # noqa: E402
from learnbot.index import Embedder, Library, VectorStore  # noqa: E402
from learnbot.llm import default_chain  # noqa: E402
from learnbot.search import default_searcher  # noqa: E402
from learnbot.upload import find_document  # noqa: E402


def main():
    sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("document", help="file name in data/uploads or data/raw")
    parser.add_argument("topics", nargs="+", help="one chapter per topic")
    args = parser.parse_args()

    path = find_document(args.document)
    if path is None:
        print(f"{args.document} was not found in data/uploads or data/raw.")
        return 1
    chain = default_chain()
    if not chain.providers:
        print("No AI key set (GEMINI_API_KEY / GROQ_API_KEY in .env).")
        return 1
    searcher = default_searcher(Library.load([path], VectorStore(Embedder())))
    try:
        chapters = make_book(args.topics, searcher, chain)
    except ValueError as problem:
        print(problem)
        return 1
    for chapter in chapters:
        print(f"{chapter.topic}: {len(chapter.facts)} facts, {chapter.dropped} dropped"
              + (f" ({chapter.text})" if not chapter.facts else ""))
    print(f"Saved {save_book(args.document, chapters).as_posix()} ({chain.calls} AI calls)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
