"""Quiz questions and the shared study steps, with a fake AI (no network, no PDF)."""

import importlib.util
import json
from pathlib import Path

import pytest

from learnbot.answer import AI_BUSY_STATUS, ANSWERED, REFUSED
from learnbot.baseline import NOT_FOUND
from learnbot.chunking import Chunk
from learnbot.evaluate import CORRECT_OTHER, MISSED, NOT_TESTED, RIGHT, TRAP_ANSWERED, WRONG, feature_gate, score_answer
from learnbot.index import Document, Library
from learnbot.llm import AllProvidersFailed, CallLimitReached
from learnbot.quiz import build_prompt, make_question, make_quiz, options_problem
from learnbot.rule_sets import RuleSets
from learnbot.search import Searcher
from learnbot.study import AI_BUSY_ITEM, nothing_kept, parse_item, spread_pieces, topic_pieces

QUOTE = "The ladder rungs must be spaced 12 inches apart along the side rails."
PIECE = Chunk("guide.pdf", 5, "Portable Ladders", QUOTE)
SECOND_QUOTE = "The ladder feet must rest on a level base of 40 inches."
SECOND = Chunk("guide.pdf", 6, "Portable Ladders", SECOND_QUOTE)
INTL = Chunk("rules.pdf", 7, "Rule 1 INTERNATIONAL", "A whistle signal shall last 4 seconds in all conditions.")
INLAND = Chunk("rules.pdf", 8, "Rule 1 INLAND", "A whistle signal shall last 6 seconds in all conditions.")
TOPIC = "ladder rungs"


class FakeLibrary:
    def __init__(self, pieces):
        self.texts = {(c.doc, c.page): c.text for c in pieces}

    def page_text(self, doc, page):
        return self.texts.get((doc, page))


class FakeSearcher:
    def __init__(self, pieces):
        self.chunks = list(pieces)
        self.library = FakeLibrary(pieces)
        self.rule_sets = RuleSets(pieces)

    def search(self, question, k=None):
        return self.chunks[:k] if k else self.chunks


class FakeChain:
    def __init__(self, *replies, fail=False):
        self.replies, self.fail, self.prompts, self.calls = list(replies), fail, [], 0

    def ask(self, prompt, budget_s=None):
        self.prompts.append(prompt)
        self.budget_s = budget_s
        if self.fail == "limit":
            raise CallLimitReached(4)
        if self.fail:
            raise AllProvidersFailed([("gemini:x", "timeout", 5.0)])
        return self.replies.pop(0), "gemini:x", False


def reply(question="How far apart must ladder rungs be?", answer="12 inches apart", doc="guide.pdf", page=5,
          quote=QUOTE, wrong=("8 inches apart", "20 inches apart", "30 inches apart")):
    return json.dumps({"found": True, "question": question, "answer": answer, "wrong": list(wrong),
                       "source": {"doc": doc, "page": page, "quote": quote}})


def ask(text, topic=TOPIC, pieces=(PIECE,)):
    return make_question(topic, FakeSearcher(pieces), FakeChain(text))


# --- A good question ------------------------------------------------------------------
def test_good_question_is_kept_with_four_options_and_source():
    q = ask(reply())
    assert q.status == ANSWERED and q.text == "12 inches apart"
    assert sorted(q.options) == sorted(["12 inches apart", "8 inches apart", "20 inches apart", "30 inches apart"])
    assert q.options[q.correct] == "12 inches apart"
    s = q.sources[0]
    assert (s["doc"], s["page"], s["title"]) == ("guide.pdf", 5, "Portable Ladders")


def test_same_question_keeps_the_same_option_order():
    assert ask(reply()).options == ask(reply()).options


def test_ai_gets_a_time_budget():
    chain = FakeChain(reply())
    make_question(TOPIC, FakeSearcher([PIECE]), chain)
    assert 0 < chain.budget_s <= 9


def test_prompt_has_topic_and_pieces():
    prompt = build_prompt("ladder rungs", [PIECE])
    assert "Topic: ladder rungs" in prompt and "doc: guide.pdf | page: 5" in prompt and QUOTE in prompt


# --- Dropped: the right answer has no proof (quiz_rules.md rules 2, 5, 9, 10) ---------
@pytest.mark.parametrize("text, reason", [
    (reply(answer="14 inches apart"), "proof:number_not_in_quote"),
    (reply(answer="12 feet apart"), "proof:unit_not_in_quote"),
    (reply(quote="The ladder rungs must be spaced 14 inches apart."), "proof:quote_not_on_page"),
    (reply(page=99), "proof:page_not_sent"),
])
def test_unproved_right_answer_drops_the_question(text, reason):
    q = ask(text)
    assert (q.status, q.text, q.reason) == (REFUSED, NOT_FOUND, reason)
    assert not q.options and not q.sources


