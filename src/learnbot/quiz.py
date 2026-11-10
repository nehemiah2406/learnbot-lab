"""Quiz questions from one document. Rules: eval/quiz_rules.md. Any file.

The right answer passes the proof check (learnbot.study). The options are checked here;
a question that fails any check is dropped, never shown:

  bad_options     not exactly 3 wrong options + the right one; an empty option
  same_options    two options are the same, or one contains another
  banned_option   "all of the above", "none of the above", "both A and B" style
  partly_right_option  a wrong option lists several things and one is in the right answer
  wrong_in_quote  a wrong option is in the source quote, or all its number + unit pairs are:
                  the document may say it is right
  limit_dropped   the right answer leaves out the limit of its number in the quote ("more
                  than", "at least", "up to", "less than", "not more than"): "3000" when the
                  document says "more than 3000" is not exact (learnbot.proof.dropped_limit)

Code cannot prove that each wrong option is wrong according to the document. The eval
report prints every kept question, for a person to read.
"""

import random
import re
from time import perf_counter

from learnbot import config, study
from learnbot.proof import dropped_limit, number_units

BANNED_OPTION = re.compile(r"\b(all|none) of (the above|these|the options|the answers)\b"
                           r"|\b(both|either|neither) [a-d]\b|\b[a-d] (and|or) [a-d]\b", re.IGNORECASE)
LIST_MARK = re.compile(r",|\b(and|or)\b", re.IGNORECASE)
AND_PAIR = re.compile(r"\b(\w+) and \w+\b", re.IGNORECASE)
LIST_WORDS = {"and", "or", "a", "an", "the"}
WORD = re.compile(r"[a-z0-9]+(?:[.,][0-9]+)*")

PROMPT = """You write ONE multiple-choice question using ONLY the numbered pieces of text below, taken from the user's document.

Rules:
""" + study.SOURCE_RULES + """
10. "answer" is the one correct option, short, in simple English.
11. "wrong" has exactly 3 options that are clearly wrong according to the pieces, not just less good, and similar in form to the answer. None may be partly correct: a wrong option must not list several things if any of them is in the answer (if the answer is "B or C", do not write "A or B"). Do not write "all of the above" or "none of the above".

Reply with JSON only, in one of these two forms:
{{"found": true, "question": "...", "answer": "...", "wrong": ["...", "...", "..."], "source": {{"doc": "file.pdf", "page": 12, "quote": "..."}}}}
{{"found": false}}

Topic: {topic}

Pieces:
{pieces}
"""


def build_prompt(topic, pieces):
    blocks = [f"[{i}] doc: {c.doc} | page: {c.page} | title: {c.title}\n{c.text}"
              for i, c in enumerate(pieces, start=1)]
    return PROMPT.format(topic=(topic or "any clear fact in the pieces").strip(), pieces="\n\n".join(blocks))


def option_words(text):
    return set(WORD.findall(text.lower())) - LIST_WORDS


def is_partly_right(option, options, answer):
    """True if a wrong option lists several things and one of them is in the right answer
    ("Type I or II" when the answer is "Type II or III"). Words every option has ("Type") do
    not count. Real case: QUIZ-02."""
    # A pair the right answer has too is wording, not a list: "two separate and distinct
    # strokes" when the answer is "three separate and distinct strokes". Real case: QUIZ2-04.
    wording = AND_PAIR.sub(lambda m: m.group(1) if study.has_words(answer, m.group(0)) else m.group(0), option)
    if not LIST_MARK.search(wording):
        return False
    shared = set.intersection(*(option_words(o) for o in options))
    return bool((option_words(option) & option_words(answer)) - shared)


def options_problem(reply):
    """(check, detail) of the first failed option check, or None."""
    answer, wrong = reply["answer"], reply["wrong"]
    limit = dropped_limit(answer, reply.get("question", ""), reply["sources"][0]["quote"])
    if limit:
        return "limit_dropped", limit
    if len(wrong) != 3 or not all(wrong):
        return "bad_options", f"{len(wrong)} wrong options"
    options = [answer, *wrong]
    for i, a in enumerate(options):
        if any(study.has_words(b, a) for j, b in enumerate(options) if i != j):
            return "same_options", a
    for option in options:
        if BANNED_OPTION.search(option):
            return "banned_option", option
    for option in wrong:
        if is_partly_right(option, options, answer):
            return "partly_right_option", option
    quote = reply["sources"][0]["quote"]
    for option in wrong:
        pairs = number_units(option)
        if study.has_words(quote, option) or (pairs and pairs <= number_units(quote)):
            return "wrong_in_quote", option
    return None


def make_question(topic, searcher, chain, pieces=None):
    """One checked quiz question as a StudyItem, or "Not in this document". With no pieces
    given, a dropped question is tried again from other pieces, inside one time budget."""
    if pieces is not None:
        item = study.make_item(topic, searcher, chain, build_prompt, options_problem, pieces)
    else:
        item = question_with_retry(topic, searcher, chain)
    if item.status == study.ANSWERED:
        item.options = [item.text, *item.wrong]
        random.Random(item.question).shuffle(item.options)  # same question, same order
        item.correct = item.options.index(item.text)
    return item


def retry_pieces(found):
    """Other pieces for a second try: the next ones, or the second best alone. None if the
    topic has only one piece (the same prompt would get the same reply)."""
    first = config.PIECES_TO_LLM
    if len(found) > first:
        return found[first:first * 2]
    return [found[1]] if len(found) > 1 else None


def question_with_retry(topic, searcher, chain):
    """Up to config.QUIZ_TRIES_PER_QUESTION tries. A dropped question stays dropped if the AI
    is busy or no time is left for the next try."""
    start = perf_counter()
    found = study.topic_pieces(topic, searcher, config.QUIZ_SEARCH_PIECES)
    tries = [found[:config.PIECES_TO_LLM], retry_pieces(found)][:config.QUIZ_TRIES_PER_QUESTION]
    item = None
    for pieces in tries:
        left = config.QUESTION_TIME_BUDGET_S - (perf_counter() - start)
        if pieces is None or (item is not None and left < config.MIN_AI_TIME_S):
            break
        attempt = study.make_item(topic, searcher, chain, build_prompt, options_problem, pieces, left)
        if item is not None and attempt.status == study.AI_BUSY_STATUS:
            break
        item = attempt
        if item.status in (study.ANSWERED, study.AI_BUSY_STATUS):
            break
    item.seconds = perf_counter() - start
    return item


def make_quiz(topic, searcher, chain, count):
    """(questions, dropped, AI busy?): up to count different questions on the topic, or from
    across the document if topic is None."""
    return study.make_set(lambda t, s, pieces: make_question(t, s, chain, pieces), topic, searcher, count,
                          config.QUIZ_SET_TRIES_PER_QUESTION)
