"""Proof check: code (not the AI) decides if an AI answer may be shown. Any PDF.

An answer is shown only if ALL checks pass for every source; otherwise the user sees
"Not in this document". Nothing is repaired or guessed. Checks, in order:

  no_answer          the reply has an answer and at least one source
  page_not_sent      the source's doc + page is one of the pieces sent to the AI
  quote_too_short    the quote has at least config.MIN_QUOTE_WORDS words
  quote_not_on_page  the quote appears word for word (normalised) on that doc + page
  wrong_rule_set     the question names a rule set -> the page has that rule set
  off_topic          the quote fits the question: if the question's key words occur in the
                     piece text, one must occur in the quote (not just in the broad piece
                     title; words compared by their first 5 letters); numbers in the question must
                     be in a quote or in the title of the piece quoted
  unit_missing       a question that asks "how many <unit>" gets an answer with that unit
  number_not_in_quote  every number in the answer is in a quote
  quote_not_focused  the quote has no other measurement ("number + unit") than those in
                     the answer or the question: an AI that quotes a whole list ("masthead
                     light, 6 miles; sidelight, 3 miles") cannot pick the wrong item unseen
  unit_not_in_quote    every "number + unit" in the answer ("6 miles", "200 Hz") is in a quote
"""

import re
from dataclasses import dataclass

from learnbot import config
from learnbot.baseline import STOPWORDS, tokenize
from learnbot.eval_check import normalize, numbers_in

NUMBER_UNIT = re.compile(r"(\d+(?:[.,]\d+)*)\s*([a-z%°]+)")
# Lines are joined with spaces in pieces, so "look-\nout" becomes "look- out".
BROKEN_HYPHEN = re.compile(r"(\w)- (\w)")


def same_text(text):
    return BROKEN_HYPHEN.sub(r"\1-\2", normalize(text))


def number_units(text):
    """{(number, unit)} pairs like ("6", "miles"); words like "to" or "and" are not units."""
    pairs = NUMBER_UNIT.findall(same_text(text).lower())
    return {(n.replace(",", ""), u) for n, u in pairs if u not in STOPWORDS}


STEM_LETTERS = 5  # "expire" / "expiration" and "signal" / "signals" count as the same word


HOW_MANY = re.compile(r"\bhow many ([a-z]+)", re.IGNORECASE)
UNIT_LETTERS = 4  # "yard" / "yards", "second" / "seconds" count as the same unit


def asked_unit(question):
    """The unit a question asks for ("how many yards" -> "yards"), or None."""
    match = HOW_MANY.search(question)
    word = match.group(1).lower() if match else None
    return word if word and word not in STOPWORDS else None


def key_words(text, ignore=()):
    """Word stems (first STEM_LETTERS letters) of the content words of 3+ letters."""
    ignore = {w.lower() for w in ignore}
    return {t[:STEM_LETTERS] for t in tokenize(text) if t.isalpha() and len(t) >= 3 and t not in ignore}


@dataclass
class Proof:
    ok: bool
    reason: str = ""  # name of the first failed check
    detail: str = ""


def fail(reason, detail=""):
    return Proof(False, reason, detail)


def quoted_pieces(source, sent):
    """Pieces sent from the source's page that contain the quote (else all from that page)."""
    page_pieces = [c for c in sent if (c.doc, c.page) == (source["doc"], source["page"])]
    quote = same_text(source["quote"])
    return [c for c in page_pieces if quote in same_text(c.search_text)] or page_pieces


def check(question, reply, sent, page_text, rule_sets):
    """Proof for one parsed AI reply. page_text(doc, page) -> full page text or None."""
    answer = (reply.get("answer") or "").strip()
    sources = reply.get("sources") or []
    if not answer or not sources:
        return fail("no_answer")
    sent_pages = {(c.doc, c.page) for c in sent}
    question_words = key_words(question, ignore=rule_sets.words)
    titles = []
    for s in sources:
        where = f"{s['doc']} p.{s['page']}"
        if (s["doc"], s["page"]) not in sent_pages:
            return fail("page_not_sent", where)
        if len(s["quote"].split()) < config.MIN_QUOTE_WORDS:
            return fail("quote_too_short", s["quote"])
        text = page_text(s["doc"], s["page"])
        if text is None or same_text(s["quote"]) not in same_text(text):
            return fail("quote_not_on_page", where)
        if not rule_sets.allowed(question, s["doc"], s["page"]):
            return fail("wrong_rule_set", f"{where} is not {rule_sets.asked(question)}")
        pieces = quoted_pieces(s, sent)
        # Quotes come from piece text, so titles are not used for the word check. Titles are
        # broad ("Visibility of Lights"): counting them would let a sidelight quote answer a
        # masthead light question.
        piece_words = key_words(" ".join(c.text for c in pieces))
        if question_words & piece_words and not question_words & key_words(s["quote"]):
            return fail("off_topic", f"quote has none of the question's words: {s['quote'][:60]}")
        titles += [c.title for c in pieces]

    unit = asked_unit(question)
    if unit and not any(t.startswith(unit[:UNIT_LETTERS]) for t in tokenize(answer)):
        return fail("unit_missing", f"question asks for {unit}")
    quotes = " ".join(s["quote"] for s in sources)
    missing = numbers_in(question) - numbers_in(quotes + " " + " ".join(titles))
    if missing:
        return fail("off_topic", f"question numbers not in the quote: {', '.join(sorted(missing))}")
    missing = numbers_in(answer) - numbers_in(quotes)
    if missing:
        return fail("number_not_in_quote", ", ".join(sorted(missing)))
    missing = number_units(answer) - number_units(quotes)
    if missing:
        return fail("unit_not_in_quote", ", ".join(f"{n} {u}" for n, u in sorted(missing)))
    extra = number_units(quotes) - number_units(answer) - number_units(question)
    if extra:
        return fail("quote_not_focused", "quote has other measurements: "
                    + ", ".join(f"{n} {u}" for n, u in sorted(extra)))
    return Proof(True)
