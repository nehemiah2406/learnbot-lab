"""Tests for the BM25 baseline and the evaluation logic, with made-up pieces."""

from pathlib import Path

import pytest

from learnbot.baseline import NOT_FOUND, BM25Index, Hit, answer, tokenize
from learnbot.chunking import Chunk
from learnbot.evaluate import (
    MISSED, REFUSED, RIGHT, TRAP_ANSWERED, WRONG,
    choose_threshold, exact_answer_in, on_right_page, outcome, sweep,
)

CHUNKS = [
    Chunk("rules.pdf", 45, "International Rule 22 Visibility of Lights",
          "(a) In vessels of 50 meters or more in length: a masthead light, 6 miles; a sidelight, 3 miles;"),
    Chunk("rules.pdf", 46, "Inland Rule 22 Visibility of lights",
          "(a) In a vessel of 50 meters or more in length: (i) A masthead light, 6 miles;"),
    Chunk("rules.pdf", 105, "International Rule 32 Definitions",
          "(c) The term prolonged blast means a blast of from four to six seconds' duration."),
    Chunk("guide.pdf", 16, "Pyrotechnic Devices",
          "Check the expiration date (42 months after the date of manufacture)."),
    Chunk("guide.pdf", 9, "Display of Numbers",
          "Lettering must be in plain, vertical block characters of not less than 3 inches in height."),
]


@pytest.fixture
def index():
    return BM25Index(CHUNKS)


def row(doc="rules.pdf", page="45", answer_text="6 miles"):
    return {"doc": doc, "page": page, "expected_answer": answer_text}


# --- Tokenizer and search -------------------------------------------------------------
def test_tokenize_keeps_numbers_drops_common_words():
    assert tokenize("What is the range of 2,000 yards?") == ["range", "2000", "yards"]


def test_search_finds_right_piece(index):
    hits = index.search("When do pyrotechnic signals expire?")
    assert (hits[0].chunk.doc, hits[0].chunk.page) == ("guide.pdf", 16)


def test_rule_set_word_in_title_picks_right_page(index):
    hits = index.search("Inland masthead light range 50 meters")
    assert hits[0].chunk.page == 46
    hits = index.search("International masthead light range 50 meters")
    assert hits[0].chunk.page == 45


def test_search_returns_at_most_three_best_first(index):
    hits = index.search("light meters length blast")
    assert len(hits) <= 3
    assert [h.score for h in hits] == sorted((h.score for h in hits), reverse=True)


def test_unknown_or_empty_query_gives_no_hits(index):
    assert index.search("photosynthesis chlorophyll") == []
    assert index.search("") == []
    assert index.search("what is the") == []


def test_low_score_gives_not_in_this_document(index):
    verdict, hits = answer(index, "masthead light", min_score=1000)
    assert verdict == NOT_FOUND and hits
    verdict, _ = answer(index, "masthead light", min_score=0)
    assert verdict is None


def test_no_hits_gives_not_in_this_document(index):
    assert answer(index, "capital of Peru", min_score=0)[0] == NOT_FOUND


# --- Evaluation logic -----------------------------------------------------------------
def hit(doc, page, text="", score=10.0):
    return Hit(score, Chunk(doc, page, "", text))


def test_right_page_needs_same_doc_and_page():
    assert on_right_page(row(), hit("rules.pdf", 45))
    assert not on_right_page(row(), hit("rules.pdf", 46))
    assert not on_right_page(row(), hit("other.pdf", 45))


def test_compare_row_either_page_counts():
    compare = row(page="107|108")
    assert on_right_page(compare, hit("rules.pdf", 107))
    assert on_right_page(compare, hit("rules.pdf", 108))


def test_exact_answer_needs_numbers_and_key_words():
    text = "a masthead light, 6 miles; a sidelight, 3 miles;"
    assert exact_answer_in("6 miles", text)
    assert not exact_answer_in("5 miles", text)
    assert not exact_answer_in("6 kilometers", text)
    assert exact_answer_in("A blast of from four to six seconds", "a blast of from four to six seconds' duration")


def test_outcomes():
    hits_right, hits_wrong = [hit("rules.pdf", 45)], [hit("rules.pdf", 99)]
    assert outcome(row(), False, None, hits_right) == RIGHT
    assert outcome(row(), False, None, hits_wrong) == WRONG
    assert outcome(row(), False, NOT_FOUND, hits_right) == MISSED
    assert outcome(row(), True, NOT_FOUND, hits_wrong) == REFUSED
    assert outcome(row(), True, None, hits_wrong) == TRAP_ANSWERED


def test_sweep_and_choose_threshold_prefers_higher_on_tie():
    results = [
        (row(), False, [hit("rules.pdf", 45, score=20)]),  # real question, strong match
        (row(), True, [hit("rules.pdf", 99, score=5)]),  # trap, weak match
    ]
    table = sweep(results, [0, 4, 10, 30])
    correct = {t: c for t, _, c in table}
    assert correct == {0: 1, 4: 1, 10: 2, 30: 1}
    assert choose_threshold(table) == 10
    assert choose_threshold([(1, {}, 2), (2, {}, 2), (3, {}, 1)]) == 2


# --- No file-specific code ------------------------------------------------------------
TEST_FILE_NAMES = ["nav_rules", "boaters_guide", "coast_pilot", "Coast Pilot", "COLREG"]


@pytest.mark.parametrize("source", sorted(Path("src/learnbot").glob("*.py")), ids=lambda p: p.name)
def test_no_file_specific_code(source):
    text = source.read_text(encoding="utf-8")
    assert not [name for name in TEST_FILE_NAMES if name in text]