def test_bad_replies_are_dropped():
    assert ask("Sure! Here is a question.").reason == "bad_json"
    assert ask('{"question": "x"}').reason == "bad_json"
    assert ask('{"found": true, "question": "x", "answer": "y"}').reason == "bad_json"  # no source
    assert ask('{"found": false}').reason == "llm_not_found"
    assert ask(reply(question="")).reason == "bad_shape"


# --- Dropped: bad options (rules 1, 3, 4, 6, 11) --------------------------------------
@pytest.mark.parametrize("wrong, reason", [
    (("8 inches apart", "20 inches apart"), "bad_options"),
    (("8 inches apart", "20 inches apart", "30 inches apart", "40 inches apart"), "bad_options"),
    (("8 inches apart", "20 inches apart", ""), "bad_options"),
    (("8 inches apart", "8 Inches  Apart.", "30 inches apart"), "same_options"),
    (("12 inches apart", "20 inches apart", "30 inches apart"), "same_options"),
    (("8 inches apart", "20 inches apart", "All of the above"), "banned_option"),
    (("8 inches apart", "20 inches apart", "None of these"), "banned_option"),
    (("8 inches apart", "20 inches apart", "Both A and B"), "banned_option"),
    (("8 inches apart", "20 inches apart", "the side rails"), "wrong_in_quote"),
    (("8 inches apart", "20 inches apart", "exactly 12 inches"), "wrong_in_quote"),
])
def test_bad_options_drop_the_question(wrong, reason):
    assert ask(reply(wrong=wrong)).reason == reason


def test_options_are_compared_as_whole_words():
    # Real case: "5 years" was dropped as the same option as "15 years".
    good = {"answer": "12 years", "wrong": ["10 years", "5 years", "15 years"], "sources": [{"quote": "It lasts 12 years."}]}
    assert options_problem(good) is None
    overlap = {"answer": "exceed 500 knots", "wrong": ["500 knots", "20 knots", "30 knots"],
               "sources": [{"quote": "It can exceed 500 knots."}]}
    assert options_problem(overlap)[0] == "same_options"
    in_quote = {"answer": "12 years", "wrong": ["2 years", "5 years", "the bottom"],
                "sources": [{"quote": "It lasts 12 years from the date on the bottom."}]}
    assert options_problem(in_quote)[0] == "wrong_in_quote"


def test_answer_inside_a_longer_number_is_not_given_away():
    page = Chunk("guide.pdf", 5, "Ladder rungs", "Ladder rungs last 5 years in 15 years of service.")
    q = ask(reply(question="In 15 years of service, how long do ladder rungs last?", answer="5 years",
                  quote="Ladder rungs last 5 years in 15 years of service."), pieces=[page])
    assert q.reason != "answer_in_question"


def test_wrong_option_may_use_words_like_above():
    data = {"answer": "12 inches apart", "wrong": ["8 inches above it", "20 inches below it", "30 inches apart"],
            "sources": [{"quote": QUOTE}]}
    assert options_problem(data) is None


# --- Dropped: topic, rule set, giving away the answer (rule 8) ------------------------
def test_topic_word_missing_from_every_piece_asks_no_ai():
    chain = FakeChain()
    q = make_question("ladder color", FakeSearcher([PIECE]), chain)
    assert (q.status, q.text, q.reason) == (REFUSED, NOT_FOUND, "no_topic_words")
    assert chain.prompts == []


def test_all_topic_words_must_be_in_one_piece():
    pieces = [Chunk("g.pdf", 1, "T", "The ladder is here."), Chunk("g.pdf", 2, "T", "The color is here.")]
    assert topic_pieces("ladder color", FakeSearcher(pieces)) == []
    assert topic_pieces("ladders here", FakeSearcher(pieces)) == [pieces[0]]


def test_only_pieces_with_the_topic_are_sent():
    chain = FakeChain('{"found": false}')
    make_question("rungs", FakeSearcher([PIECE, SECOND]), chain)
    assert QUOTE in chain.prompts[0] and SECOND_QUOTE not in chain.prompts[0]


def test_topic_number_must_be_in_the_piece():
    assert topic_pieces("ladder 14", FakeSearcher([PIECE])) == []


