"""Score search answers against the eval set. Works for any answering method
(baseline now, RAG in Phase 4): it only needs doc, page and text of the top hits.
"""

from learnbot.baseline import NOT_FOUND, tokenize
from learnbot.eval_check import numbers_in, row_pages

# Outcomes
RIGHT = "right"  # answered, top-1 piece is from the right doc + page
WRONG = "wrong"  # answered, top-1 piece is from a wrong doc or page (must become 0)
MISSED = "missed"  # eval question, but said "Not in this document"
REFUSED = "refused"  # trap, correctly said "Not in this document"
TRAP_ANSWERED = "trap_answered"  # trap, but gave an answer (also wrong)


def on_right_page(row, hit):
    """True if the hit is from the row's doc and one of its pages (compare: either page)."""
    return hit.chunk.doc == row["doc"] and hit.chunk.page in (row_pages(row) or [])


def key_words(text):
    """Content words of 3+ letters (no numbers, no common words)."""
    return {t for t in tokenize(text) if t.isalpha() and len(t) >= 3}


def exact_answer_in(expected_answer, text):
    """All numbers and all key words of the expected answer appear in the text."""
    numbers_ok = numbers_in(expected_answer) <= numbers_in(text)
    words_ok = key_words(expected_answer) <= set(tokenize(text))
    return numbers_ok and words_ok


def outcome(row, is_trap, verdict, hits):
    """One of RIGHT / WRONG / MISSED for questions, REFUSED / TRAP_ANSWERED for traps."""
    if is_trap:
        return REFUSED if verdict == NOT_FOUND else TRAP_ANSWERED
    if verdict == NOT_FOUND:
        return MISSED
    return RIGHT if on_right_page(row, hits[0]) else WRONG


def correct_count(outcomes):
    return sum(1 for o in outcomes if o in (RIGHT, REFUSED))


def outcome_at(row, is_trap, hits, min_score):
    verdict = NOT_FOUND if not hits or hits[0].score < min_score else None
    return outcome(row, is_trap, verdict, hits)


def sweep(results, thresholds):
    """For each threshold: counts of each outcome. results = [(row, is_trap, hits)]."""
    table = []
    for t in thresholds:
        outcomes = [outcome_at(row, trap, hits, t) for row, trap, hits in results]
        counts = {o: outcomes.count(o) for o in (RIGHT, WRONG, MISSED, REFUSED, TRAP_ANSWERED)}
        table.append((t, counts, correct_count(outcomes)))
    return table


def choose_threshold(table):
    """Most correct outcomes (right + refused); on a tie the HIGHER threshold (never guess)."""
    best = max(correct for _, _, correct in table)
    return max(t for t, _, correct in table if correct == best)
