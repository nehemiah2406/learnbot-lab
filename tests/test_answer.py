"""Answer flow and Phase 4 scoring with a fake AI and fake search (no network, no PDF)."""

import json

import pytest

from learnbot.answer import AI_BUSY_STATUS, ANSWERED, REFUSED, Answer, answer_question, build_prompt, parse_reply
from learnbot.baseline import NOT_FOUND
from learnbot.chunking import Chunk
from learnbot.evaluate import (
    CORRECT_OTHER, MISSED, NOT_TESTED, RIGHT, TRAP_ANSWERED, WRONG, numbers_differ, score_answer,
)
from learnbot.evaluate import REFUSED as TRAP_REFUSED
from learnbot.llm import AI_BUSY, AllProvidersFailed, CallLimitReached
from learnbot.rule_sets import RuleSets

PIECE = Chunk("guide.pdf", 16, "Pyrotechnic Devices",
              "Check the expiration date (42 months after the date of manufacture).")
OTHER = Chunk("other.pdf", 3, "Flares", "Check the expiration date (42 months after the date of manufacture).")
QUESTION = "When do pyrotechnic signals expire?"
QUOTE = "Check the expiration date (42 months after the date of manufacture)."


class FakeLibrary:
    def page_text(self, doc, page):
        return {("guide.pdf", 16): PIECE.text, ("other.pdf", 3): OTHER.text}.get((doc, page))


class FakeSearcher:
    def __init__(self, pieces):
        self.pieces = pieces
        self.library = FakeLibrary()
        self.rule_sets = RuleSets(pieces)

    def search(self, question):
        return self.pieces


class FakeChain:
    def __init__(self, reply=None, fail=False):
        self.reply, self.fail, self.prompts = reply, fail, []

    def ask(self, prompt, budget_s=None):
        self.prompts.append(prompt)
        self.budget_s = budget_s
        if self.fail == "limit":
            raise CallLimitReached(4)
        if self.fail:
            raise AllProvidersFailed([("gemini:x", "rate_limit", 0.3), ("groq:y", "timeout", 15.0)])
        return self.reply, "gemini:x", False


def found(answer="42 months after the date of manufacture.", doc="guide.pdf", page=16, quote=QUOTE):
    return json.dumps({"found": True, "answer": answer, "sources": [{"doc": doc, "page": page, "quote": quote}]})


def ask(reply=None, pieces=(PIECE,), fail=False):
    return answer_question(QUESTION, FakeSearcher(list(pieces)), FakeChain(reply, fail))


# --- Answer flow ----------------------------------------------------------------------
def test_checked_answer_is_shown_with_source_title_from_piece():
    ans = ask(found())
    assert ans.status == ANSWERED and ans.text.startswith("42 months")
    assert ans.sources[0]["title"] == "Pyrotechnic Devices" and ans.provider == "gemini:x"


def test_llm_not_found_gives_not_in_this_document():
    ans = ask('{"found": false}')
    assert (ans.status, ans.text, ans.reason) == (REFUSED, NOT_FOUND, "llm_not_found")


def test_bad_json_gives_not_in_this_document():
    assert ask("Sure! The answer is 42 months.").reason == "bad_json"
    assert ask('{"answer": "42 months"}').reason == "bad_json"


def test_proof_failure_is_never_repaired():
    ans = ask(found(answer="36 months after manufacture."))
    assert (ans.status, ans.text, ans.reason) == (REFUSED, NOT_FOUND, "proof:number_not_in_quote")


def test_ai_busy_shows_pieces_not_an_answer():
    ans = ask(fail=True)
    assert ans.status == AI_BUSY_STATUS and ans.text == AI_BUSY and ans.pieces == [PIECE]
    assert "rate_limit" in ans.detail and not ans.sources


def test_call_limit_stops_the_run_instead_of_ai_busy():
    # The limit is an eval-run stop, not an answer: it must not become "AI busy".
    with pytest.raises(CallLimitReached):
        ask(fail="limit")


def test_no_pieces_means_no_ai_call():
    chain = FakeChain(found())
    ans = answer_question(QUESTION, FakeSearcher([]), chain)
    assert ans.reason == "no_pieces" and chain.prompts == []


def test_prompt_has_question_and_labelled_pieces():
    prompt = build_prompt(QUESTION, [PIECE])
    assert QUESTION in prompt and "doc: guide.pdf | page: 16 | title: Pyrotechnic Devices" in prompt


