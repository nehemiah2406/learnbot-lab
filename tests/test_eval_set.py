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
    find_accepted_sources,
    format_sources,
    parse_other_answers,
    parse_sources,
    quote_core,
    verify_accepted_sources,
    verify_other_answers,
    verify_quotes,
    verify_trap,
)

EVAL_DIR = Path("eval")


def explain_row(**changes):
    row = {
        "doc": "book.pdf", "id": "X-01", "question": "How far under the International Rules?", "type": "number",
        "expected_answer": "6 miles", "rule": "Rule 22", "rule_set": "International",
        "page": "45", "source_quote": "a masthead light, 6 miles;", "accepted_sources": "book.pdf:45",
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
                       source_quote="range of 5 miles | range of 2 miles",
                       accepted_sources="book.pdf:107;book.pdf:108")
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


@pytest.fixture(scope="session")
def rule_sets(docs):
    """Page labels of all eval documents (as the app makes them); skips if a PDF is missing."""
    names = sorted({r["doc"] for r in EXPLAIN_ROWS + TRAP_ROWS})
    for name in names:
        need_pdf(docs, name)
    return docs.rule_sets(names)


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


@pytest.mark.parametrize("row", EXPLAIN_ROWS, ids=lambda r: r["id"])
def test_accepted_sources_are_exactly_the_pages_with_the_quote(row, docs, rule_sets):
    names = sorted({r["doc"] for r in EXPLAIN_ROWS + TRAP_ROWS})
    assert verify_accepted_sources(row, docs, names, rule_sets) == []


@pytest.mark.parametrize("row", EXPLAIN_ROWS, ids=lambda r: r["id"])
def test_other_answers_are_on_their_page(row, docs):
    for doc, _, _ in parse_other_answers(row.get("other_answers", "")) or []:
        need_pdf(docs, doc)
    assert verify_other_answers(row, docs) == []


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


def test_accepted_sources_format():
    assert parse_sources("b.pdf:3;a.pdf:12") == [("b.pdf", 3), ("a.pdf", 12)]
    assert parse_sources("a.pdf:x") is None and parse_sources("") is None
    assert format_sources([("b.pdf", 3), ("a.pdf", 12), ("a.pdf", 12)]) == "a.pdf:12;b.pdf:3"
    assert check_explain_row(explain_row(accepted_sources="book.pdf:46")) == [
        "accepted_sources must include the row's own page(s)"]
    assert check_explain_row(explain_row(accepted_sources="page 45"))[0].startswith("accepted_sources must be")


class FakePages:
    def __init__(self, docs):
        self.docs = docs  # {doc: {page: text}}

    def page_count(self, doc):
        return len(self.docs[doc])

    def pages(self, doc, numbers):
        return {n: self.docs[doc].get(n) for n in numbers}


def test_find_accepted_sources_ignores_marker_and_short_quotes():
    pages = FakePages({
        "a.pdf": {1: "(p) A high intensity white light flashing 50 to 70 times per minute.",
                  2: "A high intensity white light\nflashing 50 to 70 times per minute. Inland only.",
                  3: "(h) [Reserved]"},
        "b.pdf": {1: "a high intensity white light flashing 60 times", 2: "(h) [Reserved]"},
    })
    row = explain_row(doc="a.pdf", page="1",
                      source_quote="(p) A high intensity white light flashing 50 to 70 times per minute.")
    assert quote_core(row["source_quote"]).startswith("A high")
    assert find_accepted_sources(row, pages, ["a.pdf", "b.pdf"]) == [("a.pdf", 1), ("a.pdf", 2)]
    short = explain_row(doc="a.pdf", page="3", source_quote="(h) [Reserved]")
    assert find_accepted_sources(short, pages, ["a.pdf", "b.pdf"]) == [("a.pdf", 3)]  # too short to search
    listed = dict(row, accepted_sources="a.pdf:1")
    assert verify_accepted_sources(listed, pages, ["a.pdf", "b.pdf"]) == [
        "page has the same text but is not listed: a.pdf:2"]


def test_overall_result():
    from learnbot.eval_check import ALL_PASS, PROBLEMS, SKIPPED, overall_result

    assert overall_result({}, set()) == ALL_PASS
    assert overall_result({}, {"book.pdf"}) == SKIPPED
    assert overall_result({"X-01": ["bad"]}, {"book.pdf"}) == PROBLEMS


# --- other_answers: another exact answer of the document --------------------------------
def test_parse_other_answers():
    assert parse_other_answers("") == []
    assert parse_other_answers("a.pdf:34=nautical mile - 1,852 meters") == [("a.pdf", 34, "nautical mile - 1,852 meters")]
    assert parse_other_answers("a.pdf:34") is None and parse_other_answers("a.pdf:x=text") is None


def test_other_answers_format_is_checked():
    assert any("other_answers" in p for p in check_explain_row(explain_row(other_answers="a.pdf=no page")))
    assert not any("other_answers" in p for p in check_explain_row(explain_row(other_answers="")))


def test_other_answer_text_must_be_on_its_page():
    class Pages:
        def exists(self, doc):
            return True

        def pages(self, doc, numbers):
            return {n: "Measurements nautical mile – 1,852 meters / 6,076.12 feet" for n in numbers}

    ok = {"other_answers": "x.pdf:34=nautical mile - 1,852 meters / 6,076.12 feet"}
    bad = {"other_answers": "x.pdf:34=nautical mile - 1,850 meters"}
    assert verify_other_answers(ok, Pages()) == []
    assert verify_other_answers(bad, Pages())
