"""Book maker, with a fake AI (no network, no PDF). Shared checks are tested in test_quiz.py."""

import importlib.util
import json
from pathlib import Path

import pytest
from test_quiz import PIECE, QUOTE, SECOND, SECOND_QUOTE, FakeChain, FakeSearcher

from learnbot import config
from learnbot.answer import AI_BUSY_STATUS, ANSWERED, REFUSED
from learnbot.baseline import NOT_FOUND
from learnbot.book import build_prompt, make_book, make_chapter, render, save_book
from learnbot.evaluate import MISSED, NOT_TESTED, REFUSED as TRAP_REFUSED, RIGHT, TRAP_ANSWERED

TOPIC = "ladder"


def fact(question="How far apart must ladder rungs be?", answer="12 inches apart", page=5, quote=QUOTE):
    return {"question": question, "answer": answer, "source": {"doc": "guide.pdf", "page": page, "quote": quote}}


SECOND_FACT = fact("How wide is the ladder base?", "40 inches", 6, SECOND_QUOTE)


def reply(*facts):
    return json.dumps({"found": True, "facts": list(facts)})


def chapter(text, topic=TOPIC, pieces=(PIECE, SECOND)):
    return make_chapter(topic, FakeSearcher(pieces), FakeChain(text))


# --- A chapter ------------------------------------------------------------------------
def test_chapter_keeps_proved_facts_with_page_and_quote():
    c = chapter(reply(fact(), SECOND_FACT))
    assert c.status == ANSWERED and [f.text for f in c.facts] == ["12 inches apart", "40 inches"] and c.dropped == 0
    s = c.facts[0].sources[0]
    assert (s["doc"], s["page"], s["quote"], s["title"]) == ("guide.pdf", 5, QUOTE, "Portable Ladders")


@pytest.mark.parametrize("bad, reason", [
    (fact(answer="14 inches apart"), "proof:number_not_in_quote"),
    (fact(quote="The ladder rungs must be spaced 14 inches apart along the side rails."), "proof:quote_not_on_page"),
    (fact(page=99), "proof:page_not_sent"),
    (fact(question="Are ladder rungs 12 inches apart?"), "answer_in_question"),
    ({"question": "No source?", "answer": "12 inches"}, "bad_fact"),
    ("not a fact", "bad_fact"),
])
def test_one_bad_fact_is_dropped_and_the_good_one_stays(bad, reason):
    c = chapter(reply(bad, SECOND_FACT))
    assert [f.text for f in c.facts] == ["40 inches"] and c.dropped == 1 and reason in c.reason


def test_same_quote_twice_is_kept_once():
    c = chapter(reply(fact(), fact(question="What is the rung spacing?", answer="12 inches")))
    assert len(c.facts) == 1 and c.dropped == 1 and c.reason == "same_quote"


def test_too_many_facts_are_cut(monkeypatch):
    monkeypatch.setattr(config, "BOOK_FACTS_PER_CHAPTER", 1)
    assert len(chapter(reply(fact(), SECOND_FACT)).facts) == 1


def test_topic_words_missing_asks_no_ai():
    chain = FakeChain()
    c = make_chapter("ladder color", FakeSearcher([PIECE]), chain)
    assert (c.status, c.text, c.reason, c.facts) == (REFUSED, NOT_FOUND, "no_topic_words", []) and chain.prompts == []


def test_ai_finds_nothing_or_bad_json_is_not_in_this_document():
    assert (chapter('{"found": false}').text, chapter('{"found": false}').reason) == (NOT_FOUND, "llm_not_found")
    assert chapter("not json").reason == "bad_json"
    assert chapter('{"found": true, "facts": "x"}').reason == "bad_json"
    assert chapter('{"found": true, "facts": []}').reason == "llm_not_found"


def test_all_facts_dropped_says_the_words_were_found():
    c = chapter(reply(fact(answer="14 inches apart")))
    assert c.status == REFUSED and not c.facts and c.dropped == 1 and "found these words" in c.text


def test_busy_ai_is_a_friendly_message():
    c = make_chapter(TOPIC, FakeSearcher([PIECE]), FakeChain(fail=True))
    assert c.status == AI_BUSY_STATUS and "try again" in c.text and "timeout" in c.detail and not c.facts