def test_topic_with_only_common_words_is_refused():
    assert make_question("the of and", FakeSearcher([PIECE]), FakeChain()).reason == "no_topic_words"


def test_quote_must_have_a_topic_word():
    text = reply(question="How wide is the base?", answer="12 inches",
                 quote="The base must rest on a floor of 12 inches.")
    page = Chunk("guide.pdf", 5, "Rungs", "Rungs are here. The base must rest on a floor of 12 inches.")
    assert ask(text, topic="rungs", pieces=[page]).reason == "topic_not_in_quote"


def test_question_must_not_contain_its_answer():
    q = ask(reply(question="Are ladder rungs 12 inches apart?"))
    assert q.reason == "answer_in_question"


def rules_reply(question):
    return reply(question=question, answer="4 seconds", doc="rules.pdf", page=7,
                 quote="A whistle signal shall last 4 seconds in all conditions.",
                 wrong=("2 seconds", "8 seconds", "10 seconds"))


def test_rule_set_page_needs_a_question_that_names_it():
    pieces = [INTL, INLAND]
    assert ask(rules_reply("How long does a whistle signal last?"), "whistle", pieces).reason == "rule_set_not_named"
    assert ask(rules_reply("Under the Inland Rules, how long is a whistle signal?"), "whistle",
               pieces).reason == "rule_set_not_named"
    kept = ask(rules_reply("Under the International Rules, how long is a whistle signal?"), "whistle", pieces)
    assert kept.status == ANSWERED


# --- AI problems ----------------------------------------------------------------------
def test_ai_busy_is_a_friendly_message_not_an_answer():
    q = make_question(TOPIC, FakeSearcher([PIECE]), FakeChain(fail=True))
    assert (q.status, q.text) == (AI_BUSY_STATUS, AI_BUSY_ITEM) and "timeout" in q.detail and not q.options


def test_call_limit_stops_the_run():
    with pytest.raises(CallLimitReached):
        make_question(TOPIC, FakeSearcher([PIECE]), FakeChain(fail="limit"))


def test_parse_item_reads_fenced_json():
    data = parse_item("```json\n" + reply() + "\n```")
    assert data["found"] and data["sources"][0]["page"] == 5 and len(data["wrong"]) == 3


# --- A whole quiz ---------------------------------------------------------------------
def second_reply():
    return reply(question="How wide is the ladder base?", answer="40 inches", page=6, quote=SECOND_QUOTE,
                 wrong=("8 inches", "20 inches", "30 inches"))


def test_quiz_makes_different_questions_one_piece_each():
    chain = FakeChain(reply(), second_reply())
    kept, dropped, busy = make_quiz("ladder", FakeSearcher([PIECE, SECOND]), chain, 2)
    assert [q.text for q in kept] == ["12 inches apart", "40 inches"] and dropped == 0 and not busy
    assert SECOND_QUOTE not in chain.prompts[0] and QUOTE not in chain.prompts[1]


def test_quiz_replaces_a_dropped_question_and_counts_it():
    kept, dropped, _ = make_quiz("ladder", FakeSearcher([PIECE, SECOND]), FakeChain('{"found": false}', second_reply()), 1)
    assert [q.text for q in kept] == ["40 inches"] and dropped == 1


def test_quiz_drops_a_repeated_quote():
    same = Chunk("guide.pdf", 5, "Portable Ladders", QUOTE)
    kept, dropped, _ = make_quiz("ladder", FakeSearcher([PIECE, same]), FakeChain(reply(), reply()), 2)
    assert len(kept) == 1 and dropped == 1


def test_quiz_stops_when_the_ai_is_busy():
    kept, dropped, busy = make_quiz("ladder", FakeSearcher([PIECE, SECOND]), FakeChain(fail=True), 2)
    assert (kept, dropped, busy) == ([], 0, True)


def test_quiz_on_a_missing_topic_asks_no_ai():
    chain = FakeChain()
    assert make_quiz("ladder color", FakeSearcher([PIECE]), chain, 3) == ([], 0, False)
    assert chain.prompts == []


def test_message_when_nothing_is_kept():
    assert nothing_kept("ladder color", 0, "question") == NOT_FOUND  # the words are not in the document
    found = nothing_kept("ladder", 4, "question")
    assert found != NOT_FOUND and "found these words" in found and "question" in found
    assert "this document" in nothing_kept(None, 2, "card") and "found these words" not in nothing_kept(None, 2, "card")


