"""Proof check: code (not the AI) decides if an AI answer may be shown. Any PDF.

An answer is shown only if ALL checks pass for every source; otherwise the user sees
"Not in this document". The answer text is never repaired or guessed. Checks, in order:

  no_answer          the reply has an answer and at least one source
  too_many_sources   one source per answer, unless the question compares (it names two
                     rule sets, or says compare / both / difference / versus)
  page_not_sent      the source's doc + page is one of the pieces sent to the AI
  quote_too_short    the quote has at least config.MIN_QUOTE_WORDS words
  quote_not_on_page  the quote appears word for word (normalised) on that doc + page
  wrong_rule_set     the question names a rule set -> the page has that rule set
  (list item)        a quote that is a list ("In vessels of 50 meters: - a masthead light,
                     6 miles; - a sidelight, 3 miles") is narrowed to the ONE item that holds
                     all the answer's numbers + units, with the list's lead-in kept. Only if
                     exactly one item does, and the item is on the page. This narrows the
                     proof; the answer is not changed. All checks below use the narrowed quote.
  off_topic          the quote fits the question: if the question's key words occur in the
                     piece text, one must occur in the quote (not just in the broad piece
                     title or a list lead-in; words compared by their first 5 letters). A paraphrased question
                     with no shared word passes only if the re-ranker scores the question and
                     the quote at least config.TOPIC_MIN_SCORE. Numbers in the question must be
                     in a quote or in the title of the piece quoted
  unit_missing       a question that asks for a unit ("how many yards", "... in km?") gets
                     an answer with that unit
  number_not_in_quote  every number in the answer is in a quote
  unit_not_in_quote  every measurement in the answer ("6 miles", "200 Hz", "$5") is in a quote
  quote_not_focused  every number in the quote is in the answer or the question: each
                     measurement ("3 miles") and each count ("one all-round light", "two
                     short blasts"). An answer cannot drop "one" or pick the wrong list item
                     unseen. References ("Rule 22", "33 CFR", "(26)") are not numbers here.
After the check, the callers show the exact sentence instead of the answer when the answer drops
a condition (dropped_condition) or has content words its quote does not have (new_words).
A measurement is a number WITH a unit from learnbot.units; "33 CFR", "Rule 34(d)" or
"Annex 1" are references, not measurements.
"""

import re
from dataclasses import dataclass, field

from learnbot import config
from learnbot.baseline import tokenize
from learnbot.eval_check import normalize, numbers_in
from learnbot.rule_sets import words_in
from learnbot.units import asked_unit, counts, measurements, number_values, units_in

# Lines are joined with spaces in pieces, so "look-\nout" becomes "look- out".
BROKEN_HYPHEN = re.compile(r"(\w)- (\w)")
COMPARE_WORDS = re.compile(r"\b(compare[sd]?|comparison|both|differ|differs|difference|differences|"
                           r"versus|vs)\b", re.IGNORECASE)
# List items: split at bullets / dashes between spaces, at ";" and before "(ii)"-style markers.
BULLET = re.compile(r"^[−–•▪·-]\s+")
ITEM_BREAK = re.compile(r"\s*(?:(?:^|\s)[−–•▪·-]\s+|;\s*|\s(?=\((?:[ivx]+|[a-z]|\d+)\)\s))")


# A limit before a number: "more than 3000 locations". An answer of "3000" without it is not exact.
NUMBER_WORDS = r"one|two|three|four|five|six|seven|eight|nine|ten|twelve|fifteen|twenty|fifty|hundred"
LIMIT = re.compile(rf"\b(not more than|more than|less than|at least|up to)\s+(?=\$?\d|(?:{NUMBER_WORDS})\b)", re.IGNORECASE)
PARAGRAPH_NUMBER = re.compile(r"^\s*\(\d+\)\s*")
CONDITION = re.compile(r"\b(except|unless|only if|provided that|other than|excluding)\b([^.;,)]*)", re.IGNORECASE)


def same_text(text):
    return BROKEN_HYPHEN.sub(r"\1-\2", normalize(text))


def number_units(text):
    """{(number, canonical unit)}: only a number WITH a known unit ("6 miles", "$5");
    "33 CFR" or "Rule 34" are not measurements (see learnbot.units)."""
    return measurements(same_text(text))


def quote_numbers(text):
    """Numbers that must be explained by the answer: measurements and counts."""
    return {n for n, _ in number_units(text)} | counts(same_text(text))


STEM_LETTERS = 5  # "expire" / "expiration" and "signal" / "signals" count as the same word


def key_words(text, ignore=()):
    """Word stems (first STEM_LETTERS letters) of the content words of 3+ letters."""
    ignore = {w.lower() for w in ignore}
    return {t[:STEM_LETTERS] for t in tokenize(text) if t.isalpha() and len(t) >= 3 and t not in ignore}


def compares(question, rule_sets):
    """True if the question compares two things (then one source per side is allowed)."""
    return bool(COMPARE_WORDS.search(question)) or len(words_in(question, rule_sets.words)) >= 2


def quote_text(source):
    """The text a source proves: its list lead-in (if narrowed) plus its quote."""
    return f"{source.get('lead', '')} {source['quote']}".strip()


