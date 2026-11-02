"""Measurements (a number WITH a unit) in any text: "6 miles", "20m", "70-200 Hz", "45°",
"10%", "$5", "Rs. 500". General, not only maritime. A number followed by any other word
("33 CFR", "Rule 34", "Annex 1") is not a measurement.

Each unit has a canonical name, so "mile" / "miles" / "mi" are the same unit, but a
different unit ("6 kilometers" for "6 miles") never is.
"""

import re

_UNIT_NAMES = {
    # length
    "mile": "mile miles mi", "nautical mile": "nautical-mile nautical-miles nm",
    "statute mile": "statute-mile statute-miles", "yard": "yard yards yd yds",
    "foot": "foot feet ft", "inch": "inch inches", "meter": "meter meters metre metres m",
    "kilometer": "kilometer kilometers kilometre kilometres km", "centimeter": "centimeter centimeters "
    "centimetre centimetres cm", "millimeter": "millimeter millimeters millimetre millimetres mm",
    "fathom": "fathom fathoms",
    # speed
    "knot": "knot knots kn kt kts", "mph": "mph", "km/h": "km/h kph kmh",
    # time
    "second": "second seconds sec secs", "minute": "minute minutes min mins",
    "hour": "hour hours hr hrs", "day": "day days", "week": "week weeks", "month": "month months",
    "year": "year years yr yrs",
    # angle, temperature
    "degree": "degree degrees deg °",
    # mass
    "kilogram": "kilogram kilograms kg kgs", "gram": "gram grams", "tonne": "tonne tonnes",
    "ton": "ton tons", "pound": "pound pounds lb lbs",
    # volume
    "litre": "litre litres liter liters", "millilitre": "millilitre millilitres milliliter milliliters ml",
    "gallon": "gallon gallons gal",
    # other
    "percent": "percent %", "hertz": "hz hertz", "kilohertz": "khz kilohertz", "megahertz": "mhz megahertz",
    "watt": "watt watts w", "kilowatt": "kilowatt kilowatts kw", "volt": "volt volts v",
    # currency written after the number
    "inr": "rupee rupees inr rs", "usd": "dollar dollars usd", "eur": "euro euros eur",
    "gbp": "gbp",
}
UNITS = {alias: name for name, aliases in _UNIT_NAMES.items() for alias in aliases.split()}
# Words that join a following unit word: "6 nautical miles" -> one unit.
_JOINERS = ("nautical", "statute")
# Currency written before the number: "$5", "₹ 500", "Rs. 500", "INR 500".
_CURRENCY_BEFORE = {"$": "usd", "usd": "usd", "₹": "inr", "rs": "inr", "rs.": "inr", "inr": "inr",
                    "€": "eur", "eur": "eur", "£": "gbp", "gbp": "gbp"}

NUMBER = r"\d+(?:[.,]\d+)*"
_AFTER = re.compile(rf"({NUMBER})\s*((?:{'|'.join(_JOINERS)})[\s-]+[a-z]+|[a-z/%°]+)")
_BEFORE = re.compile(rf"(\$|₹|€|£|\brs\.?|\binr\b|\busd\b|\beur\b|\bgbp\b)\s*({NUMBER})")


def _clean(text):
    return re.sub(r"\bper\s+cent\b", "percent", text.lower().replace("’", "'"))


def _unit_name(word):
    word = re.sub(r"[\s-]+", "-", word.strip())
    return UNITS.get(word)


def measurements(text):
    """{(number, canonical unit)}; number without thousands commas ("2,000" -> "2000")."""
    text = _clean(text)
    found = set()
    for number, word in _AFTER.findall(text):
        unit = _unit_name(word)
        if unit:
            found.add((number.replace(",", ""), unit))
    for symbol, number in _BEFORE.findall(text):
        found.add((number.replace(",", ""), _CURRENCY_BEFORE[symbol.strip()]))
    return found


_ASKED = [
    re.compile(r"\bhow many ([a-z/%°]+(?:[\s-]+[a-z]+)?)"),  # "how many yards", "how many nautical miles"
    re.compile(r"\bin ([a-z/%°]+(?:[\s-]+[a-z]+)?)\s*\??\s*$"),  # "... in kilometres?"
    re.compile(r"\bhow many (\$|₹|€|£)"),
]


def asked_unit(question):
    """Canonical unit a question asks for ("how many yards" -> "yard"), or None."""
    text = _clean(question.strip())
    for pattern in _ASKED:
        match = pattern.search(text)
        if not match:
            continue
        words = match.group(1)
        if words in _CURRENCY_BEFORE:
            return _CURRENCY_BEFORE[words]
        # Try "nautical miles" first, then the first word alone ("yards are" -> "yards").
        for candidate in (words, words.split()[0]):
            unit = _unit_name(candidate)
            if unit:
                return unit
    return None


def units_in(text):
    """Canonical units named in the text, with or without a number ("in yards" -> {"yard"})."""
    text = _clean(text)
    found = {UNITS[w] for w in re.findall(r"[a-z/%°]+", text) if w in UNITS and len(w) > 2}
    found |= {u for _, u in measurements(text)}
    for joiner in _JOINERS:
        for word in re.findall(rf"\b{joiner}[\s-]+([a-z]+)", text):
            unit = _unit_name(f"{joiner} {word}")
            if unit:
                found.add(unit)
    return found
