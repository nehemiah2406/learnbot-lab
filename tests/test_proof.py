"""Proof check cases with made-up pieces (no AI, no PDF)."""

from learnbot.chunking import Chunk
from learnbot import config
from learnbot.proof import asked_unit, check, compares, list_items, number_units, same_text, shown_quote
from learnbot.rule_sets import RuleSets

P45 = Chunk("rules.pdf", 45, "—INTERNATIONAL— Rule 22 Visibility of Lights",
            "(a) In vessels of 50 meters or more in length: − a masthead light, 6 miles; "
            "− a sidelight, 3 miles; − a sternlight, 3 miles;")
P46 = Chunk("rules.pdf", 46, "—INLAND— Rule 22 Visibility of lights",
            "(a) In a vessel of 50 meters or more in length: (i) A masthead light, 6 miles;")
G16 = Chunk("guide.pdf", 16, "Pyrotechnic Devices",
            "Check the expiration date (42 months after the date of manufacture). Keep the "
            "look- out signals dry.")
PAGES = {
    ("rules.pdf", 45): "—INTERNATIONAL—\nRule 22\n(a) In vessels of 50 meters or more in length:\n"
                       "− a masthead light, 6 miles;\n− a sidelight, 3 miles;\n− a sternlight, 3 miles;",
    ("rules.pdf", 46): "—INLAND—\nRule 22\n(a) In a vessel of 50 meters or more in length:\n"
                       "(i) A masthead light, 6 miles;",
    ("guide.pdf", 16): "Pyrotechnic Devices\nCheck the expiration date (42 months after the date of "
                       "manufacture). Keep the look-\nout signals dry.",
}
SENT = [P45, P46, G16]
RULES = RuleSets(SENT)
QUESTION = "Under the International Rules, what is the range of a masthead light on a vessel of 50 meters?"
GOOD_QUOTE = "In vessels of 50 meters or more in length: − a masthead light, 6 miles;"


def page_text(doc, page):
    return PAGES.get((doc, page))


def reply(answer="6 miles", quote=GOOD_QUOTE, doc="rules.pdf", page=45):
    return {"found": True, "answer": answer, "sources": [{"doc": doc, "page": page, "quote": quote}]}


def run(r, question=QUESTION, sent=SENT):
    return check(question, r, sent, page_text, RULES)


def test_good_answer_passes():
    assert run(reply()).ok


def test_wrong_number_is_rejected():
    assert run(reply(answer="5 miles")).reason == "number_not_in_quote"


def test_changed_unit_is_rejected():
    assert run(reply(answer="6 kilometers")).reason == "unit_not_in_quote"
    assert run(reply(answer="6 nautical miles")).reason == "unit_not_in_quote"


def test_quote_not_on_page_is_rejected():
    assert run(reply(quote="In vessels of 50 meters or more: a masthead light, 6 miles;")).reason == "quote_not_on_page"
    # Real text, but from page 46, claimed as page 45:
    assert run(reply(quote="(i) A masthead light, 6 miles;")).reason == "quote_not_on_page"


def test_page_not_sent_is_rejected():
    assert run(reply(page=99)).reason == "page_not_sent"
    assert run(reply(), sent=[P46, G16]).reason == "page_not_sent"


def test_wrong_rule_set_is_rejected():
    r = reply(quote="In a vessel of 50 meters or more in length: (i) A masthead light, 6 miles;", page=46)
    assert run(r).reason == "wrong_rule_set"
    assert run(r, question=QUESTION.replace("International", "Inland")).ok


def test_rule_set_not_checked_for_documents_without_rule_sets():
    r = reply(answer="42 months after manufacture", quote="Check the expiration date (42 months after the date",
              doc="guide.pdf", page=16)
    assert run(r, question="Under the International Rules, when do pyrotechnic signals expire?").ok


def test_off_topic_quote_is_rejected():
    r = reply(answer="3 miles", quote="a sidelight, 3 miles; − a sternlight, 3 miles;")
    result = run(r, question="Under the International Rules, what is the range of a masthead light?")
    assert result.reason == "off_topic"


def test_answer_must_have_the_unit_the_question_asks_for():
    r = reply(answer="6", quote=GOOD_QUOTE)
    question = "Under the International Rules, how many miles must a masthead light on a 50 meters vessel be seen?"
    assert run(r, question=question).reason == "unit_missing"
    assert run(reply(answer="6 miles"), question=question).ok
    assert run(reply(answer="6 miles"), question=question.replace("how many miles", "how many mile")).ok
    km = question.replace("how many miles", "how many kilometers")
    assert run(reply(answer="6 miles"), question=km).reason == "unit_missing"


