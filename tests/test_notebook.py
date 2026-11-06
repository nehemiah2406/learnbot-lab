"""Notebook, with a fake AI (no network, no PDF)."""

import json

import pytest
from test_quiz import FakeChain

from learnbot.answer import AI_BUSY_SCOPED, AI_BUSY_STATUS, ANSWERED, REFUSED, Answer
from learnbot.notebook import NOT_IN_NOTEBOOK, YOUR_NOTE, Notebook
from learnbot.research import research
from learnbot.study import StudyItem

QUOTE = "The ladder rungs must be spaced 12 inches apart along the side rails."
SOURCE = {"doc": "guide.pdf", "page": 5, "quote": QUOTE, "title": "Portable Ladders"}
QUESTION = "How far apart must ladder rungs be spaced?"


def answer(sources=(SOURCE,), status=ANSWERED):
    return Answer(status, "12 inches apart", [], sources=list(sources))


def reply(text="12 inches apart", quote=QUOTE, page=5):
    return json.dumps({"found": True, "answer": text, "sources": [{"doc": "guide.pdf", "page": page, "quote": quote}]})


@pytest.fixture
def notebook(tmp_path):
    return Notebook(tmp_path)


# --- Saving ---------------------------------------------------------------------------
def test_saved_chat_answer_keeps_page_and_quote(notebook):
    item = notebook.save("chat", answer(), QUESTION)
    assert (item["kind"], item["question"], item["text"]) == ("chat", QUESTION, "12 inches apart")
    assert item["sources"][0] == SOURCE


def test_saved_quiz_question_keeps_its_options(notebook):
    quiz = StudyItem(ANSWERED, "12 inches", [], sources=[SOURCE], question="How far?", options=["8", "12 inches"], correct=1)
    item = notebook.save("quiz", quiz)
    assert (item["question"], item["options"], item["correct"]) == ("How far?", ["8", "12 inches"], 1)


def test_saved_flashcard_uses_its_front_as_the_question(notebook):
    card = StudyItem(ANSWERED, "12 inches", [], sources=[SOURCE], question="Rung spacing?")
    assert notebook.save("card", card)["question"] == "Rung spacing?"
    assert "options" not in notebook.items[0]


def test_narrowed_list_quote_saves_the_full_quote(notebook):
    full = "In vessels of 50 meters: a masthead light, 6 miles; a sidelight, 3 miles"
    source = {**SOURCE, "quote": "a masthead light, 6 miles", "lead": "In vessels of 50 meters:", "full_quote": full}
    notebook.save("chat", answer([source]), "Range?")
    assert notebook.pieces()[0].text == full


def test_unproved_answer_cannot_be_saved(notebook):
    with pytest.raises(ValueError, match="page and quote"):
        notebook.save("chat", answer(status=REFUSED), QUESTION)
    with pytest.raises(ValueError, match="page and quote"):
        notebook.save("chat", answer(sources=()), QUESTION)
    assert notebook.items == []


def test_unknown_kind_cannot_be_saved(notebook):
    with pytest.raises(ValueError, match="unknown kind"):
        notebook.save("web", answer(), QUESTION)


def test_web_answer_is_never_saved(notebook, tmp_path, monkeypatch):
    url = "https://example.org/page"
    text = json.dumps({"found": True, "answer": "12 inches apart", "sources": [{"doc": url, "page": 1, "quote": QUOTE}]})
    monkeypatch.setattr("learnbot.config.STORAGE_DIR", str(tmp_path))
    web = research("How far apart are ladder rungs spaced?", FakeChain(text),
                   lambda q: [{"title": "t", "url": url, "content": QUOTE}])
    assert web.status == ANSWERED
    with pytest.raises(ValueError, match="Web answers"):
        notebook.save("chat", web, "q")
    assert notebook.items == []


# --- Notes, list, delete, restart -----------------------------------------------------
def test_typed_note_is_labelled(notebook):
    item = notebook.add_note("  Check the flares  ")
    assert (item["label"], item["text"], item["kind"]) == (YOUR_NOTE, "Check the flares", "note")
    assert YOUR_NOTE == "Your note"
    with pytest.raises(ValueError):
        notebook.add_note("   ")


