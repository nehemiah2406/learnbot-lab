"""Reading mode: read one page of a document, or ask a question about that page.

Run:  .venv\\Scripts\\python scripts\\read_page.py boaters_guide.pdf --page 16
      .venv\\Scripts\\python scripts\\read_page.py boaters_guide.pdf --page 16 --ask "When do the signals expire?"

Reading uses no AI. A question uses 1-2 AI calls and is answered only from that page.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from learnbot.index import load_document  # noqa: E402
from learnbot.llm import default_chain  # noqa: E402
from learnbot.proof import shown_quote, shown_where  # noqa: E402
from learnbot.reading import ask_page, view_page  # noqa: E402
from learnbot.upload import find_document  # noqa: E402


def main():
    sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("document", help="file name in data/uploads or data/raw")
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--ask", help="a question about this page")
    args = parser.parse_args()

    path = find_document(args.document)
    if path is None:
        print(f"{args.document} was not found in data/uploads or data/raw.")
        return 1
    document = load_document(path)
    try:
        view = view_page(document, path, args.page)
        if args.ask:
            ans = ask_page(args.ask, document, args.page, default_chain())
            print(ans.text)
            for s in ans.sources:
                print(f"Source: {s['doc']}, {shown_where(s)} ({s['title'][:60]})")
                print(f"Quote: \"{shown_quote(s)}\"")
            if view.warning:
                print(view.warning)
            return 0
    except ValueError as problem:
        print(problem)
        return 1
    print(f"{view.doc}, {view.where + ', part' if view.where else 'page'} {view.page} of {view.total}")
    if view.warning:
        print(view.warning)
    print()
    print(view.text)
    print()
    print(f"Previous: {'--page ' + str(view.previous) if view.previous else 'none'}   "
          f"Next: {'--page ' + str(view.next) if view.next else 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
