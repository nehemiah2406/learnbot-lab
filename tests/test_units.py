"""General unit detection (not only maritime): measurements = a number WITH a unit."""

import pytest

from learnbot.units import asked_unit, measurements, units_in


@pytest.mark.parametrize("text, expected", [
    ("a masthead light, 6 miles;", ("6", "mile")),
    ("approximately 2,000 yards", ("2000", "yard")),
    ("about 1.15 statute miles", ("1.15", "statute mile")),
    ("visible 6 nautical miles", ("6", "nautical mile")),
    ("not less than 3 inches in height", ("3", "inch")),
    ("ships of length 20m or greater", ("20", "meter")),
    ("a 12 ft boat", ("12", "foot")),
    ("10 km away", ("10", "kilometer")),
    ("5 cm", ("5", "centimeter")),
    ("2 mm thick", ("2", "millimeter")),
    ("a speed of 8 knots", ("8", "knot")),
    ("4 to 6 seconds’ duration", ("6", "second")),
    ("not more than 2 minutes", ("2", "minute")),
    ("within 24 hours", ("24", "hour")),
    ("30 days", ("30", "day")),
    ("42 months after manufacture", ("42", "month")),
    ("every 5 years", ("5", "year")),
    ("an arc of 112.5 degrees", ("112.5", "degree")),
    ("an angle of 45°", ("45", "degree")),
    ("a load of 50 kg", ("50", "kilogram")),
    ("3 tonnes of cargo", ("3", "tonne")),
    ("20 litres of fuel", ("20", "litre")),
    ("a 10% discount", ("10", "percent")),
    ("10 per cent of the crew", ("10", "percent")),
    ("70-200 Hz", ("200", "hertz")),
    ("a fine of $5,000", ("5000", "usd")),
    ("costs ₹ 500", ("500", "inr")),
    ("costs Rs. 1,200", ("1200", "inr")),
    ("costs 300 rupees", ("300", "inr")),
])
def test_measurements_found(text, expected):
    assert expected in measurements(text)


@pytest.mark.parametrize("text", [
    "33 CFR 83.34", "Rule 34(d)", "Annex 1", "paragraph 12 of section 4", "in 2024 the rule", "(37) Distances",
])
def test_references_are_not_measurements(text):
    assert measurements(text) == set()


def test_same_unit_different_spelling_but_never_a_different_unit():
    assert measurements("6 miles") == measurements("6 mile") == measurements("6 mi")
    assert measurements("6 miles") != measurements("6 kilometers")
    assert measurements("6 miles") != measurements("6 nautical miles")


@pytest.mark.parametrize("question, unit", [
    ("Roughly how many yards are in one nautical mile?", "yard"),
    ("How many seconds does a prolonged blast last?", "second"),
    ("How many nautical miles is it?", "nautical mile"),
    ("What is the distance in kilometres?", "kilometer"),
    ("How heavy is the anchor in kg?", "kilogram"),
    ("What is the fee in rupees?", "inr"),
    ("How many $ does it cost?", "usd"),
    ("How long is a nautical mile?", None),
    ("How many short blasts?", None),  # "short" is not a unit
    ("How many of the lights?", None),
    ("What is the range in length?", None),
])
def test_asked_unit(question, unit):
    assert asked_unit(question) == unit


def test_units_in_answer_text():
    assert "yard" in units_in("Approximately 2,000 yards.")
    assert "yard" in units_in("It is given in yards")
    assert "kilometer" not in units_in("6 miles")
