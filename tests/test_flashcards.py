"""Flashcards, with a fake AI (no network, no PDF). Shared steps are tested in test_quiz.py."""

import json

from test_quiz import PIECE, QUOTE, SECOND, SECOND_QUOTE, TOPIC, FakeChain, FakeSearcher

from learnbot.answer import AI_BUSY_STATUS, ANSWERED, REFUSED
from learnbot.baseline import NOT_FOUND
from learnbot.flashcards import build_prompt, make_card, make_cards


def card(question="How far apart must ladder rungs be?", answer="12 inches apart", page=5, quote=QUOTE):
    return json.dumps({"found": True, "question": question, "answer": answer,
                       "source": {"doc": "guide.pdf", "page": page, "quote": quote}})


def ask(text, topic=TOPIC):
    return make_card(topic, FakeSearcher([PIECE]), FakeChain(text))


def test_good_card_has_front_back_and_source():
    c = ask(card())
    assert c.status == ANSWERED and c.question.startswith("How far") and c.text == "12 inches apart"
    assert not c.options
    assert (c.sources[0]["doc"], c.sources[0]["page"], c.sources[0]["title"]) == ("guide.pdf", 5, "Portable Ladders")


def test_card_with_an_unproved_back_is_dropped():
    c = ask(card(answer="14 inches apart"))
    assert (c.status, c.text, c.reason) == (REFUSED, NOT_FOUND, "proof:number_not_in_quote")
    assert ask(card(quote="The rungs are 14 inches apart.")).reason == "proof:quote_not_on_page"


def test_card_that_gives_away_its_back_is_dropped():
    assert ask(card(question="Are ladder rungs 12 inches apart?")).reason == "answer_in_question"


def test_card_on_a_missing_topic_asks_no_ai():
    chain = FakeChain()
    c = make_card("ladder color", FakeSearcher([PIECE]), chain)
    assert (c.text, c.reason) == (NOT_FOUND, "no_topic_words") and chain.prompts == []


def test_busy_ai_gives_no_card():
    c = make_card(TOPIC, FakeSearcher([PIECE]), FakeChain(fail=True))
    assert c.status == AI_BUSY_STATUS and not c.sources


def test_prompt_asks_for_a_card_not_options():
    prompt = build_prompt(TOPIC, [PIECE])
    assert "ONE flashcard" in prompt and f"Topic: {TOPIC}" in prompt and '"wrong"' not in prompt


def test_cards_are_different_one_piece_each():
    second = card(question="How wide is the ladder base?", answer="40 inches", page=6, quote=SECOND_QUOTE)
    chain = FakeChain(card(), second)
    cards, dropped, busy = make_cards("ladder", FakeSearcher([PIECE, SECOND]), chain, 2)
    assert [c.text for c in cards] == ["12 inches apart", "40 inches"] and dropped == 0 and not busy
    assert SECOND_QUOTE not in chain.prompts[0]
