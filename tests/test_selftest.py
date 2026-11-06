"""Upload self-test and upload steps, with a fake AI (no network, no PDF reading)."""

import importlib.util
import json
from pathlib import Path

import pytest
from test_quiz import FakeSearcher

from learnbot import config, selftest, upload
from learnbot.answer import Answer
from learnbot.chunking import Chunk
from learnbot.llm import AllProvidersFailed, CallLimitReached
from learnbot.pdf_check import FAIL, OK, WARNING, PdfCheckResult
from learnbot.selftest import (
    BUSY, DIFFERENT, NOT_FINISHED, OTHER_PAGE, PASSED, REFUSED, SAME, SelfTest, compare, run_self_test, self_test_once,
)

WORDS = " ".join(["filler"] * 30)


def fact(n):
    return f"The ladder number {n} holds {100 + n} pounds of weight."


PIECES = [Chunk("f.pdf", n, "T", f"{fact(n)} {WORDS}") for n in range(1, 11)]


def card_reply(n):
    return json.dumps({"found": True, "question": f"How much does ladder number {n} hold?",
                       "answer": f"{100 + n} pounds",
                       "source": {"doc": "f.pdf", "page": n, "quote": fact(n)}})


def answer_reply(n, value=None, page=None):
    return json.dumps({"found": True, "answer": f"{value or 100 + n} pounds",
                       "sources": [{"doc": "f.pdf", "page": page or n, "quote": fact(page or n)}]})


class ScriptedChain:
    """Card prompts get a card for their piece; chat prompts get the given replies per piece."""

    def __init__(self, answers=None, busy_at=None, no_cards=False):
        self.answers, self.busy_at, self.no_cards = answers or {}, busy_at, no_cards
        self.calls = 0

    def ask(self, prompt, budget_s=None):
        self.calls += 1
        if self.busy_at == self.calls:
            raise AllProvidersFailed([("gemini:x", "timeout", 5.0)])
        if "ONE flashcard" in prompt:
            n = next(c.page for c in PIECES if f"| page: {c.page} |" in prompt)
            return ('{"found": false}' if self.no_cards else card_reply(n)), "gemini:x", False
        n = int(prompt.split("Question: How much does ladder number ")[1].split(" ")[0])
        return self.answers.get(n, answer_reply(n)), "gemini:x", False


class PageSearcher(FakeSearcher):
    """Chat search: the piece of the ladder asked about."""

    def search(self, question, k=None):
        for n in range(1, 11):
            if f"ladder number {n} " in question:
                return [PIECES[n - 1]]
        return self.chunks[:k] if k else self.chunks


def searcher():
    return PageSearcher(PIECES)


def test_file_where_every_answer_matches_passes():
    test = run_self_test("f.pdf", searcher(), ScriptedChain())
    assert (test.verdict, test.passed, len(test.questions), test.dropped) == (PASSED, 5, 5, 0)
    assert "5 of 5" in test.message and test.questions[0]["result"] == SAME


def bad_answers(pages):
    return {p: '{"found": false}' for p in pages}


def test_three_of_five_is_enough_but_two_is_a_warning():
    pages = [c.sources[0]["page"] for c in selftest.make_cards(None, searcher(), ScriptedChain(), 5)[0]]
    assert run_self_test("f.pdf", searcher(), ScriptedChain(bad_answers(pages[:2]))).verdict == PASSED
    test = run_self_test("f.pdf", searcher(), ScriptedChain(bad_answers(pages[:3])))
    assert (test.verdict, test.passed) == (selftest.WARNING, 2)
    assert test.message.startswith("Warning") and "still use the file" in test.message


def test_too_few_cards_is_a_warning_not_a_crash():
    test = run_self_test("f.pdf", searcher(), ScriptedChain(no_cards=True))
    assert (test.verdict, test.passed, test.questions, test.dropped) == (selftest.WARNING, 0, [], 10)


def test_busy_ai_gives_no_verdict():
    assert run_self_test("f.pdf", searcher(), ScriptedChain(busy_at=1)).verdict == NOT_FINISHED
    assert run_self_test("f.pdf", searcher(), ScriptedChain(busy_at=7)).verdict == NOT_FINISHED


def card(text="101 pounds", page=1):
    return Answer("answered", text, [], sources=[{"doc": "f.pdf", "page": page}])


@pytest.mark.parametrize("ans, result", [
    (Answer("answered", "101 pounds", [], sources=[{"doc": "f.pdf", "page": 1}]), SAME),
    (Answer("answered", "101 pounds", [], sources=[{"doc": "f.pdf", "page": 2}]), OTHER_PAGE),
    (Answer("answered", "109 pounds", [], sources=[{"doc": "f.pdf", "page": 1}]), DIFFERENT),
    (Answer("not_found", "Not in this document", []), REFUSED),
    (Answer("ai_busy", "busy", []), BUSY),
])
def test_compare_chat_answer_with_card(ans, result):
    c = card()
    c.question = "How much?"
    assert compare(c, ans) == result


# --- Once per file --------------------------------------------------------------------
def test_result_is_saved_and_never_repeated(tmp_path):
    chain = ScriptedChain()
    first = self_test_once("f.pdf", "abc", searcher(), chain, tmp_path)
    calls = chain.calls
    again = self_test_once("renamed.pdf", "abc", searcher(), chain, tmp_path)
    assert calls > 0 and chain.calls == calls  # no AI call the second time
    assert not first.from_saved and again.from_saved
    assert (again.verdict, again.passed, again.file) == (PASSED, 5, "f.pdf")


def test_other_file_content_is_tested(tmp_path):
    chain = ScriptedChain()
    self_test_once("f.pdf", "abc", searcher(), chain, tmp_path)
    calls = chain.calls
    self_test_once("f.pdf", "def", searcher(), chain, tmp_path)
    assert chain.calls > calls


