"""Upload one file (PDF, .txt, .md, .csv, .html, .docx, .pptx, .xlsx): self-check, then the automatic self-test, once per file.

Run:  .venv\\Scripts\\python scripts\\upload_file.py C:\\path\\to\\file.pdf

A new file uses about 10-20 AI calls. The same file again uses none: its result is saved.
The first run takes a minute or two to load the models. Public documents only.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from learnbot.index import Embedder, Library, VectorStore, file_hash  # noqa: E402
from learnbot.llm import CallLimitReached, default_chain  # noqa: E402
from learnbot.search import default_searcher  # noqa: E402
from learnbot.selftest import self_test_once  # noqa: E402
from learnbot.upload import upload_file  # noqa: E402


def self_test_of(chain):
    """The self-test step of an upload, with this chain."""
    def run(path):
        searcher = default_searcher(Library.load([path], VectorStore(Embedder())))
        return self_test_once(path.name, file_hash(path), searcher, chain)
    return run


def main():
    sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("file")
    parser.add_argument("--max-calls", type=int, help="stop after this many AI calls (default: no limit)")
    args = parser.parse_args()
    if not Path(args.file).is_file():
        print(f"File not found: {args.file}")
        return 1

    chain = default_chain()
    chain.max_calls = args.max_calls
    try:
        result = upload_file(args.file, self_test_of(chain))
    except CallLimitReached:
        print(f"STOPPED: limit of {args.max_calls} AI calls reached. No self-test result was saved; "
              "replies so far are kept, so a new try does not pay for them again.")
        return 2
    print(f"Self-check: {result.check.verdict} ({result.check.page_count} pages or parts)")
    for reason in result.check.reasons:
        print(f"  - {reason}")
    if result.problem:
        print(result.problem)
        return 1
    test = result.self_test
    print(f"Stored as {result.path.as_posix()}")
    print(test.message + (" (saved result, no AI calls)" if test.from_saved else ""))
    for q in test.questions:
        print(f"  [{q['result']}] {q.get('where') or 'p.' + str(q['page'])} {q['question']}")
    print(f"AI calls this run: {chain.calls}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
