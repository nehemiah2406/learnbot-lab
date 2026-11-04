"""Study items (quiz questions, flashcards) from one document: the steps they share.

search one document -> topic check -> AI writes the item -> checks -> keep or drop. Any file.
An item is kept only if ALL checks pass; otherwise the user sees "Not in this document".
Nothing is repaired or guessed. The AI's right answer goes through the same proof check as
a chat answer (learnbot.proof), with the item's question as the question. Extra checks:

  no_topic_words     every key word of the topic must be in one piece, or no AI is asked
  bad_shape          the reply has no question, answer or exactly one source
  answer_in_question the question gives away its own answer
  topic_not_in_quote the quote has none of the topic's key words
  rule_set_not_named the source page is from a rule set (International / Inland), and the
                     question does not say which one (eval/quiz_rules.md rule 8)

Each item has its own time budget (config.QUESTION_TIME_BUDGET_S), so items can be shown
as they are ready. Quiz rules: learnbot.quiz.
"""

import json
import re
from dataclasses import dataclass, field
from time import perf_counter

from learnbot import config, proof
from learnbot.answer import AI_BUSY_STATUS, ANSWERED, REFUSED, Answer, attempts_text
from learnbot.baseline import NOT_FOUND, tokenize
from learnbot.eval_check import normalize
from learnbot.llm import AllProvidersFailed

AI_BUSY_ITEM = "The AI is busy right now. Please try again in a minute."
FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$")

# Rules shared by every item prompt. Same meaning as the chat prompt (learnbot.answer).
SOURCE_RULES = """1. Use only the pieces. Do not use your own knowledge.
2. If the pieces have no clear fact about the topic, reply {{"found": false}}.
3. Copy numbers, units, lights and signals exactly as written. Never round, convert or spell out numbers.
4. "quote" must be copied word for word from ONE piece: only the one sentence or list item that holds the answer. Do not change any word or punctuation inside it.
5. "doc" and "page" must be those of the piece you quote.
6. In "answer", write numbers and number words exactly as they are written in your quote, and include every number of the quote that is not already in "question".
7. If the piece title names a rule set (for example International or Inland), "question" must name that rule set.
8. "question" must not contain the answer."""


@dataclass
class StudyItem(Answer):
    """An Answer (text = the right answer) plus the question side of the item."""

    question: str = ""
    wrong: list = field(default_factory=list)  # quiz only: the 3 wrong options
    options: list = field(default_factory=list)  # quiz only: 4 options, shuffled
    correct: int = -1  # quiz only: position of the right answer in options


def topic_stems(text):
    """Word stems (as in the proof check) and whole numbers of the text."""
    return {t[:proof.STEM_LETTERS] for t in tokenize(text) if t.isdigit() or (t.isalpha() and len(t) >= 3)}


def topic_words(topic, rule_sets):
    return topic_stems(topic) - {w.lower()[:proof.STEM_LETTERS] for w in rule_sets.words}


def topic_pieces(topic, searcher, k=None):
    """Pieces found for the topic that hold ALL its key words ([] = not in this document)."""
    words = topic_words(topic, searcher.rule_sets)
    if not words:
        return []
    return [c for c in searcher.search(topic, k) if words <= topic_stems(c.search_text)]


def spread_pieces(chunks, n):
    """n pieces evenly spread over the document, for a quiz with no topic. Short pieces and
    contents pages are skipped: they have no fact to ask about."""
    usable = [c for c in chunks if len(c.text.split()) >= config.STUDY_MIN_PIECE_WORDS and "...." not in c.text]
    step = max(len(usable) / n, 1) if n else 1
    return [usable[int(i * step)] for i in range(min(n, len(usable)))]


def parse_item(text):
    """The AI's JSON as {found, question, answer, wrong, sources}. Raises ValueError."""
    data = json.loads(FENCE.sub("", text or ""))
    if not isinstance(data, dict) or not isinstance(data.get("found"), bool):
        raise ValueError("reply has no found: true/false")
    if not data["found"]:
        return {"found": False}
    source = data["source"]
    sources = [{"doc": str(source["doc"]).strip(), "page": int(source["page"]), "quote": str(source["quote"])}]
    wrong = data.get("wrong") or []
    if not isinstance(wrong, list):
        raise ValueError("wrong is not a list")
    return {"found": True, "question": str(data.get("question") or "").strip(),
            "answer": str(data.get("answer") or "").strip(), "wrong": [str(w).strip() for w in wrong],
            "sources": sources}


