"""Tests for the eval set.

Part 1: checker logic on made-up rows (always runs).
Part 2: every row of the real eval files against its PDF in data/raw.
        Rows whose PDF is missing are skipped, so the suite passes on GitHub.
"""

from pathlib import Path

import pytest

from learnbot.eval_check import (
    DocumentPages,
    EXPLAIN_COLUMNS,
    NOT_FOUND,
    TRAP_COLUMNS,
    check_explain_row,
    check_trap_row,
    duplicate_ids,
    found_keywords,
    load_rows,
    missing_numbers,
    normalize,
    numbers_in,
    quote_on_page,
    verify_quotes,
    verify_trap,
)

EVAL_DIR = Path("eval")


def explain_row(**changes):
    row = {
        "doc": "book.pdf", "id": "X-01", "question": "How far under the International Rules?", "type": "number",
        "expected_answer": "6 miles", "rule": "Rule 22", "rule_set": "International",
        "page": "45", "source_quote": "a masthead light, 6 miles;",
    }
    row.update(changes)
    return row


def trap_row(**changes):
    row = {
        "doc": "book.pdf", "id": "T-01", "question": "Capital of Peru?", "type": "off_topic",
        "expected_answer": NOT_FOUND, "keywords": "Lima;Peru",
    }
    row.update(changes)
    return row


# --- Part 1: checker logic -------------------------------------------------------------
def test_quote_found_ignoring_spaces_and_line_breaks():
    page = "(a) In vessels of 50 meters\nor more in   length:\n− a masthead light, 6 miles;"
    assert quote_on_page("In vessels of 50 meters or more in length: − a masthead light", page)


def test_quote_with_different_quote_marks_and_dashes_still_found():
    page = "one short blast to mean “I am altering my course to starboard”"
    assert quote_on_page('one short blast to mean "I am altering my course to starboard"', page)


def test_hyphen_at_line_end_joins_word():
    assert normalize("PAN-\nPAN spoken") == "PAN-PAN spoken"


def test_wrong_quote_not_found():
    assert not quote_on_page("a masthead light, 5 miles;", "a masthead light, 6 miles;")


def test_numbers_in_digits_and_words():
    assert numbers_in("approximately 2,000 yards, about 1.15 miles") == {"2000", "1.15"}
    assert numbers_in("from four to six seconds") == {"four", "six"}


def test_missing_numbers_caught():
    assert missing_numbers("6 miles", "a masthead light, 6 miles;") == []
    assert missing_numbers("5 miles", "a masthead light, 6 miles;") == ["5"]
    assert missing_numbers("four to six seconds", "4 to 6 seconds") == ["four", "six"]


def test_good_row_has_no_problems():
    assert check_explain_row(explain_row()) == []


def test_empty_column_reported():
    assert check_explain_row(explain_row(source_quote=" ")) == ["empty column: source_quote"]


def test_invalid_type_and_rule_set():
    problems = check_explain_row(explain_row(type="guess", rule_set="Europe"))
    assert "unknown type: guess" in problems
    assert "unknown rule_set: Europe" in problems


def test_answer_number_not_in_quote():
    problems = check_explain_row(explain_row(expected_answer="5 miles"))
    assert problems == ["numbers in answer not in source_quote: 5"]


def test_bad_page():
    assert check_explain_row(explain_row(page="45a"))[0].startswith("page must be a number")


def test_doc_must_be_plain_pdf_name():
    problems = check_explain_row(explain_row(doc="../secret/file.pdf"))
    assert problems[0].startswith("doc must be a PDF file name")


def test_compare_row_needs_two_pages_and_two_quotes():
    good = explain_row(type="compare", rule_set="Both", page="107|108",
                       expected_answer="5 miles and 2 miles",
                       source_quote="range of 5 miles | range of 2 miles")
    assert check_explain_row(good) == []
    one_quote = dict(good, source_quote="range of 5 miles and 2 miles")
    assert check_explain_row(one_quote) == ["compare row needs 2 page(s) and 2 quote(s)"]
    wrong_set = dict(good, rule_set="N/A")
    assert check_explain_row(wrong_set) == ["compare row must have rule_set Both"]


def test_duplicate_ids():
    assert duplicate_ids([{"id": "A"}, {"id": "B"}, {"id": "A"}]) == ["A"]


def test_trap_row_checks():
    assert check_trap_row(trap_row()) == []
    assert check_trap_row(trap_row(expected_answer="Lima")) == [
        f"expected_answer must be '{NOT_FOUND}'"
    ]


def test_trap_keywords_found_case_insensitive():
    text = "Annex V of MARPOL 73/78 prohibits\nthrowing refuse"
    assert found_keywords(["marpol", "lifeboat"], text) == ["marpol"]
    assert found_keywords(["lifeboat"], text) == []


# --- Part 2: the real eval files ------------------------------------------------------
EXPLAIN_ROWS = load_rows(EVAL_DIR / "explain_questions.csv")
TRAP_ROWS = load_rows(EVAL_DIR / "trap_questions.csv")


@pytest.fixture(scope="session")
def docs():
    return DocumentPages()


def need_pdf(docs, doc):
    if not docs.exists(doc):
        pytest.skip(f"{doc} not found in data/raw, see PLAN.md Data section for the download link")


def test_eval_files_have_expected_columns():
    assert list(EXPLAIN_ROWS[0]) == EXPLAIN_COLUMNS
    assert list(TRAP_ROWS[0]) == TRAP_COLUMNS


def test_eval_ids_unique():
    assert duplicate_ids(EXPLAIN_ROWS + TRAP_ROWS) == []


@pytest.mark.parametrize("row", EXPLAIN_ROWS, ids=lambda r: r["id"])
def test_explain_row_valid(row):
    assert check_explain_row(row) == []


@pytest.mark.parametrize("row", TRAP_ROWS, ids=lambda r: r["id"])
def test_trap_row_valid(row):
    assert check_trap_row(row) == []


@pytest.mark.parametrize("row", EXPLAIN_ROWS, ids=lambda r: r["id"])
def test_quote_on_stated_page(row, docs):
    need_pdf(docs, row["doc"])
    assert verify_quotes(row, docs) == []


@pytest.mark.parametrize("row", TRAP_ROWS, ids=lambda r: r["id"])
def test_trap_keywords_absent_from_document(row, docs):
    need_pdf(docs, row["doc"])
    assert verify_trap(row, docs) == []


# --- Rule-set naming and overall result -------------------------------------------------
def test_question_must_name_its_rule_set():
    vague = explain_row(rule_set="International", question="How far must a masthead light be seen?")
    assert check_explain_row(vague) == ["question must name its rule set (International)"]
    clear = explain_row(rule_set="International", question="Under the International Rules, how far?")
    assert check_explain_row(clear) == []
    assert check_explain_row(explain_row(rule_set="N/A", question="How far?")) == []


def test_overall_result():
    from learnbot.eval_check import ALL_PASS, PROBLEMS, SKIPPED, overall_result

    assert overall_result({}, set()) == ALL_PASS
    assert overall_result({}, {"book.pdf"}) == SKIPPED
    assert overall_result({"X-01": ["bad"]}, {"book.pdf"}) == PROBLEMS
