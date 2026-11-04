# Quiz rules

Every quiz question LearnBot makes (`src/learnbot/quiz.py`) must pass ALL of these rules.
A question that fails any rule is dropped, never shown to the user.
They apply to any uploaded document, not one book.

## Content

1. **One correct option.** Exactly one option is correct; the question has 4 options in total.
2. **Answer from the source text.** The correct option is supported by a `source_quote`: an exact sentence copied from the document text (same column-aware reading as `read_page_text()`), found on the stated page.
3. **Three clearly wrong options.** Each wrong option must be clearly wrong *according to the document text*, not just "less good". No option may be partly correct.
4. **No "all of the above" / "none of the above"** (or "both A and B" style options).
5. **Exact numbers.** Numbers, units, distances, lights, signals and times in the correct option are exactly as in the source quote (same digits or number words, same units). Never rounded, converted or invented.
6. **Wrong numbers are real alternatives.** A wrong option may use a number from elsewhere in the document (e.g. "2 miles" vs "3 miles"), but must not be correct for the situation asked.

## Source

7. **Rule/section and page shown.** Every question shows its rule or section label and the PDF page number (as shown in the PDF viewer, page 1 = first page).
8. **One rule set only.** International and Inland rules are never mixed in one question. If a document has both, the question says which one it asks about, and all options come from that one.

## Checks before a question is kept

9. The source quote is found on the stated page (spaces and line breaks ignored).
10. Every number in the correct option appears in the source quote.
11. No two options are the same after normalising spaces and case.
12. If any check fails or LearnBot is unsure, the question is dropped. Fewer good questions are better than one wrong answer key.

## What a person must still check

Code proves the right answer and catches a wrong option that is in the source quote. Code cannot fully prove rules 3 and 6 (each wrong option is wrong according to the document). So the feature test prints every kept question for a person to read. A "wrong" option that is actually correct counts as a wrong question in the score.
