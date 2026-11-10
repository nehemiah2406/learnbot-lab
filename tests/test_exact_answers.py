"""Rule 1, exact answers: no leading paragraph number, and an answer with words its quote lacks
shows the document's exact sentence (chat, flashcards, book). Quiz options are not changed."""

import json

from learnbot import proof
from learnbot.answer import WORDS_NOT_IN_QUOTE, answer_with_conditions, not_exact, parse_reply

QUOTE = "(36) Squat denotes a change in trim of a ship underway, relative to her trim when stopped."
SOURCES = [{"doc": "a.pdf", "page": 2, "quote": QUOTE}]
QUESTION = "What does squat mean?"


def test_leading_paragraph_number_is_removed():
    assert proof.without_paragraph_number("(36) a change in trim") == "a change in trim"
    assert proof.without_paragraph_number("Rule (36) applies") == "Rule (36) applies"
    assert proof.without_paragraph_number("(a) In vessels") == "(a) In vessels"


def test_reply_answer_loses_its_paragraph_number():
    reply = json.dumps({"found": True, "answer": "(36) a change in trim", "sources": [{"doc": "a.pdf", "page": 2, "quote": QUOTE}]})
    assert parse_reply(reply)["answer"] == "a change in trim"


def test_words_not_in_the_quote_are_found():
    assert proof.new_words("Squat is a change in trim when moving", QUOTE) == ["movin"]
    assert proof.new_words("a change in trim of a ship underway", QUOTE) == []


def test_answer_with_new_words_becomes_the_exact_sentence_without_its_number():
    answer = "Squat is a change in trim of a ship when it is moving compared to when it is stopped."
    assert not_exact(QUESTION, answer, SOURCES) == WORDS_NOT_IN_QUOTE
    assert answer_with_conditions(QUESTION, answer, SOURCES) == QUOTE[5:]


def test_answer_made_only_of_quote_words_is_kept():
    assert answer_with_conditions(QUESTION, "A change in trim of a ship underway.", SOURCES) == "A change in trim of a ship underway."


def test_too_long_sentence_is_refused_not_shown_changed():
    long_quote = "Squat " + "word " * 70 + "stopped."
    assert answer_with_conditions(QUESTION, "Squat means moving.", [{"doc": "a.pdf", "page": 2, "quote": long_quote}]) is None


# --- Quiz: an answer must keep the limit of its number --------------------------------
LIMIT_QUOTE = "NOAA Tide Predictions allows the generation of predicted tides for more than 3000 locations along the U.S. coastline."


def test_answer_without_more_than_drops_the_limit():
    assert proof.dropped_limit("3000", "For how many locations can tides be predicted?", LIMIT_QUOTE) == "more than"


def test_answer_or_question_with_the_limit_is_fine():
    assert proof.dropped_limit("more than 3000", "For how many locations?", LIMIT_QUOTE) == ""
    assert proof.dropped_limit("3000", "Tides can be predicted for more than how many locations?", LIMIT_QUOTE) == ""


def test_each_limit_word_is_found():
    for limit in ("more than", "at least", "up to", "less than", "not more than"):
        quote = f"A vessel must carry {limit} 3 flares on board at all times."
        assert proof.dropped_limit("3 flares", "How many flares?", quote) == limit


def test_limit_word_not_before_a_number_is_ignored():
    quote = "Keep at least a safe distance, and carry 3 flares on board at all times."
    assert proof.dropped_limit("3 flares", "How many flares?", quote) == ""


def test_limit_before_a_number_word_counts():
    assert proof.dropped_limit("one", "How many lights?", "Show at least one white light at all times.") == "at least"


def test_quiz_question_that_drops_the_limit_is_dropped():
    from learnbot.quiz import options_problem
    reply = {"question": "For how many locations can tides be predicted?", "answer": "3000", "wrong": ["15", "1", "6"],
             "sources": [{"doc": "a.pdf", "page": 27, "quote": LIMIT_QUOTE}]}
    assert options_problem(reply) == ("limit_dropped", "more than")
    reply["answer"] = "More than 3000"
    reply["wrong"] = ["More than 15", "More than 1", "More than 6"]
    assert options_problem(reply) is None or options_problem(reply)[0] != "limit_dropped"


# --- Every document answer keeps the limit of its number (bug: book "3000") ----------
LIMIT_SOURCES = [{"doc": "coast.pdf", "page": 27, "quote": LIMIT_QUOTE}]


def test_chat_answer_without_the_limit_shows_the_sentence():
    question = "For how many locations can predicted tides be generated?"
    assert answer_with_conditions(question, "3000", LIMIT_SOURCES) == LIMIT_QUOTE
    assert answer_with_conditions(question, "More than 3000", LIMIT_SOURCES) == "More than 3000"


def test_book_fact_without_the_limit_shows_the_sentence():
    from learnbot.book import checked_fact
    from learnbot.chunking import Chunk
    from learnbot.rule_sets import RuleSets

    piece = Chunk("coast.pdf", 27, "Tides", LIMIT_QUOTE)

    class Searcher:
        rule_sets = RuleSets([piece])

        class library:
            @staticmethod
            def page_text(doc, page):
                return LIMIT_QUOTE if (doc, page) == ("coast.pdf", 27) else None

    raw = {"question": "For how many locations can predicted tides be generated?", "answer": "3000",
           "source": {"doc": "coast.pdf", "page": 27, "quote": LIMIT_QUOTE}}
    fact, reason = checked_fact("tide", raw, [piece], Searcher)
    assert reason == "" and fact.text == LIMIT_QUOTE