def test_asked_unit():
    assert asked_unit("Roughly how many yards are in one nautical mile?") == "yard"
    assert asked_unit("How long is a nautical mile?") is None


def test_quote_with_cfr_reference_is_not_refused_as_unfocused():
    # "33 CFR" is a law reference, not a measurement (NAV-08's quote had one).
    piece = Chunk("rules.pdf", 108, "—INLAND— Rule 34",
                  "33 CFR 83.34 (iii) The light used for this signal shall, if fitted, be one all-round "
                  "white or yellow light, visible at a minimum range of 2 miles")
    pages = {("rules.pdf", 108): piece.text}
    r = reply(answer="One all-round white or yellow light, visible at a minimum range of 2 miles.",
              quote=piece.text, page=108)
    question = "Under the Inland Rules, what light may supplement whistle signals and what is its minimum range?"
    result = check(question, r, [piece], lambda d, p: pages.get((d, p)), RuleSets([piece]))
    assert result.ok, result


LONG_QUOTE = ("In vessels of 50 meters or more in length: − a masthead light, 6 miles; − a sidelight, 3 miles; "
              "− a sternlight, 3 miles;")


def test_quote_with_other_measurements_is_rejected():
    # Real case (NAV-10): the AI quoted the whole list and answered with another item's range.
    question = "Under the International Rules, how far away must the top white light of a big ship (50 m or longer) be visible?"
    # "3 miles" is in two items (sidelight, sternlight): no single item -> refused.
    assert run(reply(answer="3 miles", quote=LONG_QUOTE), question=question).reason == "quote_not_focused"
    # The focused quote of the right item passes; "50 meters" is the question's condition.
    assert run(reply(answer="6 miles", quote=GOOD_QUOTE), question=question.replace("50 m ", "50 meters ")).ok


def test_answer_with_all_measurements_of_its_quote_passes():
    r = reply(answer="6 miles for the masthead light, 3 miles for the sidelight",
              quote="a masthead light, 6 miles; − a sidelight, 3 miles;")
    assert run(r, question="Under the International Rules, what are the ranges of the masthead light "
                           "and the sidelight on a 50 meters vessel?").reason != "quote_not_focused"


def test_broad_title_word_does_not_make_off_topic_quote_pass():
    # P45's title "Visibility of Lights" shares "light" with the question; the quote is
    # about the sidelight, not the masthead light. Must stay rejected (wrong number risk).
    r = reply(answer="3 miles", quote="a sidelight, 3 miles; − a sternlight, 3 miles;")
    question = "Under the International Rules, what is the range of a masthead light?"
    assert "Lights" in P45.title and run(r, question=question).reason == "off_topic"


def test_question_number_must_be_in_quote():
    r = reply(quote="a masthead light, 6 miles; − a sidelight, 3 miles;")
    assert run(r).reason == "off_topic"  # question says 50 meters, quote does not


def test_quote_too_short_or_no_source_is_rejected():
    assert run(reply(quote="6 miles")).reason == "quote_too_short"
    assert run({"found": True, "answer": "6 miles", "sources": []}).reason == "no_answer"
    assert run({"found": True, "answer": "", "sources": reply()["sources"]}).reason == "no_answer"


def test_quote_matching_is_normalised():
    curly = reply(quote="In vessels of 50 meters or more in length: - a masthead light, 6 miles;")
    assert run(curly).ok
    hyphen = reply(answer="Keep them dry", quote="Keep the look- out signals dry.", doc="guide.pdf", page=16)
    assert run(hyphen, question="How should signals be kept on look-out?").ok
    assert same_text("look- out") == same_text("look-\nout")


def test_number_units():
    assert number_units("70-200 Hz, for 200 meters; 4 to 6 seconds; 20m") == {
        ("200", "hertz"), ("200", "meter"), ("6", "second"), ("20", "meter")}
    assert number_units("approximately 2,000 yards") == {("2000", "yard")}
    assert number_units("33 CFR 83.34 and Rule 34(d)") == set()


# --- Fix 1: a list quote is narrowed to its one answering item ---------------------------
def test_list_quote_is_narrowed_to_the_one_item_with_the_answer():
    question = "Under the International Rules, how far away must the top white light of a big ship (50 m or longer) be visible?"
    result = run(reply(answer="6 miles", quote=LONG_QUOTE), question=question)
    assert result.ok
    (source,) = result.sources
    assert source["quote"] == "a masthead light, 6 miles"
    assert source["lead"] == "In vessels of 50 meters or more in length:"
    assert shown_quote(source) == "In vessels of 50 meters or more in length: … a masthead light, 6 miles"


