"""Notebook: saved chat answers, quiz questions and flashcards, kept after a restart.

Each saved item keeps its page and quote. Typed notes are labelled "Your note"; they are shown
and listed, but never used in answers, because they have no page to prove them against.
Questions go through the chat pipeline and proof check (learnbot.answer), with only the saved
quotes as pieces and pages. Anything else is "Not in your notebook". Web answers are not saved
here: they must never mix with document answers.
"""

import json
from datetime import datetime
from pathlib import Path

from learnbot import config
from learnbot.answer import ANSWERED, answer_within
from learnbot.chunking import Chunk
from learnbot.rule_sets import RuleSets
from learnbot.search import ScopedSearcher

NOT_IN_NOTEBOOK = "Not in your notebook"
YOUR_NOTE = "Your note"
SAVED_KINDS = ("chat", "quiz", "card")


class Notebook:
    def __init__(self, storage_dir=None):
        self.path = Path(storage_dir or config.STORAGE_DIR) / "notebook.json"
        self.items = json.loads(self.path.read_text(encoding="utf-8")) if self.path.is_file() else []

    def write(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".tmp")  # a crash while saving never damages the notebook
        temp.write_text(json.dumps(self.items, ensure_ascii=False, indent=1), encoding="utf-8")
        temp.replace(self.path)

    def add(self, **fields):
        number = max((item["id"] for item in self.items), default=0) + 1
        item = {"id": number, "saved": datetime.now().isoformat(timespec="seconds"), **fields}
        self.items.append(item)
        self.write()
        return item

    def save(self, kind, ans, question=None):
        """Save a checked answer, quiz question or flashcard. Raises ValueError if it has no
        proof or came from the web."""
        if kind not in SAVED_KINDS:
            raise ValueError(f"unknown kind: {kind}")
        if ans.status != ANSWERED or not ans.sources:
            raise ValueError("Only an answer with a page and quote can be saved.")
        if any(str(s["doc"]).startswith(("http://", "https://")) for s in ans.sources):
            raise ValueError("Web answers are not saved in the notebook.")
        sources = [{key: s[key] for key in ("doc", "page", "quote", "title", "where", "lead", "full_quote") if key in s}
                   for s in ans.sources]
        extra = {"options": ans.options, "correct": ans.correct} if getattr(ans, "options", None) else {}
        return self.add(kind=kind, question=question or getattr(ans, "question", ""), text=ans.text,
                        sources=sources, **extra)

    def add_note(self, text):
        """A typed note: shown and listed, never used in answers."""
        if not text.strip():
            raise ValueError("A note cannot be empty.")
        return self.add(kind="note", label=YOUR_NOTE, text=text.strip())

    def delete(self, number):
        """True if the item was there."""
        kept = [item for item in self.items if item["id"] != number]
        found = len(kept) != len(self.items)
        if found:
            self.items = kept
            self.write()
        return found

    def pieces(self):
        """The saved quotes as pieces, one per source. Typed notes have none."""
        found = {}
        for item in self.items:
            for s in item.get("sources", []):
                text = s.get("full_quote") or s["quote"]
                found[(s["doc"], s["page"], text)] = Chunk(s["doc"], s["page"], s.get("title", ""), text, s.get("where", ""))
        return list(found.values())

    def searcher(self):
        pieces = self.pieces()
        pages = {}
        for c in pieces:
            pages.setdefault((c.doc, c.page), []).append(c.text)
        rule_sets = RuleSets(pieces)
        # The other rule set of a document may not be saved, so one label is enough to check.
        rule_sets.docs_with_sets = {doc for doc, _ in rule_sets.labels}
        return ScopedSearcher(pieces, lambda doc, page: "\n".join(pages[(doc, page)]) if (doc, page) in pages else None,
                              rule_sets)

    def ask(self, question, chain):
        """An Answer from saved items only, or "Not in your notebook"."""
        return answer_within(question, self.searcher(), chain, NOT_IN_NOTEBOOK)
