"""Proof check cases with made-up pieces (no AI, no PDF)."""

from learnbot.chunking import Chunk
from learnbot.proof import check, number_units, same_text
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
        ("200", "hz"), ("200", "meters"), ("6", "seconds"), ("20", "m")}
    assert number_units("approximately 2,000 yards") == {("2000", "yards")}
