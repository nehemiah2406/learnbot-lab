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


# --- Counts: a number used to count something ("one all-round light", "two short blasts") ---
WORD_NUMBERS = {
    w: str(i) for i, w in enumerate(
        "zero one two three four five six seven eight nine ten eleven twelve thirteen "
        "fourteen fifteen sixteen seventeen eighteen nineteen twenty".split())
}
WORD_NUMBERS.update({"thirty": "30", "forty": "40", "fifty": "50", "sixty": "60",
                     "seventy": "70", "eighty": "80", "ninety": "90"})
# A number after one of these words is a reference, not a count: "Rule 22 lights", "page 4".
_REFERENCE_WORDS = {
    "rule", "rules", "annex", "section", "sections", "paragraph", "paragraphs", "para", "chapter",
    "part", "parts", "subpart", "page", "pages", "article", "regulation", "cfr", "usc", "u.s.c.",
    "figure", "fig", "table", "item", "no", "no.", "number", "appendix", "title", "volume", "§",
    "chart", "edition", "step", "phase", "class", "category", "type", "level", "tier", "group",
    "zone", "district", "region", "route", "version",
}
# "one" after these words is not a count: "no one", "the one", "each one".
_NOT_A_COUNT_AFTER = {"no", "any", "each", "every", "the", "this", "that", "which", "some"}
# A count is followed by a noun (or an adjective of one): "two short blasts", "one all-round
# light". Not by these words: "one of the", "one or more", "one another", "in 2024 the".
_NOT_A_NOUN = {
    "of", "or", "and", "to", "the", "a", "an", "in", "on", "at", "for", "by", "with", "from",
    "is", "are", "was", "were", "be", "shall", "may", "must", "as", "than", "another", "other",
    "more", "less", "nor", "but", "which", "that", "who", "it", "if", "when",
}
_COUNT = re.compile(rf"(?<![\w(§.,/-])({NUMBER}|{'|'.join(WORD_NUMBERS)})\s+([A-Za-z][\w-]*)", re.IGNORECASE)


def counts(text):
    """{number as digits} for numbers that count something ("one all-round light" -> "1").
    Not counted: references ("Rule 22", "33 CFR", "(26)"), "no one", "one of the", and a
    number before a capitalised word (a title or reference)."""
    text = text.replace("’", "'")
    found = set()
    for match in _COUNT.finditer(text):
        number, word = match.group(1), match.group(2)
        before = text[:match.start()].split()
        prev = before[-1].lower() if before else ""
        is_word = number.lower() in WORD_NUMBERS
        if prev in _REFERENCE_WORDS or word[0].isupper() or word.lower() in _NOT_A_NOUN:
            continue
        if is_word and prev in _NOT_A_COUNT_AFTER:
            continue
        found.add(WORD_NUMBERS[number.lower()] if is_word else number.replace(",", ""))
    return found


def number_values(text):
    """Every number in the text as digits, number words included ("four" -> "4", "2,000" -> "2000")."""
    text = text.lower()
    digits = {n.replace(",", "") for n in re.findall(NUMBER, text)}
    words = {WORD_NUMBERS[w] for w in re.findall(r"[a-z]+", text) if w in WORD_NUMBERS}
    return digits | words