def item_problem(topic, reply, rule_sets):
    """(check, detail) of the first failed shared check, or None."""
    question, answer = reply["question"], reply["answer"]
    source = reply["sources"][0]
    if not question or not answer:
        return "bad_shape", "no question or answer"
    if normalize(answer).lower().rstrip(".") in normalize(question).lower():
        return "answer_in_question", answer
    if topic and not topic_words(topic, rule_sets) & topic_stems(source["quote"]):
        return "topic_not_in_quote", source["quote"][:60]
    label = rule_sets.label(source["doc"], source["page"])
    if source["doc"] in rule_sets.docs_with_sets and label and rule_sets.asked(question) != label:
        return "rule_set_not_named", f"{source['doc']} p.{source['page']} is {label}"
    return None


def make_item(topic, searcher, chain, prompt, extra_check=None, pieces=None):
    """One checked StudyItem (never raises for AI errors). prompt(topic, pieces) -> text.
    topic None = any fact of the pieces given. extra_check(reply) -> (check, detail) or None."""
    start = perf_counter()
    if pieces is None:
        pieces = topic_pieces(topic, searcher)

    def done(status, text, **kw):
        return StudyItem(status, text, pieces, seconds=perf_counter() - start, **kw)

    if not pieces:
        return done(REFUSED, NOT_FOUND, reason="no_topic_words")
    budget = config.QUESTION_TIME_BUDGET_S - (perf_counter() - start)
    try:
        text, provider, cached = chain.ask(prompt(topic, pieces), budget_s=budget)
    except AllProvidersFailed as failed:
        return done(AI_BUSY_STATUS, AI_BUSY_ITEM, reason="ai_busy", detail=attempts_text(failed.attempts))
    info = {"provider": provider, "cached": cached, "attempts": attempts_text(getattr(chain, "last_attempts", []))}
    try:
        reply = parse_item(text)
    except (ValueError, KeyError, TypeError):
        return done(REFUSED, NOT_FOUND, reason="bad_json", **info)
    if not reply["found"]:
        return done(REFUSED, NOT_FOUND, reason="llm_not_found", **info)
    problem = item_problem(topic, reply, searcher.rule_sets) or (extra_check(reply) if extra_check else None)
    if problem:
        return done(REFUSED, NOT_FOUND, reason=problem[0], detail=problem[1], **info)
    reranker = getattr(searcher, "reranker", None)
    topic_score = (lambda q, t: float(reranker.scores(q, [t])[0])) if reranker else None
    result = proof.check(reply["question"], reply, pieces, searcher.library.page_text, searcher.rule_sets, topic_score)
    if not result.ok:
        return done(REFUSED, NOT_FOUND, reason=f"proof:{result.reason}", detail=result.detail, **info)
    sources = [{**s, "title": proof.quoted_pieces(s, pieces)[0].title} for s in result.sources]
    return done(ANSWERED, reply["answer"], sources=sources, question=reply["question"], wrong=reply["wrong"], **info)


def make_set(make_one, topic, searcher, count):
    """(kept items, items dropped, AI busy?). One piece per item, so items differ; at most
    config.STUDY_TRIES_PER_ITEM tries per item. Stops when the AI is busy."""
    tries = count * config.STUDY_TRIES_PER_ITEM
    pieces = topic_pieces(topic, searcher, tries) if topic else spread_pieces(searcher.chunks, tries)
    kept, dropped, seen = [], 0, set()
    for piece in pieces:
        if len(kept) == count:
            break
        item = make_one(topic, searcher, [piece])
        if item.status == AI_BUSY_STATUS:
            return kept, dropped, True
        quote = normalize(item.sources[0]["quote"]) if item.sources else ""
        if item.status == ANSWERED and quote not in seen:
            seen.add(quote)
            kept.append(item)
        else:
            dropped += 1
    return kept, dropped, False
