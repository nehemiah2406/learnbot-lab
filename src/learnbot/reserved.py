"""Reserved rules: if a question names a rule / section ("Inland Rule 28", "Rule 3(h)") and the
best matching piece says it is "[Reserved]", LearnBot says so with its location. Code only,
no AI. General: any document that marks empty rules or paragraphs "[Reserved]".

"Best matching piece" = the first piece, in search order, that names the rule (and has the
asked paragraph marker, e.g. "(h)"). If that piece has text for it, this rule does nothing
and the normal AI answer + proof check runs.
"""

import re

from learnbot.proof import same_text

RESERVED_ANSWER = "This rule is reserved (no text) in this document."
REFERENCE = re.compile(r"\b(rule|section|article|annex|regulation|chapter|part|§)\s*(\d+|[ivxlc]+)\b"
                       r"((?:\s*\([a-z0-9]+\))*)", re.IGNORECASE)
RESERVED = r"\s*\[reserved\]"


def asked_references(question):
    """[(rule pattern, paragraph marker or None)], e.g. "Rule 3(h)" -> (r"\\brule\\s*3\\b", "(h)")."""
    refs = []
    for kind, number, tail in REFERENCE.findall(question):
        markers = re.findall(r"\([a-z0-9]+\)", tail.lower())
        refs.append((rf"\b{re.escape(kind)}\s*{re.escape(number)}\b", markers[-1] if markers else None))
    return refs


def reserved_source(question, pieces, page_text, rule_sets):
    """{doc, page, quote, title} if the asked rule / paragraph is "[Reserved]", else None."""
    for rule, marker in asked_references(question):
        for c in pieces:
            if not rule_sets.allowed(question, c.doc, c.page):
                continue
            text = same_text(c.search_text)
            if not re.search(rule, text, re.IGNORECASE):
                continue
            if marker:
                where = rf"(?<![\w(]){re.escape(marker)}"
                first = re.search(rf"{where}({RESERVED})?", text, re.IGNORECASE)
                if not first:
                    continue  # this piece of the rule does not have the paragraph
                if not first.group(1):
                    return None  # the best matching piece has text for this paragraph
                pattern = where + RESERVED
            else:
                pattern = rule + RESERVED
                if not re.search(pattern, text, re.IGNORECASE):
                    return None  # the best matching piece has text for this rule
            page = same_text(page_text(c.doc, c.page) or "")
            found = re.search(pattern, page, re.IGNORECASE)
            if not found:
                return None
            return {"doc": c.doc, "page": c.page, "quote": found.group(0).strip(), "title": c.title}
    return None
