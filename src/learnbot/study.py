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
  condition_dropped  the answer and question leave out a condition of the quote ("except ...",
                     learnbot.proof.dropped_condition). A flashcard then shows the exact
                     sentence; a quiz question is dropped
  words_not_in_quote the answer has content words its quote does not have (rule 1, exact
                     answers; learnbot.proof.new_words). A flashcard or book fact then shows
                     the exact sentence. Quiz options are short by design: not checked for now

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
CONDITION_CHECK = "condition_dropped"
WORDS_CHECK = "words_not_in_quote"
FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$")

# Rules shared by every item prompt. Same meaning as the chat prompt (learnbot.answer).
SOURCE_RULES = """1. Use only the pieces. Do not use your own knowledge.
2. If the pieces have no clear fact about the topic, reply {{"found": false}}.
3. Copy numbers, units, lights and signals exactly as written. Never round, convert or spell out numbers.
4. "quote" must be copied word for word from ONE piece: only the one sentence or list item that holds the answer. Do not change any word or punctuation inside it.
5. "doc" and "page" must be those of the piece you quote.
6. In "answer", write numbers and number words exactly as they are written in your quote, and include every number of the quote that is not already in "question".
7. If the piece title names a rule set (for example International or Inland), "question" must name that rule set.
8. "question" must not contain the answer.
9. The quote must say the answer about the exact thing "question" asks. If it says it about something else, even something closely related, do not use it; if no quote fits, reply {{"found": false}}."""


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
    usable = usable or [c for c in chunks if len(c.text.split()) >= config.STUDY_MIN_ROW_WORDS and "...." not in c.text]
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
            "answer": proof.without_paragraph_number(str(data.get("answer") or "")).strip(), "wrong": [str(w).strip() for w in wrong],
            "sources": sources}


def plain(text):
    return normalize(text).lower().rstrip(".")


def has_words(text, part):
    """True if part is in the text as whole words ("5 years" is not in "15 years")."""
    return re.search(rf"(?<!\w){re.escape(plain(part))}(?!\w)", plain(text)) is not None


def item_problem(topic, reply, rule_sets):
    """(check, detail) of the first failed shared check, or None."""
    question, answer = reply["question"], reply["answer"]
    source = reply["sources"][0]
    if not question or not answer:
        return "bad_shape", "no question or answer"
    if has_words(question, answer):
        return "answer_in_question", answer
    if topic and not topic_words(topic, rule_sets) & topic_stems(source["quote"]):
        return "topic_not_in_quote", source["quote"][:60]
    label = rule_sets.label(source["doc"], source["page"])
    if source["doc"] in rule_sets.docs_with_sets and label and rule_sets.asked(question) != label:
        return "rule_set_not_named", f"{source['doc']} p.{source['page']} is {label}"
    return None


def check_reply(topic, reply, pieces, searcher, extra_check=None, exact_words=True):
    """(checked sources, "", "") if every check passes, else (None, failed check, detail).
    exact_words: also check that the answer has no content word its quote lacks."""
    problem = item_problem(topic, reply, searcher.rule_sets) or (extra_check(reply) if extra_check else None)
    if problem:
        return None, problem[0], problem[1]
    reranker = getattr(searcher, "reranker", None)
    topic_score = (lambda q, t: float(reranker.scores(q, [t])[0])) if reranker else None
    result = proof.check(reply["question"], reply, pieces, searcher.library.page_text, searcher.rule_sets, topic_score)
    if not result.ok:
        return None, f"proof:{result.reason}", result.detail
    checked = [{**s, "title": proof.quoted_pieces(s, pieces)[0].title, "where": proof.quoted_pieces(s, pieces)[0].where}
               for s in result.sources]
    condition = proof.dropped_condition(reply["answer"], reply["question"], proof.quote_text(checked[0]))
    if condition:
        return None, CONDITION_CHECK, condition
    extra = proof.new_words(reply["answer"], proof.quote_text(checked[0]))
    if exact_words and config.EXACT_WORDS_RULE and extra:
        return None, WORDS_CHECK, ", ".join(extra)
    return checked, "", ""


def check_with_sentence(topic, reply, pieces, searcher, sentence_checks=(), extra_check=None):
    """check_reply; if the only failure is one of sentence_checks, the answer becomes the
    document's exact sentence (without a leading paragraph number) and is checked again.
    Changes reply["answer"]. Only items that may show a sentence check exact words."""
    exact_words = WORDS_CHECK in sentence_checks
    result = check_reply(topic, reply, pieces, searcher, extra_check, exact_words)
    quote = proof.without_paragraph_number(reply["sources"][0]["quote"])
    if result[1] in sentence_checks and len(quote.split()) <= config.MAX_SENTENCE_ANSWER_WORDS:
        reply["answer"] = quote
        return check_reply(topic, reply, pieces, searcher, extra_check, exact_words)
    return result


def make_item(topic, searcher, chain, prompt, extra_check=None, pieces=None, budget_s=None, sentence_checks=()):
    """One checked StudyItem (never raises for AI errors). prompt(topic, pieces) -> text.
    topic None = any fact of the pieces given. extra_check(reply) -> (check, detail) or None.
    budget_s: seconds for this item (default config.QUESTION_TIME_BUDGET_S). sentence_checks:
    failed checks that show the document's exact sentence instead of dropping the item."""
    start = perf_counter()
    if pieces is None:
        pieces = topic_pieces(topic, searcher)

    def done(status, text, **kw):
        return StudyItem(status, text, pieces, seconds=perf_counter() - start, **kw)

    if not pieces:
        return done(REFUSED, NOT_FOUND, reason="no_topic_words")
    budget = (config.QUESTION_TIME_BUDGET_S if budget_s is None else budget_s) - (perf_counter() - start)
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
    sources, reason, detail = check_with_sentence(topic, reply, pieces, searcher, sentence_checks, extra_check)
    if reason:
        return done(REFUSED, NOT_FOUND, reason=reason, detail=detail, **info)
    return done(ANSWERED, reply["answer"], sources=sources, question=reply["question"], wrong=reply["wrong"], **info)


def nothing_kept(topic, dropped, noun):
    """What the user sees when a set has no items. dropped 0: no piece had the topic's words."""
    if not dropped:
        return NOT_FOUND
    if topic:
        return f"I found these words in the document, but could not make a {noun} I can prove from them. Try another topic."
    return f"I could not make a {noun} I can prove from this document."


def make_set(make_one, topic, searcher, count, tries_per_item=None):
    """(kept items, items dropped, AI busy?). One piece per item, so items differ; at most
    tries_per_item (default config.STUDY_TRIES_PER_ITEM) tries per item. Stops when the AI is busy."""
    tries = count * (tries_per_item or config.STUDY_TRIES_PER_ITEM)
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
