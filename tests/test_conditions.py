"""The conditions rule: an answer never silently drops an "except ..." of its quote (fake AI)."""

import json

import pytest
from test_quiz import FakeChain, FakeSearcher

from learnbot import config
from learnbot.answer import ANSWERED, REFUSED, answer_is_quote, answer_question
from learnbot.book import make_chapter
from learnbot.chunking import Chunk
from learnbot.flashcards import make_card
from learnbot.proof import dropped_condition
from learnbot.quiz import make_question
from learnbot.reading import ask_page
from learnbot.research import research

QUOTE = "Any boat 16 feet and longer (except canoes and kayaks) must also carry one throwable PFD (Type IV)."
PIECE = Chunk("g.pdf", 13, "Life Jackets", QUOTE)
QUESTION = "What must any boat 16 feet and longer also carry?"
SHORT = "One throwable PFD (Type IV)."


def chat(answer=SHORT, quote=QUOTE):
    return json.dumps({"found": True, "answer": answer, "sources": [{"doc": "g.pdf", "page": 13, "quote": quote}]})


def item(answer=SHORT, question=QUESTION, wrong=()):
    return json.dumps({"found": True, "question": question, "answer": answer, "wrong": list(wrong),
                       "source": {"doc": "g.pdf", "page": 13, "quote": QUOTE}})


@pytest.mark.parametrize("quote, answer, question, dropped", [
    (QUOTE, SHORT, QUESTION, True),
    (QUOTE, "One throwable PFD, except on canoes and kayaks.", QUESTION, False),
    (QUOTE, SHORT, "What must boats carry, except canoes and kayaks?", False),
    ("It is allowed within 3 miles except in designated No Discharge Zone areas.", "Within 3 miles", "How far?", True),
    ("Wear it unless swimming in a designated area.", "Wear it", "What should I do?", True),
    ("A light may be used only if the vessel is at anchor.", "A light may be used", "What may be used?", True),
    ("Carry a whistle on every boat.", "A whistle", "What must be carried?", False),
    ("Use a horn, provided that it works.", "A horn", "What may be used?", True),
    ("Vessels other than canoes need a whistle.", "A whistle", "What do vessels need?", True),
    ("EXCEPT FOR KAYAKS, carry a whistle.", "A whistle", "What must be carried?", True),
])
def test_dropped_condition(quote, answer, question, dropped):
    assert bool(dropped_condition(answer, question, quote)) == dropped


def test_words_inside_other_words_are_not_conditions():
    assert not dropped_condition("A whistle", "What?", "The exception is a whistle for mother than others.")


# --- Chat -----------------------------------------------------------------------------
def test_real_case_chat_shows_the_exact_sentence():
    ans = answer_question(QUESTION, FakeSearcher([PIECE]), FakeChain(chat()))
    assert (ans.status, ans.text) == (ANSWERED, QUOTE) and answer_is_quote(ans)


def test_answer_that_keeps_the_condition_is_unchanged():
    keep = "One throwable PFD, except on canoes and kayaks."
    ans = answer_question(QUESTION, FakeSearcher([PIECE]), FakeChain(chat(keep)))
    assert ans.text == keep and not answer_is_quote(ans)


def test_answer_with_no_condition_is_unchanged():
    plain = Chunk("g.pdf", 2, "T", "Any boat must carry one whistle on board at all times.")
    text = json.dumps({"found": True, "answer": "One whistle", "sources": [{"doc": "g.pdf", "page": 2, "quote": plain.text}]})
    ans = answer_question("What must any boat carry?", FakeSearcher([plain]), FakeChain(text))
    assert ans.text == "One whistle" and not answer_is_quote(ans)


def test_very_long_sentence_is_refused_not_pasted(monkeypatch):
    monkeypatch.setattr(config, "MAX_SENTENCE_ANSWER_WORDS", 5)
    ans = answer_question(QUESTION, FakeSearcher([PIECE]), FakeChain(chat()))
    assert (ans.status, ans.reason) == (REFUSED, "condition_dropped")


def test_unproved_answer_is_still_refused_not_replaced():
    ans = answer_question(QUESTION, FakeSearcher([PIECE]), FakeChain(chat("Two throwable PFDs (Type IV).")))
    assert ans.status == REFUSED and ans.reason.startswith("proof:")


# --- The other features ---------------------------------------------------------------
def test_flashcard_shows_the_exact_sentence():
    card = make_card("throwable PFD", FakeSearcher([PIECE]), FakeChain(item()))
    assert (card.status, card.text) == (ANSWERED, QUOTE)


def test_flashcard_that_says_the_condition_on_its_front_is_unchanged():
    front = "Except canoes and kayaks, what must any boat 16 feet and longer carry?"
    assert make_card("throwable PFD", FakeSearcher([PIECE]), FakeChain(item(question=front))).text == SHORT


def test_quiz_question_is_dropped():
    wrong = ("Two whistles", "A gong", "A flare")
    q = make_question("throwable PFD", FakeSearcher([PIECE]), FakeChain(item(wrong=wrong)))
    assert (q.status, q.reason) == (REFUSED, "condition_dropped")


def test_quiz_question_that_states_the_condition_is_kept():
    wrong = ("Two whistles", "A gong", "A flare")
    front = "Except canoes and kayaks, what must any boat 16 feet and longer carry?"
    q = make_question("throwable PFD", FakeSearcher([PIECE]), FakeChain(item(question=front, wrong=wrong)))
    assert q.status == ANSWERED and q.text == SHORT


def test_book_fact_shows_the_exact_sentence():
    fact = {"question": QUESTION, "answer": SHORT, "source": {"doc": "g.pdf", "page": 13, "quote": QUOTE}}
    chapter = make_chapter("throwable PFD", FakeSearcher([PIECE]), FakeChain(json.dumps({"found": True, "facts": [fact]})))
    assert [f.text for f in chapter.facts] == [QUOTE]


def test_reading_mode_shows_the_exact_sentence():
    from learnbot.index import Document

    document = Document("g.pdf", "h", {13: QUOTE}, [PIECE])
    assert ask_page(QUESTION, document, 13, FakeChain(chat())).text == QUOTE


def test_research_is_unchanged(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STORAGE_DIR", str(tmp_path))
    url = "https://example.org/p"
    text = json.dumps({"found": True, "answer": SHORT, "sources": [{"doc": url, "page": 1, "quote": QUOTE}]})
    web = research(QUESTION, FakeChain(text), lambda q: [{"title": "t", "url": url, "content": QUOTE}])
    assert (web.status, web.text) == (ANSWERED, SHORT)
