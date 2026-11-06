"""Your notebook. It is kept in storage/notebook.json after a restart.

Run:  .venv\\Scripts\\python scripts\\notebook.py list
      .venv\\Scripts\\python scripts\\notebook.py note "Check the flares before Friday"
      .venv\\Scripts\\python scripts\\notebook.py delete 3
      .venv\\Scripts\\python scripts\\notebook.py save boaters_guide.pdf "When do flares expire?"   (asks chat, saves a proved answer)
      .venv\\Scripts\\python scripts\\notebook.py ask "When do flares expire?"

Save quiz questions and flashcards with --save on make_quiz.py and make_flashcards.py.
"ask" and "save" use 1-2 AI calls. "save" takes a minute or two to load the models.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from learnbot.answer import ANSWERED, answer_question  # noqa: E402
from learnbot.llm import default_chain  # noqa: E402
from learnbot.notebook import Notebook  # noqa: E402
from learnbot.proof import shown_quote, shown_where  # noqa: E402
from learnbot.upload import find_document  # noqa: E402


def show_sources(sources):
    for s in sources:
        print(f"   Source: {s['doc']}, {shown_where(s)} ({s.get('title', '')[:60]})")
        print(f"   Quote: \"{shown_quote(s)}\"")


def show_item(item):
    if item["kind"] == "note":
        print(f"[{item['id']}] {item['label']}: {item['text']}")
        return
    print(f"[{item['id']}] {item['kind']}: {item['question']}")
    for i, option in enumerate(item.get("options", [])):
        print(f"   {'*' if i == item['correct'] else '-'} {option}")
    print(f"   Answer: {item['text']}")
    show_sources(item["sources"])


def save_chat(notebook, document, question):
    from learnbot.index import Embedder, Library, VectorStore
    from learnbot.search import default_searcher

    path = find_document(document)
    if path is None:
        print(f"{document} was not found in data/uploads or data/raw.")
        return 1
    searcher = default_searcher(Library.load([path], VectorStore(Embedder())))
    ans = answer_question(question, searcher, default_chain())
    if ans.status != ANSWERED:
        print(f"Nothing saved: {ans.text}")
        return 1
    show_item(notebook.save("chat", ans, question))
    return 0


def main():
    sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list")
    commands.add_parser("note").add_argument("text")
    commands.add_parser("delete").add_argument("id", type=int)
    commands.add_parser("ask").add_argument("question")
    save = commands.add_parser("save")
    save.add_argument("document")
    save.add_argument("question")
    args = parser.parse_args()

    notebook = Notebook()
    if args.command == "list":
        for item in notebook.items:
            show_item(item)
        print(f"{len(notebook.items)} items.")
    elif args.command == "note":
        show_item(notebook.add_note(args.text))
    elif args.command == "delete":
        print("Deleted." if notebook.delete(args.id) else f"No item {args.id}.")
    elif args.command == "save":
        return save_chat(notebook, args.document, args.question)
    else:
        ans = notebook.ask(args.question, default_chain())
        print(ans.text)
        show_sources(ans.sources)
    return 0


if __name__ == "__main__":
    sys.exit(main())