def test_chapter_has_its_own_time_budget():
    chain = FakeChain(reply(fact()))
    make_chapter(TOPIC, FakeSearcher([PIECE]), chain)
    assert 0 < chain.budget_s <= config.QUESTION_TIME_BUDGET_S


def test_prompt_has_the_rules_topic_and_pieces():
    prompt = build_prompt(TOPIC, [PIECE])
    assert f"Topic: {TOPIC}" in prompt and QUOTE in prompt and "about the exact thing" in prompt
    assert f"up to {config.BOOK_FACTS_PER_CHAPTER} different facts" in prompt


# --- A book ---------------------------------------------------------------------------
def test_book_has_one_chapter_per_topic_in_order():
    chapters = make_book(["ladder", "  ", "ladder color"], FakeSearcher([PIECE]), FakeChain(reply(fact())))
    assert [c.topic for c in chapters] == ["ladder", "ladder color"]
    assert [bool(c.facts) for c in chapters] == [True, False]


@pytest.mark.parametrize("topics", [[], ["  "], ["t"] * (config.BOOK_MAX_TOPICS + 1)])
def test_wrong_number_of_topics_is_a_clear_error(topics):
    with pytest.raises(ValueError, match="1 to"):
        make_book(topics, FakeSearcher([PIECE]), FakeChain())


def test_render_shows_every_fact_with_page_section_and_quote_and_says_what_is_missing():
    chapters = make_book(["ladder", "ladder color"], FakeSearcher([PIECE]), FakeChain(reply(fact())))
    text = render("guide.pdf", chapters)
    assert "# Study book: guide.pdf" in text and "## ladder" in text and "12 inches apart" in text
    assert "Page 5 (Portable Ladders)" in text and f'"{QUOTE}"' in text
    assert "## ladder color" in text and NOT_FOUND in text


def test_book_is_saved_and_the_same_topics_use_the_same_file(tmp_path):
    chapters = make_book(["ladder"], FakeSearcher([PIECE]), FakeChain(reply(fact())))
    path = save_book("guide file.pdf", chapters, tmp_path)
    assert path.parent == tmp_path / "books" and path.name.startswith("guide-file-") and path.suffix == ".md"
    assert "12 inches apart" in path.read_text(encoding="utf-8")
    assert save_book("guide file.pdf", chapters, tmp_path) == path
    other = make_book(["ladder rungs"], FakeSearcher([PIECE]), FakeChain(reply(fact())))
    assert save_book("guide file.pdf", other, tmp_path) != path


# --- Scoring --------------------------------------------------------------------------
@pytest.fixture
def script(monkeypatch):
    folder = Path(__file__).resolve().parents[1] / "scripts"
    spec = importlib.util.spec_from_file_location("run_book_eval", folder / "run_book_eval.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ROW = {"doc": "guide.pdf", "id": "B", "question": "ladder", "type": "number", "expected_answer": "12 inches",
       "page": "5", "source_quote": QUOTE, "accepted_sources": "guide.pdf:5", "other_answers": ""}


def test_chapter_scoring(script):
    assert script.score_chapter(ROW, False, chapter(reply(SECOND_FACT, fact())))[0] == RIGHT
    assert script.score_chapter(ROW, False, chapter(reply(SECOND_FACT))) == (MISSED, "expected fact not in the chapter")
    assert script.score_chapter(ROW, False, chapter('{"found": false}'))[0] == MISSED
    assert script.score_chapter(ROW, True, chapter(reply(fact())))[0] == TRAP_ANSWERED
    assert script.score_chapter(ROW, True, chapter('{"found": false}'))[0] == TRAP_REFUSED
    busy = make_chapter(TOPIC, FakeSearcher([PIECE]), FakeChain(fail=True))
    assert script.score_chapter(ROW, False, busy)[0] == NOT_TESTED


def test_report_keeps_hard_traps_out_of_the_table_of_numbers(script):
    good = chapter(reply(fact()))
    hard = chapter(reply(SECOND_FACT))
    records = [{"row": ROW, "trap": False, "hard": False, "chapter": good, "outcome": RIGHT, "reason": ""},
               {"row": {**ROW, "id": "H"}, "trap": True, "hard": True, "chapter": hard, "outcome": TRAP_ANSWERED, "reason": ""}]
    report = script.build_report(records, 2, [])
    assert "Gate: PASS" in report and "| 1/1 | 0 | 0/0 |" in report and "hard trap" in report and "40 inches" in report
