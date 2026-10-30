"""Tests for learnbot.pdf_check using made-up text only (no real PDF)."""

from learnbot.pdf_check import (
    FAIL,
    OK,
    WARNING,
    PdfCheckResult,
    analyse_pages,
    check_page_limit,
    check_size_limit,
    char_stats,
    decide_verdict,
    find_gaps,
    find_headings,
    find_low_text_pages,
    make_notes,
    page_ranges,
    pick_samples,
    roman_to_int,
)

MB = 1024 * 1024
FULL = "x" * 500  # a page with plenty of text


def analysed(texts, tables=None):
    result = PdfCheckResult(path="fake.pdf")
    return analyse_pages(result, texts, tables or [0] * len(texts))


# --- Heading finder ---------------------------------------------------------------
def test_heading_found_on_correct_page():
    headings = find_headings(["Intro text", "Rule 5\nEvery vessel shall keep a look-out."])
    assert headings["Rule"] == {"5": [2]}


def test_rule_10_is_not_rule_1():
    headings = find_headings(["Rule 10\nTraffic schemes"])
    assert list(headings["Rule"]) == ["10"]


def test_annex_ii_is_not_annex_i():
    headings = find_headings(["Annex II\nFishing", "Annex I\nLights", "Annex IV: Distress"])
    assert headings["Annex"] == {"I": [2], "II": [1], "IV": [3]}


def test_only_line_start_counts():
    headings = find_headings(["Action taken as required by Rule 7 and Section 4."])
    assert headings == {}


def test_wrapped_sentence_at_line_start_is_not_heading():
    text = "the vessel under\nRule 13.\nRule 21. From 5 degrees\nAnnex III to these Regulations."
    assert find_headings([text]) == {}


def test_heading_styles_accepted():
    text = "RULE 3\nRule 4-Application\nRule 5: Look-out\nRule 23—CONTINUED\nSection 6 Safe Speed"
    headings = find_headings([text])
    assert list(headings["Rule"]) == ["3", "4", "5", "23"]
    assert list(headings["Section"]) == ["6"]


def test_other_kinds_and_dotted_numbers():
    text = "Chapter 2\nArticle 4 Scope\n1.2 Title of part\n1.10 Later part\n1.5 m above the hull"
    headings = find_headings([text])
    assert list(headings["Chapter"]) == ["2"]
    assert list(headings["Article"]) == ["4"]
    assert list(headings["Numbered"]) == ["1.2", "1.10"]  # "1.5 m" is not a title


def test_lowercase_words_not_read_as_roman_numerals():
    assert find_headings(["Part in the middle", "Section mix"]) == {}


def test_letter_labels_not_read_as_roman_numerals():
    assert find_headings(["Part C\nLights", "Appendix D"]) == {}


def test_contents_page_is_skipped():
    toc = "\n".join(f"Rule {n}-Title ........ {n}" for n in range(1, 6))
    toc += "\nRule 6-A long title that wraps\nonto the next line ........ 9"
    assert find_headings([toc]) == {}


def test_same_page_listed_once_and_pages_in_order():
    headings = find_headings(["Rule 1\nInternational\nRule 1\nInland", "Rule 1—CONTINUED"])
    assert headings["Rule"]["1"] == [1, 2]


def test_roman_numeral_validation():
    assert roman_to_int("IV") == 4
    assert roman_to_int("XXXVIII") == 38
    assert roman_to_int("IIII") is None


# --- Numbering gaps ---------------------------------------------------------------
def test_gap_found():
    gaps = find_gaps({"Rule": {"1": [1], "2": [1], "4": [2], "5": [2]}})
    assert gaps == {"Rule": ["3"]}


def test_no_gap_when_complete():
    assert find_gaps({"Rule": {str(n): [n] for n in range(1, 39)}}) == {}


def test_gaps_skipped_for_few_headings():
    assert find_gaps({"Chapter": {"2": [1], "7": [5]}}) == {}


def test_roman_gap_shown_as_roman():
    assert find_gaps({"Annex": {"I": [1], "II": [2], "IV": [3]}}) == {"Annex": ["III"]}


def test_dotted_gap_inside_parent():
    gaps = find_gaps({"Numbered": {"1.1": [1], "1.2": [1], "1.4": [2], "2.1": [3]}})
    assert gaps == {"Numbered": ["1.3"]}


def test_sparse_numbering_is_not_reported_as_gaps():
    # Legal-style numbers like 80.105, 80.110, 80.115 skip numbers on purpose.
    nums = {f"80.{n}": [1] for n in (105, 110, 115, 120)}
    assert find_gaps({"Numbered": nums}) == {}


def test_long_gap_list_is_shortened():
    texts = [f"Rule {n}\n{FULL}" for n in range(1, 41) if n not in range(5, 20)]
    reason = decide_verdict(analysed(texts))[1][0]
    assert reason == (
        "Rule numbering has gaps, missing: 5, 6, 7, 8, 9, 10, 11, 12, 13, 14 ... (+5 more)."
    )


