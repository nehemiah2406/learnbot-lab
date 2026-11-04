"""Score search answers against the eval set. Works for any answering method
(baseline now, RAG in Phase 4): it only needs doc, page and text of the top hits.
"""

from collections import Counter

from learnbot import config
from learnbot.baseline import NOT_FOUND, Hit, tokenize
from learnbot.eval_check import (
    normalize, numbers_in, parse_other_answers, parse_sources, row_pages, split_pair,
)
from learnbot.units import WORD_NUMBERS

# Outcomes
RIGHT = "right"  # answered, top-1 piece is from the right doc + page
CORRECT_OTHER = "correct_other_source"  # other doc/page, but the piece contains the source_quote
WRONG = "wrong"  # answered, top-1 piece does not support the answer (must become 0)
MISSED = "missed"  # eval question, but said "Not in this document"
REFUSED = "refused"  # trap, correctly said "Not in this document"
TRAP_ANSWERED = "trap_answered"  # trap, but gave an answer (also wrong)
NOT_TESTED = "not_tested"  # Phase 4: no AI could be reached ("AI busy"); the run is incomplete


def right_sources(row):
    """{(doc, page)}: the row's own page(s) (compare: either), its accepted_sources and the
    pages of its other_answers."""
    own = {(row["doc"], p) for p in row_pages(row) or []}
    others = {(doc, page) for doc, page, _ in parse_other_answers(row.get("other_answers", "")) or []}
    return own | set(parse_sources(row.get("accepted_sources", "")) or []) | others


def on_right_page(row, hit):
    """True if the hit is from one of the row's right sources."""
    return (hit.chunk.doc, hit.chunk.page) in right_sources(row)


def key_words(text):
    """Content words of 3+ letters (no numbers, no common words)."""
    return {t for t in tokenize(text) if t.isalpha() and len(t) >= 3}


def exact_answer_in(expected_answer, text):
    """All numbers and all key words of the expected answer appear in the text."""
    numbers_ok = numbers_in(expected_answer) <= numbers_in(text)
    words_ok = key_words(expected_answer) <= set(tokenize(text))
    return numbers_ok and words_ok


def has_source_quote(row, hit):
    """True if the hit's text contains the row's source_quote (compare: either quote), normalised."""
    text = normalize(hit.chunk.text)
    return any(normalize(q) in text for q in split_pair(row["source_quote"]) if q)


def outcome(row, is_trap, verdict, hits):
    """RIGHT / CORRECT_OTHER / WRONG / MISSED for questions, REFUSED / TRAP_ANSWERED for traps."""
    if is_trap:
        return REFUSED if verdict == NOT_FOUND else TRAP_ANSWERED
    if verdict == NOT_FOUND:
        return MISSED
    if on_right_page(row, hits[0]):
        return RIGHT
    return CORRECT_OTHER if has_source_quote(row, hits[0]) else WRONG


def correct_count(outcomes):
    return sum(1 for o in outcomes if o in (RIGHT, CORRECT_OTHER, REFUSED))


def outcome_at(row, is_trap, hits, min_score):
    verdict = NOT_FOUND if not hits or hits[0].score < min_score else None
    return outcome(row, is_trap, verdict, hits)


def sweep(results, thresholds):
    """For each threshold: counts of each outcome. results = [(row, is_trap, hits)]."""
    table = []
    for t in thresholds:
        outcomes = [outcome_at(row, trap, hits, t) for row, trap, hits in results]
        counts = {o: outcomes.count(o) for o in (RIGHT, CORRECT_OTHER, WRONG, MISSED, REFUSED, TRAP_ANSWERED)}
        table.append((t, counts, correct_count(outcomes)))
    return table


# --- Phase 4: scoring an AI answer (learnbot.answer.Answer) --------------------------
def same_numbers(text):
    """Numbers in the text, with number words as digits ("four" -> "4")."""
    return {WORD_NUMBERS.get(n, n) for n in numbers_in(text)}


def numbers_differ(expected_answer, shown_answer, question, given=""):
    """True if a number of the expected answer is missing from the shown answer, or the
    shown answer has a number that is neither expected nor in the question. given: text
    shown with the answer whose numbers count as shown (a quiz question's own wording;
    the proof check requires them to be in the quote or the piece title)."""
    expected, shown = same_numbers(expected_answer), same_numbers(shown_answer)
    return not expected <= shown | same_numbers(given) or not shown <= expected | same_numbers(question)


def score_answer(row, is_trap, ans):
    """(outcome, reason) for one Answer. Outcomes as in Phase 3; reason explains failures.
    "AI busy" is NOT_TESTED, never a pass: no AI looked at the question."""
    if ans.status == "ai_busy":
        return NOT_TESTED, ans.reason + (f" ({ans.detail})" if ans.detail else "")
    if is_trap:
        if ans.status != "answered":
            return REFUSED, ""
        where = ", ".join(f"{s['doc']} p.{s['page']}" for s in ans.sources)
        return TRAP_ANSWERED, f"answered from {where}"
    right_sent = any(on_right_page(row, Hit(0, c)) for c in ans.pieces)
    if ans.status != "answered":
        reason = ans.reason + (f" ({ans.detail})" if ans.detail else "")
        return MISSED, reason if right_sent else f"search miss (right page not sent); {reason}"
    given = getattr(ans, "question", "")  # a study item's question (a chat answer has none)
    for doc, page, text in parse_other_answers(row.get("other_answers", "")) or []:
        # Another exact answer of the document (other_answers), shown from its own page.
        if (any((s["doc"], s["page"]) == (doc, page) for s in ans.sources)
                and not numbers_differ(text, ans.text, row["question"], given)):
            return RIGHT, f"other answer from {doc} p.{page}"
    if numbers_differ(row["expected_answer"], ans.text, row["question"], given):
        expected, shown = sorted(same_numbers(row["expected_answer"])), sorted(same_numbers(ans.text))
        return WRONG, f"numbers differ: expected {expected}, shown {shown}"
    if any(hit_on_right_page(row, s) for s in ans.sources):
        return RIGHT, ""
    for s in ans.sources:
        page_pieces = [c for c in ans.pieces if (c.doc, c.page) == (s["doc"], s["page"])]
        if any(has_source_quote(row, Hit(0, c)) for c in page_pieces):
            return CORRECT_OTHER, f"from {s['doc']} p.{s['page']}"
    return WRONG, "answer shown is not supported by the expected source"


def feature_gate(outcomes, slowest_s):
    """Failures of one feature's test run ([] = passed), PLAN.md feature gate. outcomes:
    one per question and trap; slowest_s: the slowest item, in seconds."""
    failures = []
    count = Counter(outcomes)
    if count[WRONG]:
        failures.append(f"wrong {count[WRONG]}")
    if count[TRAP_ANSWERED]:
        failures.append(f"traps answered {count[TRAP_ANSWERED]}")
    if count[NOT_TESTED]:
        failures.append(f"not tested (AI busy) {count[NOT_TESTED]}")
    kept = count[RIGHT] + count[CORRECT_OTHER]
    if kept < config.STUDY_MIN_KEPT:
        failures.append(f"only {kept} kept (at least {config.STUDY_MIN_KEPT} needed)")
    if slowest_s >= 10:
        failures.append(f"slowest {slowest_s:.1f} s (must be under 10 s)")
    return failures


def hit_on_right_page(row, source):
    return (source["doc"], source["page"]) in right_sources(row)


def choose_threshold(table):
    """Most correct outcomes (right + correct other source + refused); on a tie the HIGHER threshold (never guess)."""
    best = max(correct for _, _, correct in table)
    return max(t for t, _, correct in table if correct == best)
