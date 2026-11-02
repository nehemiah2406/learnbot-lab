"""Proof check cases with made-up pieces (no AI, no PDF)."""

from learnbot.chunking import Chunk
from learnbot.proof import asked_unit, check, number_units, same_text
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
    assert run(reply(answer="3 miles", quote=LONG_QUOTE), question=question).reason == "quote_not_focused"
    assert run(reply(answer="6 miles", quote=LONG_QUOTE), question=question).reason == "quote_not_focused"
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
