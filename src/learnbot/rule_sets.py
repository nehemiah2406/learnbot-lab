"""Rule sets (e.g. International / Inland) from page headings. General rule, any PDF.

- A page's label is the one rule-set word found in the headings (piece titles) of
  that page. A page with none or with more than one has no label.
- A document "has rule sets" if it has labelled pages for at least two different words.
- If a question names exactly one rule-set word, an answer from a document with rule
  sets must come from a page labelled with that word. Other documents are not affected.
"""

import re
from collections import defaultdict

from learnbot import config


def words_in(text, words):
    return {w for w in words if re.search(rf"\b{re.escape(w)}\b", text, re.IGNORECASE)}


class RuleSets:
    def __init__(self, chunks, words=None):
        self.words = tuple(words or config.RULE_SET_WORDS)
        found = defaultdict(set)
        for c in chunks:
            found[(c.doc, c.page)] |= words_in(c.title, self.words)
        self.labels = {key: next(iter(w)) for key, w in found.items() if len(w) == 1}
        per_doc = defaultdict(set)
        for (doc, _), label in self.labels.items():
            per_doc[doc].add(label)
        self.docs_with_sets = {doc for doc, labels in per_doc.items() if len(labels) >= 2}

    def asked(self, question):
        """The one rule-set word named in the question, or None (none or several named)."""
        named = words_in(question, self.words)
        return next(iter(named)) if len(named) == 1 else None

    def label(self, doc, page):
        return self.labels.get((doc, page))

    def allowed(self, question, doc, page):
        """False only if the question names a rule set the page does not belong to."""
        asked = self.asked(question)
        if asked is None or doc not in self.docs_with_sets:
            return True
        return self.label(doc, page) == asked
