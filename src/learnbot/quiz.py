"""Quiz questions from one document. Rules: eval/quiz_rules.md. Any file.

The right answer passes the proof check (learnbot.study). The options are checked here;
a question that fails any check is dropped, never shown:

  bad_options     not exactly 3 wrong options + the right one; an empty option
  same_options    two options are the same, or one contains another
  banned_option   "all of the above", "none of the above", "both A and B" style
  partly_right_option  a wrong option lists several things and one is in the right answer
  wrong_in_quote  a wrong option is in the source quote, or all its number + unit pairs are:
                  the document may say it is right

Code cannot prove that each wrong option is wrong according to the document. The eval
report prints every kept question, for a person to read.
"""

import random
import re

from learnbot import study
from learnbot.proof import number_units

BANNED_OPTION = re.compile(r"\b(all|none) of (the above|these|the options|the answers)\b"
                           r"|\b(both|either|neither) [a-d]\b|\b[a-d] (and|or) [a-d]\b", re.IGNORECASE)
LIST_MARK = re.compile(r",|\b(and|or)\b", re.IGNORECASE)
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
    if not LIST_MARK.search(option):
        return False
    shared = set.intersection(*(option_words(o) for o in options))
    return bool((option_words(option) & option_words(answer)) - shared)


def options_problem(reply):
    """(check, detail) of the first failed option check, or None."""
    answer, wrong = reply["answer"], reply["wrong"]
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
    """One checked quiz question as a StudyItem, or "Not in this document"."""
    item = study.make_item(topic, searcher, chain, build_prompt, options_problem, pieces)
    if item.status == study.ANSWERED:
        item.options = [item.text, *item.wrong]
        random.Random(item.question).shuffle(item.options)  # same question, same order
        item.correct = item.options.index(item.text)
    return item


def make_quiz(topic, searcher, chain, count):
    """(questions, dropped, AI busy?): up to count different questions on the topic, or from
    across the document if topic is None."""
    return study.make_set(lambda t, s, pieces: make_question(t, s, chain, pieces), topic, searcher, count)
