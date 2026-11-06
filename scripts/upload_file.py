"""Upload one PDF: self-check, then the automatic self-test (once per file).

Run:  .venv\\Scripts\\python scripts\\upload_file.py C:\\path\\to\\file.pdf

A new file uses about 10-20 AI calls. The same file again uses none: its result is saved.
The first run takes a minute or two to load the models. Public documents only.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from learnbot.index import Embedder, Library, VectorStore, file_hash  # noqa: E402
from learnbot.llm import default_chain  # noqa: E402
from learnbot.search import default_searcher  # noqa: E402
from learnbot.selftest import self_test_once  # noqa: E402
from learnbot.upload import upload_file  # noqa: E402


def test_file(path):
    chain = default_chain()
    searcher = default_searcher(Library.load([path], VectorStore(Embedder())))
    return self_test_once(path.name, file_hash(path), searcher, chain)


def main():
    sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("file")
    args = parser.parse_args()
    if not Path(args.file).is_file():
        print(f"File not found: {args.file}")
        return 1

    result = upload_file(args.file, test_file)
    print(f"Self-check: {result.check.verdict} ({result.check.page_count} pages)")
    for reason in result.check.reasons:
        print(f"  - {reason}")
    if result.problem:
        print(result.problem)
        return 1
    test = result.self_test
    print(f"Stored as {result.path.as_posix()}")
    print(test.message + (" (saved result, no AI calls)" if test.from_saved else ""))
    for q in test.questions:
        print(f"  [{q['result']}] p.{q['page']} {q['question']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