def test_warning_result_is_saved_too(tmp_path):
    self_test_once("f.pdf", "abc", searcher(), ScriptedChain(no_cards=True), tmp_path)
    assert self_test_once("f.pdf", "abc", searcher(), ScriptedChain(), tmp_path).verdict == selftest.WARNING


def test_not_finished_is_not_saved(tmp_path):
    assert self_test_once("f.pdf", "abc", searcher(), ScriptedChain(busy_at=1), tmp_path).verdict == NOT_FINISHED
    assert not selftest.saved_path("abc", tmp_path).exists()
    assert self_test_once("f.pdf", "abc", searcher(), ScriptedChain(), tmp_path).verdict == PASSED


def test_saved_result_has_only_the_expected_fields(tmp_path):
    self_test_once("f.pdf", "abc", searcher(), ScriptedChain(), tmp_path)
    data = json.loads(selftest.saved_path("abc", tmp_path).read_text(encoding="utf-8"))
    assert SelfTest(**data).passed == 5


# --- Upload ---------------------------------------------------------------------------
def fake_check(monkeypatch, verdict):
    result = PdfCheckResult(path="f.pdf")
    result.verdict, result.reasons = verdict, ["too many blank pages"] if verdict != OK else []
    monkeypatch.setattr(upload, "check_file", lambda path: result)


@pytest.fixture
def file(tmp_path):
    path = tmp_path / "source" / "f.pdf"
    path.parent.mkdir()
    path.write_bytes(b"first file")
    return path


def test_upload_stores_the_file_and_runs_the_self_test(monkeypatch, tmp_path, file):
    fake_check(monkeypatch, OK)
    seen = []
    result = upload.upload_file(file, lambda p: seen.append(p) or "tested", tmp_path / "up")
    assert result.path == tmp_path / "up" / "f.pdf" and result.path.read_bytes() == b"first file"
    assert seen == [result.path] and result.self_test == "tested" and not result.problem


def test_upload_with_a_warning_still_runs(monkeypatch, tmp_path, file):
    fake_check(monkeypatch, WARNING)
    assert upload.upload_file(file, lambda p: "tested", tmp_path / "up").self_test == "tested"


def test_failed_self_check_is_not_added_and_not_tested(monkeypatch, tmp_path, file):
    fake_check(monkeypatch, FAIL)
    seen = []
    result = upload.upload_file(file, seen.append, tmp_path / "up")
    assert result.path is None and "too many blank pages" in result.problem and seen == []
    assert not (tmp_path / "up").exists()


def test_different_file_with_the_same_name_is_not_overwritten(monkeypatch, tmp_path, file):
    fake_check(monkeypatch, OK)
    upload.upload_file(file, lambda p: "tested", tmp_path / "up")
    file.write_bytes(b"second file")
    seen = []
    result = upload.upload_file(file, seen.append, tmp_path / "up")
    assert "already uploaded" in result.problem and seen == []
    assert (tmp_path / "up" / "f.pdf").read_bytes() == b"first file"


def test_same_file_again_is_fine(monkeypatch, tmp_path, file):
    fake_check(monkeypatch, OK)
    upload.upload_file(file, lambda p: "tested", tmp_path / "up")
    assert upload.upload_file(file, lambda p: "again", tmp_path / "up").self_test == "again"


def load_script(name, monkeypatch):
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location(name, scripts / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_upload_command_stops_clearly_at_the_call_limit(monkeypatch, capsys, file):
    script = load_script("upload_file", monkeypatch)

    def limit(*args):
        raise CallLimitReached(3)
    monkeypatch.setattr(script, "upload_file", limit)
    monkeypatch.setattr(script, "default_chain", lambda: ScriptedChain())
    monkeypatch.setattr("sys.argv", ["upload_file.py", str(file), "--max-calls", "3"])
    assert script.main() == 2
    assert "limit of 3 AI calls" in capsys.readouterr().out


def test_hard_traps_are_reported_but_not_in_the_gate(monkeypatch):
    script = load_script("run_selftest_eval", monkeypatch)
    test = run_self_test("f.pdf", searcher(), ScriptedChain())
    refused = Answer("not_found", "Not in this document", [], seconds=1.0)
    answered = Answer("answered", "several hours", [], seconds=2.0)
    traps = [{"row": {"question": "Normal?"}, "hard": False, "item": refused, "outcome": "refused", "reason": ""},
             {"row": {"question": "Hard?"}, "hard": True, "item": answered, "outcome": "trap_answered", "reason": ""},
             {"row": {"question": "Late?"}, "hard": True, "item": None, "outcome": "not asked", "reason": ""}]
    report = script.build_report("f.pdf", test, traps, [], 3)
    assert "hard (not a gate) | trap_answered | several hours" in report and "not asked (call limit)" in report
    assert "1 normal traps" in report and "Gate: PASS" in report


def test_find_document_looks_in_uploads_then_test_documents(monkeypatch, tmp_path):
    (tmp_path / "up").mkdir()
    (tmp_path / "raw").mkdir()
    monkeypatch.setattr(config, "UPLOAD_DIR", str(tmp_path / "up"))
    monkeypatch.setattr(config, "TEST_DOCS_DIR", str(tmp_path / "raw"))
    (tmp_path / "raw" / "a.pdf").write_bytes(b"x")
    assert upload.find_document("a.pdf") == Path(tmp_path / "raw" / "a.pdf")
    (tmp_path / "up" / "a.pdf").write_bytes(b"y")
    assert upload.find_document("a.pdf") == Path(tmp_path / "up" / "a.pdf")
    assert upload.find_document("b.pdf") is None
