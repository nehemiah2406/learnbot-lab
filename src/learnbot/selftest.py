"""Upload self-test: can LearnBot answer from this file? Runs once per file. Any file.

It makes up to config.SELF_TEST_QUESTIONS flashcards from across the file, then asks chat
each card's question as a fresh question. A question passes if chat gives the same numbers
from the same page. A file passes with at least config.SELF_TEST_MIN_PASS; below that the
user sees a warning but can still use the file.

The result is saved by file content (config.STORAGE_DIR/selftest), so the same file is never
tested twice, even under another name. If the AI was busy there is no real result: nothing
is saved, and the next upload of the file finishes the test (saved AI replies cost no quota).

The questions come from the file itself, so this finds files LearnBot reads badly. It does
not prove that every answer will be right.
"""

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from learnbot import config
from learnbot.answer import AI_BUSY_STATUS, ANSWERED, answer_question
from learnbot.evaluate import numbers_differ
from learnbot.flashcards import make_cards

PASSED, WARNING, NOT_FINISHED = "passed", "warning", "not_finished"
# One question's result. Only SAME counts as a pass.
SAME, OTHER_PAGE, DIFFERENT, REFUSED, BUSY = "same", "other_page", "different_numbers", "refused", "ai_busy"
MESSAGES = {
    PASSED: "Self-test passed: LearnBot answered {passed} of {wanted} test questions from this file.",
    WARNING: "Warning: LearnBot answered only {passed} of {wanted} test questions from this file. "
             "It may often say it cannot find an answer here. You can still use the file.",
    NOT_FINISHED: "The self-test could not finish because the AI is busy. It will finish on the next upload of this file.",
}


@dataclass
class SelfTest:
    file: str
    verdict: str
    passed: int = 0
    wanted: int = config.SELF_TEST_QUESTIONS
    questions: list = field(default_factory=list)  # [{question, expected, page, answer, answer_page, result, seconds}]
    dropped: int = 0  # flashcards the checks dropped while making the test
    from_saved: bool = False

    @property
    def message(self):
        return MESSAGES[self.verdict].format(passed=self.passed, wanted=self.wanted)


def compare(card, ans):
    """The result of one question: chat's answer against the card it was made from."""
    if ans.status == AI_BUSY_STATUS:
        return BUSY
    if ans.status != ANSWERED:
        return REFUSED
    if numbers_differ(card.text, ans.text, card.question):
        return DIFFERENT
    page = (card.sources[0]["doc"], card.sources[0]["page"])
    return SAME if page in {(s["doc"], s["page"]) for s in ans.sources} else OTHER_PAGE


def run_self_test(name, searcher, chain):
    """Make the questions and ask them. searcher: search of this one document."""
    cards, dropped, busy = make_cards(None, searcher, chain, config.SELF_TEST_QUESTIONS)
    questions = []
    for card in cards:
        ans = answer_question(card.question, searcher, chain)
        source = ans.sources[0] if ans.sources else {}
        questions.append({"question": card.question, "expected": card.text, "page": card.sources[0]["page"],
                          "answer": ans.text, "answer_page": source.get("page"), "result": compare(card, ans),
                          "seconds": round(max(card.seconds, ans.seconds), 1)})
    passed = sum(q["result"] == SAME for q in questions)
    if busy or any(q["result"] == BUSY for q in questions):
        verdict = NOT_FINISHED
    else:
        verdict = PASSED if passed >= config.SELF_TEST_MIN_PASS else WARNING
    return SelfTest(name, verdict, passed, questions=questions, dropped=dropped)


def saved_path(digest, storage_dir=None):
    return Path(storage_dir or config.STORAGE_DIR) / "selftest" / f"{digest}.json"


def self_test_once(name, digest, searcher, chain, storage_dir=None):
    """The saved result of this file, or a new test (saved unless it could not finish)."""
    path = saved_path(digest, storage_dir)
    if path.is_file():
        data = json.loads(path.read_text(encoding="utf-8"))
        return SelfTest(**{**data, "from_saved": True})
    result = run_self_test(name, searcher, chain)
    if result.verdict != NOT_FINISHED:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(result), ensure_ascii=False, indent=1), encoding="utf-8")
    return result