def test_narrowed_item_must_still_fit_the_question():
    # The only 6-mile item is the masthead light; the question is about the sidelight.
    question = "Under the International Rules, what is the range of a sidelight on a vessel of 50 meters?"
    assert run(reply(answer="6 miles", quote=LONG_QUOTE), question=question).reason == "off_topic"


def test_list_items():
    lead, items = list_items(LONG_QUOTE)
    assert lead.endswith("length:") and items == ["a masthead light, 6 miles", "a sidelight, 3 miles",
                                                   "a sternlight, 3 miles"]
    assert list_items("(i) A masthead light, 6 miles; (ii) A sidelight, 2 miles;")[1] == [
        "(i) A masthead light, 6 miles", "(ii) A sidelight, 2 miles"]
    assert list_items("Keep the look-out signals dry and all-round lights clean.") == ("", [])


# --- Fix 2: every number of the quote (counts too) must be in the answer ------------------
R34 = Chunk("rules.pdf", 108, "—INLAND— Rule 34",
            "(iii) The light used for this signal shall, if fitted, be one all-round white or yellow light, "
            "visible at a minimum range of 2 miles")
Q34 = "Under the Inland Rules, what light may supplement whistle signals and what is its minimum range?"


def run34(answer):
    r = reply(answer=answer, quote=R34.text, page=108)
    return check(Q34, r, [R34], lambda d, p: R34.text if (d, p) == ("rules.pdf", 108) else None, RuleSets([R34]))


def test_answer_that_drops_a_count_is_refused():
    # Real case (NAV-08): the AI wrote "an all-round ... light"; the quote says "one".
    result = run34("An all-round white or yellow light, visible at a minimum range of 2 miles.")
    assert result.reason == "quote_not_focused" and "1" in result.detail
    assert run34("One all-round white or yellow light, visible at 2 miles.").ok


def test_one_as_a_pronoun_or_reference_is_not_a_count():
    piece = Chunk("rules.pdf", 7, "Rule 8", "No one shall alter course unless one of the vessels sounds "
                  "two short blasts as in Rule 34 and 33 CFR 83.34 (26) Distances")
    r = reply(answer="Two short blasts.", quote=piece.text, page=7)
    question = "What signal is sounded before a course change?"
    result = check(question, r, [piece], lambda d, p: piece.text, RuleSets([piece]))
    assert result.ok, result


# --- Fix 3: one source per answer unless the question compares ----------------------------
def test_two_sources_only_when_the_question_compares():
    two = {"found": True, "answer": "6 miles", "sources": reply()["sources"] + [
        {"doc": "rules.pdf", "page": 46, "quote": "(i) A masthead light, 6 miles;"}]}
    assert run(two, question="What is the range of a masthead light on a vessel of 50 meters?").reason == "too_many_sources"
    assert compares("Compare the International and Inland masthead light ranges", RULES)
    assert compares("Under the International and Inland Rules, what is the range?", RULES)
    assert compares("Do both rules require it?", RULES)
    assert not compares("Under the International Rules, what is the range?", RULES)
    assert run(two, question="Under the International and Inland Rules, what is the range of a masthead "
                             "light on a vessel of 50 meters?").ok


# --- Fix 6: paraphrase may pass on the re-ranker score, only above TOPIC_MIN_SCORE --------
def test_paraphrase_passes_only_with_a_high_topic_score(monkeypatch):
    sidelight = reply(answer="3 miles", quote="a sidelight, 3 miles; − a sternlight, 3 miles;")
    question = "Under the International Rules, what is the range of a masthead light?"
    high = lambda q, t: 9.0  # noqa: E731
    monkeypatch.setattr(config, "TOPIC_MIN_SCORE", None)
    assert check(question, sidelight, SENT, page_text, RULES, high).reason == "off_topic"  # off = never rescued
    monkeypatch.setattr(config, "TOPIC_MIN_SCORE", 8.0)
    low = check(question, sidelight, SENT, page_text, RULES, lambda q, t: -2.0)
    assert low.reason == "off_topic" and "topic score -2.00" in low.detail
    # A high score only replaces the word check; the sidelight quote still fails on its numbers.
    assert check(question, sidelight, SENT, page_text, RULES, high).reason != "ok"
