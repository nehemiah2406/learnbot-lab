"""Flashcards from one document. Any file.

The front is a question or term; the back is the short exact answer, with page and quote.
The back passes the proof check, with the front as the question (learnbot.study). A card
that fails any check is dropped, never shown.
"""

from learnbot import study

PROMPT = """You write ONE flashcard using ONLY the numbered pieces of text below, taken from the user's document.

Rules:
""" + study.SOURCE_RULES + """
10. "question" is the front of the card: one short question about the topic.
11. "answer" is the back of the card: the short exact answer, in simple English. Add no other facts.

Reply with JSON only, in one of these two forms:
{{"found": true, "question": "...", "answer": "...", "source": {{"doc": "file.pdf", "page": 12, "quote": "..."}}}}
{{"found": false}}

Topic: {topic}

Pieces:
{pieces}
"""


def build_prompt(topic, pieces):
    blocks = [f"[{i}] doc: {c.doc} | page: {c.page} | title: {c.title}\n{c.text}"
              for i, c in enumerate(pieces, start=1)]
    return PROMPT.format(topic=(topic or "any clear fact in the pieces").strip(), pieces="\n\n".join(blocks))


def make_card(topic, searcher, chain, pieces=None):
    """One checked flashcard as a StudyItem (question = front, text = back), or "Not in this document"."""
    return study.make_item(topic, searcher, chain, build_prompt, pieces=pieces, sentence_checks=(study.CONDITION_CHECK, study.WORDS_CHECK))


def make_cards(topic, searcher, chain, count):
    """(cards, dropped, AI busy?): up to count different cards on the topic, or from across
    the document if topic is None."""
    return study.make_set(lambda t, s, pieces: make_card(t, s, chain, pieces), topic, searcher, count)