def test_quiz_with_no_topic_uses_pieces_from_across_the_document():
    long_text = " ".join(["word"] * 30)
    chunks = [Chunk("g.pdf", n, "T", long_text) for n in range(1, 11)]
    assert [c.page for c in spread_pieces(chunks, 2)] == [1, 6]
    assert spread_pieces([Chunk("g.pdf", 1, "T", "short")], 2) == []
    assert spread_pieces([Chunk("g.pdf", 1, "Contents", long_text + " ..... 3")], 2) == []
    assert len(spread_pieces(chunks[:1], 5)) == 1


# --- One document only (chat still searches everything) -------------------------------
def library():
    docs = [Document(name, name, {1: text}, [Chunk(name, 1, "T", text)])
            for name, text in [("a.pdf", "ladder rungs"), ("b.pdf", "ladder feet")]]
    return Library(docs)


def test_search_inside_one_document():
    searcher = Searcher(library(), "bm25")
    assert {c.doc for c in searcher.search("ladder")} == {"a.pdf", "b.pdf"}
    one = searcher.for_document("a.pdf")
    assert {c.doc for c in one.search("ladder")} == {"a.pdf"}
    assert searcher.for_document("a.pdf") is one
    assert one.library.page_text("b.pdf", 1) is None


def test_unknown_document_is_a_clear_error():
    with pytest.raises(ValueError, match="not loaded"):
        Searcher(library(), "bm25").for_document("c.pdf")


# --- Scoring and the gate -------------------------------------------------------------
ROW = {"doc": "guide.pdf", "id": "Q", "question": "ladder rungs", "type": "number", "expected_answer": "12 inches",
       "page": "5", "source_quote": QUOTE, "accepted_sources": "guide.pdf:5", "other_answers": ""}


def test_kept_question_is_scored_like_a_chat_answer():
    assert score_answer(ROW, False, ask(reply()))[0] == RIGHT
    wrong_key = reply(answer="40 inches", page=6, quote=SECOND_QUOTE, wrong=("8 inches", "20 inches", "30 inches"))
    assert score_answer(ROW, False, ask(wrong_key, topic="ladder", pieces=[PIECE, SECOND]))[0] == WRONG
    assert score_answer(ROW, False, ask('{"found": false}'))[0] == MISSED
    assert score_answer(ROW, True, ask(reply()))[0] == TRAP_ANSWERED


def test_number_stated_in_the_question_counts_as_shown():
    row = {**ROW, "expected_answer": "12 inches or 30 cm"}
    assert score_answer(row, False, ask(reply()))[0] == WRONG  # 30 is nowhere
    page = Chunk("guide.pdf", 5, "Rungs", "Ladder rungs are 12 inches or 30 cm apart.")
    text = reply(question="Ladder rungs are 30 cm apart. How many inches is that?", answer="12 inches",
                 quote="Ladder rungs are 12 inches or 30 cm apart.")
    assert score_answer(row, False, ask(text, pieces=[page]))[0] == RIGHT


def test_report_prints_kept_questions_for_a_person_to_read(monkeypatch):
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location("run_study_eval", scripts / "run_study_eval.py")
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    records = [{"row": ROW, "trap": False, "item": ask(reply()), "outcome": RIGHT, "reason": ""},
               {"row": {**ROW, "id": "T"}, "trap": True, "item": ask('{"found": false}'), "outcome": "refused", "reason": ""}]
    report = script.build_report("Quiz", records, FakeChain(), ["only 1 kept"])
    assert "NOT PASSED: only 1 kept" in report and "| 1/1 | 1/1 | 0 | 1/1 |" in report
    assert "8 inches apart" in report and "* 12 inches apart" in report and "guide.pdf p.5" in report


GOOD = [RIGHT, RIGHT, CORRECT_OTHER, MISSED, MISSED, "refused", "refused"]


def test_gate_passes():
    assert feature_gate(GOOD, 9.9) == []


@pytest.mark.parametrize("outcomes, slowest, text", [
    (GOOD + [WRONG], 1, "wrong 1"),
    (GOOD + [TRAP_ANSWERED], 1, "traps answered 1"),
    (GOOD + [NOT_TESTED], 1, "not tested"),
    (GOOD, 10.0, "slowest 10.0 s"),
    ([RIGHT, RIGHT, MISSED, MISSED, MISSED, "refused", "refused"], 1, "only 2 kept"),
])
def test_gate_fails(outcomes, slowest, text):
    assert any(text in failure for failure in feature_gate(outcomes, slowest))
