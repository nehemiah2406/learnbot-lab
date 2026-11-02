"""Reserved rules are answered by code with their location (no AI). Made-up pieces."""

from learnbot.chunking import Chunk
from learnbot.reserved import RESERVED_ANSWER, asked_references, reserved_source
from learnbot.rule_sets import RuleSets

R28_INLAND = Chunk("rules.pdf", 87, "—INLAND— Lights and Shapes Rule 28", "[Reserved]")
R28_INTL = Chunk("rules.pdf", 86, "—INTERNATIONAL— Lights and Shapes Rule 28 Vessels Constrained by Their Draft",
                 "A vessel constrained by her draft may exhibit three all-round red lights in a vertical line.")
R3_INLAND = Chunk("rules.pdf", 16, "—INLAND— Rule 3 Definitions",
                  "(g) The term vessel restricted in her ability to maneuver means a vessel. (h) [Reserved] "
                  "(i) The word underway means that a vessel is not at anchor.")
R3_INTL = Chunk("rules.pdf", 15, "—INTERNATIONAL— Rule 3 General Definitions",
                "(h) The term vessel constrained by her draft means a power-driven vessel which")
ALL = [R28_INLAND, R28_INTL, R3_INLAND, R3_INTL]
PAGES = {(c.doc, c.page): f"{c.title}\n{c.text}\n{c.page}" for c in ALL}
RULES = RuleSets(ALL)


def find(question, pieces):
    return reserved_source(question, pieces, lambda d, p: PAGES.get((d, p)), RULES)


def test_reserved_rule_is_found_with_its_location():
    src = find("What does Inland Rule 28 say?", [R28_INLAND, R3_INLAND])
    assert src == {"doc": "rules.pdf", "page": 87, "quote": "Rule 28 [Reserved]",
                   "title": "—INLAND— Lights and Shapes Rule 28"}


def test_reserved_paragraph_is_found():
    src = find("What is Inland Rule 3(h)?", [R3_INLAND])
    assert (src["page"], src["quote"]) == (16, "(h) [Reserved]")


def test_rule_with_text_is_not_reserved():
    assert find("What does International Rule 28 say?", [R28_INTL]) is None
    assert find("What is International Rule 3(h)?", [R3_INTL]) is None
    # The best matching piece (first in search order) has text: no reserved answer.
    assert find("What is Rule 3(h)?", [R3_INTL, R3_INLAND]) is None


def test_no_rule_named_means_no_reserved_answer():
    assert find("What is a vessel constrained by her draft?", [R3_INLAND]) is None
    assert asked_references("Rule 34(b)(iii) and Annex II") == [
        (r"\bRule\s*34\b", "(iii)"), (r"\bAnnex\s*II\b", None)]


def test_reserved_answer_text():
    assert "reserved" in RESERVED_ANSWER.lower()