def test_parse_reply_accepts_code_fence_and_string_page():
    text = '```json\n{"found": true, "answer": "a", "sources": [{"doc": "x.pdf", "page": "12", "quote": "q"}]}\n```'
    assert parse_reply(text)["sources"][0]["page"] == 12
    with pytest.raises(ValueError):
        parse_reply("not json")


# --- Phase 4 scoring ------------------------------------------------------------------
ROW = {"doc": "guide.pdf", "page": "16", "question": QUESTION,
       "expected_answer": "42 months after the date of manufacture.", "source_quote": QUOTE}


def test_score_right_wrong_number_and_other_source():
    assert score_answer(ROW, False, ask(found()))[0] == RIGHT
    other = ask(found(doc="other.pdf", page=3), pieces=(PIECE, OTHER))
    assert score_answer(ROW, False, other) == (CORRECT_OTHER, "from other.pdf p.3")
    wrong_number = ask(found(answer="42 months or 4 years.", quote=QUOTE + " Replace after 4 years."))
    wrong_number.status, wrong_number.text = ANSWERED, "42 months or 4 years."  # as if it had passed
    assert score_answer(ROW, False, wrong_number)[0] == WRONG


def test_score_missed_names_the_reason():
    assert score_answer(ROW, False, ask('{"found": false}')) == (MISSED, "llm_not_found")
    outcome, reason = score_answer(ROW, False, ask('{"found": false}', pieces=(OTHER,)))
    assert outcome == MISSED and reason.startswith("search miss")


def test_score_traps():
    assert score_answer(ROW, True, ask('{"found": false}'))[0] == TRAP_REFUSED
    assert score_answer(ROW, True, ask(found()))[0] == TRAP_ANSWERED


def test_ai_busy_is_not_tested_never_a_pass():
    busy = ask(fail=True)
    assert score_answer(ROW, True, busy)[0] == NOT_TESTED  # not "refused"
    assert score_answer(ROW, False, busy)[0] == NOT_TESTED


def test_numbers_differ():
    assert not numbers_differ("A blast of from 4 to 6 seconds", "four to six seconds", "How long?")
    assert numbers_differ("6 miles", "5 miles", "How far?")
    assert numbers_differ("6 miles; about 1.15 statute miles", "6 miles", "How far?")  # missing number
    assert not numbers_differ("6 miles", "On a 50 m vessel: 6 miles", "Vessel of 50 m, how far?")


# --- Reserved rules and the time budget --------------------------------------------------
def test_reserved_rule_is_answered_without_the_ai():
    piece = Chunk("rules.pdf", 87, "—INLAND— Lights and Shapes Rule 28", "[Reserved]")

    class Lib:
        def page_text(self, doc, page):
            return "—INLAND—\nLights and Shapes\nRule 28\n[Reserved]\n87"

    searcher = FakeSearcher([piece])
    searcher.library = Lib()
    chain = FakeChain(found())
    ans = answer_question("What does Rule 28 of the Inland Rules say?", searcher, chain)
    assert ans.status == ANSWERED and "reserved" in ans.text.lower() and chain.prompts == []
    assert ans.sources[0]["page"] == 87 and ans.sources[0]["quote"] == "Rule 28 [Reserved]"
    assert ans.provider == "code:reserved"


def test_ai_gets_the_time_left_of_the_question_budget():
    chain = FakeChain(found())
    answer_question(QUESTION, FakeSearcher([PIECE]), chain)
    from learnbot import config
    assert 0 < chain.budget_s <= config.QUESTION_TIME_BUDGET_S


def test_other_answer_from_its_own_page_counts_as_right():
    row = {"doc": "pilot.pdf", "page": "2", "question": "How long is a nautical mile?", "accepted_sources": "pilot.pdf:2",
           "expected_answer": "One minute of latitude, or approximately 2,000 yards; about 1.15 statute miles.",
           "source_quote": "A nautical mile is one minute of latitude, or approximately 2,000 yards",
           "other_answers": "pilot.pdf:34=nautical mile - 1,852 meters / 6,076.12 feet"}
    p34 = {"doc": "pilot.pdf", "page": 34, "quote": "nautical mile - 1,852 meters / 6,076.12 feet"}
    ans = Answer(ANSWERED, "1,852 meters / 6,076.12 feet", [], sources=[p34])
    assert score_answer(row, False, ans)[0] == RIGHT
    # Same page, but numbers that are not that other answer: still wrong.
    ans = Answer(ANSWERED, "1,800 meters", [], sources=[p34])
    assert score_answer(row, False, ans)[0] == WRONG