# --- Low-text pages, stats, sample ---------------------------------------------------
def test_low_text_pages():
    assert find_low_text_pages(["", "x" * 50, "y" * 200, "   \n  "], limit=100) == [1, 2, 4]


def test_page_ranges():
    assert page_ranges([5, 6, 7, 8, 12, 14, 15]) == "5-8, 12, 14-15"
    assert page_ranges([]) == ""


def test_char_stats():
    assert char_stats([0, 50, 200]) == {"min": 0, "max": 200, "avg": 83.3}
    assert char_stats([])["max"] == 0


def test_samples_skip_low_text_pages():
    assert pick_samples(["", "short", "Real text here"], [1, 2], n=4) == [(3, "Real")]


def test_samples_first_and_middle_text_page():
    texts = ["Cover", "", "Body A", "Body B", "Body C"]
    assert pick_samples(texts, [2], n=6) == [(1, "Cover"), (4, "Body B")]
    assert pick_samples(["", ""], [1, 2]) == []


# --- Verdict --------------------------------------------------------------------------
def test_verdict_ok():
    result = analysed([f"Rule {n}\n{FULL}" for n in range(1, 11)])
    assert decide_verdict(result) == (OK, ["File looks good."])


def test_verdict_fail_when_mostly_scanned():
    result = analysed(["", "", "", f"Rule 1\n{FULL}"])
    verdict, reasons = decide_verdict(result)
    assert verdict == FAIL
    assert "scanned" in reasons[0]


def test_verdict_warning_for_some_blank_pages_with_ranges():
    texts = [f"Rule {n}\n{FULL}" for n in range(1, 11)]
    texts[4:8] = ["", "", "", ""]  # pages 5-8, 40% < 50%
    verdict, reasons = decide_verdict(analysed(texts))
    assert verdict == WARNING
    assert "Pages 5-8 have almost no text" in reasons[0]


def test_few_blank_pages_do_not_warn():
    texts = [f"Rule {n}\n{FULL}" for n in range(1, 21)] + [""]  # 1 of 21 < 10%
    assert decide_verdict(analysed(texts))[0] == OK


def test_no_headings_is_only_a_note():
    result = analysed([FULL, FULL])
    assert decide_verdict(result) == (OK, ["File looks good."])
    assert "No numbered headings" in make_notes(result)[0]


def test_multi_column_pages_noted():
    result = analysed([f"Rule 1\n{FULL}"] * 4)
    result.multi_column_pages = [2, 3]
    assert make_notes(result) == ["Multi-column pages read column by column: 2-3."]


def test_no_notes_for_failed_file():
    result = PdfCheckResult(path="x.pdf", errors=["File not found."])
    assert make_notes(result) == []


def test_verdict_warning_numbering_gap():
    texts = [f"Rule {n}\n{FULL}" for n in (1, 2, 3, 5)]
    verdict, reasons = decide_verdict(analysed(texts))
    assert verdict == WARNING
    assert reasons == ["Rule numbering has gaps, missing: 4."]


def test_dotted_gaps_do_not_change_verdict():
    texts = [f"Rule {n}\n1.{n} Title\n{FULL}" for n in (1, 2, 3, 4)] + [f"1.6 Title\n{FULL}"]
    result = analysed(texts)
    assert result.gaps == {"Numbered": ["1.5"]}  # still shown in the report
    assert decide_verdict(result)[0] == OK


def test_verdict_warning_messy_text():
    texts = [f"Rule 1\n{FULL}" + "�" * 5, f"Rule 2\n{FULL}" + "(cid:12)" * 5]
    verdict, reasons = decide_verdict(analysed(texts))
    assert verdict == WARNING
    assert "10 broken characters" in reasons[0]


def test_verdict_fail_on_errors():
    result = PdfCheckResult(path="x.pdf", errors=["The PDF is password protected."])
    assert decide_verdict(result) == (FAIL, ["The PDF is password protected."])


# --- Limits ---------------------------------------------------------------------------
def test_size_limit():
    assert check_size_limit(50 * MB) is None
    message = check_size_limit(60 * MB)
    assert "60.0 MB" in message and "limit is 50 MB" in message


def test_page_limit():
    assert check_page_limit(1000) is None
    assert "limit is 1000 pages" in check_page_limit(1200)
    assert check_page_limit(0) == "The PDF has no pages."


def test_missing_file_fails(tmp_path):
    from learnbot.pdf_check import check_pdf

    result = check_pdf(tmp_path / "nope.pdf")
    assert result.verdict == FAIL
    assert result.reasons == ["File not found."]


def test_non_pdf_file_fails_with_friendly_message(tmp_path):
    from learnbot.pdf_check import check_pdf

    fake = tmp_path / "notes.pdf"
    fake.write_text("this is not a pdf")
    result = check_pdf(fake)
    assert result.verdict == FAIL
    assert "could not be" in result.reasons[0]