def dropped_condition(answer, question, quote):
    """The condition of the quote that the answer leaves out, or "". A short answer can be
    false without it: "any boat 16 feet and longer" drops "(except canoes and kayaks)". Only
    conditions with these words; the key words must be in the answer or the question."""
    have = key_words(f"{answer} {question}")
    for match in CONDITION.finditer(same_text(quote)):
        if not key_words(match.group(2)) <= have:
            return match.group(0).strip()
    return ""


def dropped_limit(answer, question, quote):
    """The limit of a number in the quote ("more than", "at least", "up to", ...) that the answer
    and question both leave out, or "". "3000" for "more than 3000 locations" is not exact."""
    have = same_text(f"{answer} {question}").lower()
    for match in LIMIT.finditer(same_text(quote)):
        if match.group(1).lower() not in have:
            return match.group(1)
    return ""


def without_paragraph_number(text):
    """The text without a leading paragraph number: "(36) Squat denotes ..." -> "Squat denotes ..."."""
    return PARAGRAPH_NUMBER.sub("", text or "")


def new_words(answer, quote):
    """Content words of the answer that its quote does not have, compared by their first
    STEM_LETTERS letters ("moving" when the quote says "underway"). Numbers are checked elsewhere."""
    return sorted(key_words(answer) - key_words(quote))


def shown_where(source):
    """The location as shown to the user: "p.12", or "Row 4" in a file with no pages."""
    return source.get("where") or f"p.{source['page']}"


def shown_quote(source):
    """The quote as shown to the user: "lead-in ... item" when narrowed to one list item."""
    return f"{source['lead']} … {source['quote']}" if source.get("lead") else source["quote"]


@dataclass
class Proof:
    ok: bool
    reason: str = ""  # name of the first failed check
    detail: str = ""
    sources: list = field(default_factory=list)  # checked sources (list quotes narrowed)


def fail(reason, detail=""):
    return Proof(False, reason, detail)


def quoted_pieces(source, sent):
    """Pieces sent from the source's page that contain the quote (else all from that page)."""
    page_pieces = [c for c in sent if (c.doc, c.page) == (source["doc"], source["page"])]
    quote = same_text(source["quote"])
    return [c for c in page_pieces if quote in same_text(c.search_text)] or page_pieces


def list_items(quote):
    """(lead-in, items) of a quote that is a list, else ("", [])."""
    parts = [BULLET.sub("", p.strip(" ;")) for p in ITEM_BREAK.split(quote)]
    parts = [p for p in parts if p]
    lead = parts[0] if parts and parts[0].endswith(":") else ""
    items = parts[1:] if lead else parts
    return (lead, items) if len(items) >= 2 else ("", [])


def unexplained(text, answer, question):
    return quote_numbers(text) - number_values(answer) - number_values(question)


def narrowed(source, answer, question, page_text):
    """The source narrowed to the one list item holding all the answer's numbers + units,
    or the source unchanged (then the focus check decides)."""
    if not unexplained(source["quote"], answer, question):
        return source
    lead, items = list_items(source["quote"])
    need_units, need_numbers = number_units(answer), numbers_in(answer)
    matches = [item for item in items
               if need_units <= number_units(f"{lead} {item}") and need_numbers <= numbers_in(f"{lead} {item}")]
    if len(matches) != 1:
        return source
    page = same_text(page_text(source["doc"], source["page"]) or "")
    if any(part and same_text(part) not in page for part in (lead, matches[0])):
        return source
    return {**source, "quote": matches[0], "lead": lead, "full_quote": source["quote"]}


def check(question, reply, sent, page_text, rule_sets, topic_score=None):
    """Proof for one parsed AI reply. page_text(doc, page) -> full page text or None.
    topic_score(question, text) -> number (re-ranker score), optional."""
    answer = (reply.get("answer") or "").strip()
    sources = reply.get("sources") or []
    if not answer or not sources:
        return fail("no_answer")
    if len(sources) > 1 and not compares(question, rule_sets):
        return fail("too_many_sources", f"{len(sources)} sources; the question does not compare")
    sent_pages = {(c.doc, c.page) for c in sent}
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

    sources = [narrowed(s, answer, question, page_text) for s in sources]
    question_words = key_words(question, ignore=rule_sets.words)
    titles = []
    for s in sources:
        pieces = quoted_pieces(s, sent)
        # Quotes come from piece text, so titles are not used for the word check. Titles are
        # broad ("Visibility of Lights"): counting them would let a sidelight quote answer a
        # masthead light question.
        piece_words = key_words(" ".join(c.text for c in pieces))
        # A narrowed list item must fit by itself: the lead-in ("In vessels of 50 meters:")
        # is shared by every item of the list.
        if question_words & piece_words and not question_words & key_words(s["quote"]):
            use_score = topic_score is not None and config.TOPIC_MIN_SCORE is not None
            score = topic_score(question, quote_text(s)) if use_score else None
            if score is None or score < config.TOPIC_MIN_SCORE:
                detail = f"quote has none of the question's words: {quote_text(s)[:60]}"
                return fail("off_topic", detail + (f" (topic score {score:.2f})" if score is not None else ""))
        titles += [c.title for c in pieces]

    unit = asked_unit(question)
    if unit and unit not in units_in(same_text(answer)):
        return fail("unit_missing", f"question asks for {unit}")
    quotes = " ".join(quote_text(s) for s in sources)
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
    extra = unexplained(quotes, answer, question)
    if extra:
        return fail("quote_not_focused", "quote has numbers the answer leaves out: " + ", ".join(sorted(extra)))
    return Proof(True, sources=sources)