def test_items_are_listed_with_their_own_numbers(notebook):
    first, second = notebook.save("chat", answer(), QUESTION), notebook.add_note("note")
    assert [i["id"] for i in notebook.items] == [first["id"], second["id"]] == [1, 2]


def test_delete(notebook):
    notebook.save("chat", answer(), QUESTION)
    notebook.add_note("note")
    assert notebook.delete(1) is True and notebook.delete(1) is False
    assert [i["id"] for i in notebook.items] == [2]
    assert notebook.add_note("next")["id"] == 3  # a number is not used twice while higher ones exist


def test_everything_is_kept_after_a_restart(notebook, tmp_path):
    notebook.save("chat", answer(), QUESTION)
    notebook.add_note("note")
    notebook.delete(2)
    notebook.add_note("kept")
    again = Notebook(tmp_path)
    assert [i["kind"] for i in again.items] == ["chat", "note"] and again.items[1]["text"] == "kept"
    assert not list(tmp_path.glob("*.tmp"))


# --- Questions ------------------------------------------------------------------------
def test_question_is_answered_from_a_saved_item(notebook):
    notebook.save("chat", answer(), QUESTION)
    ans = notebook.ask(QUESTION, FakeChain(reply()))
    assert ans.status == ANSWERED and ans.text == "12 inches apart"
    assert (ans.sources[0]["doc"], ans.sources[0]["page"]) == ("guide.pdf", 5)


def test_empty_notebook_asks_no_ai(notebook):
    chain = FakeChain()
    ans = notebook.ask(QUESTION, chain)
    assert (ans.status, ans.text) == (REFUSED, NOT_IN_NOTEBOOK) and chain.prompts == []


def test_typed_note_is_never_used_in_an_answer(notebook):
    notebook.add_note("The ladder rungs must be spaced 12 inches apart along the side rails.")
    chain = FakeChain(reply())
    assert notebook.ask(QUESTION, chain).text == NOT_IN_NOTEBOOK and chain.prompts == []


def test_typed_note_is_not_sent_to_the_ai_with_saved_items(notebook):
    notebook.save("chat", answer(), QUESTION)
    notebook.add_note("Ladder rungs secret note about spacing")
    chain = FakeChain('{"found": false}')
    notebook.ask(QUESTION, chain)
    assert QUOTE in chain.prompts[0] and "secret note" not in chain.prompts[0]


@pytest.mark.parametrize("text", [
    reply(text="14 inches apart"),  # number not in the quote
    reply(quote="The ladder rungs must be spaced 14 inches apart along the side rails."),  # quote not saved
    reply(page=9),  # page not saved
    '{"found": false}', "not json",
])
def test_anything_unproved_says_not_in_your_notebook(notebook, text):
    notebook.save("chat", answer(), QUESTION)
    ans = notebook.ask(QUESTION, FakeChain(text))
    assert (ans.status, ans.text, ans.sources) == (REFUSED, NOT_IN_NOTEBOOK, [])


def test_quote_from_the_document_but_not_saved_is_refused(notebook):
    notebook.save("chat", answer(), QUESTION)
    other = "The ladder rungs on the same page are spaced 12 inches apart on this other line."
    assert notebook.ask(QUESTION, FakeChain(reply(quote=other))).text == NOT_IN_NOTEBOOK


def test_saved_international_rule_does_not_answer_an_inland_question(notebook):
    source = {"doc": "rules.pdf", "page": 7, "title": "Rule 1 INTERNATIONAL", "quote": "A whistle signal shall last 4 seconds."}
    notebook.save("chat", answer([source]), "Whistle?")
    text = json.dumps({"found": True, "answer": "4 seconds", "sources": [{"doc": "rules.pdf", "page": 7, "quote": source["quote"]}]})
    assert notebook.ask("Under the Inland Rules, how long does a whistle signal last?", FakeChain(text)).text == NOT_IN_NOTEBOOK
    assert notebook.ask("Under the International Rules, how long does a whistle signal last?", FakeChain(text)).status == ANSWERED


def test_busy_ai_is_a_friendly_message(notebook):
    notebook.save("chat", answer(), QUESTION)
    ans = notebook.ask(QUESTION, FakeChain(fail=True))
    assert (ans.status, ans.text) == (AI_BUSY_STATUS, AI_BUSY_SCOPED) and "document" not in ans.text
