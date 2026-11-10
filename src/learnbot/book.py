"""Book maker: a short study book from one document, one chapter per topic. Any file.

Every line of a book is a fact with its page and quote; there is no free text or summary,
because code cannot prove it. One AI call per chapter asks for up to
config.BOOK_FACTS_PER_CHAPTER facts. Each fact goes through the same checks as a flashcard
(learnbot.study) one at a time; a fact that fails is dropped. A chapter with no facts says why.
One exception, in books only: if the only failure is that the answer leaves out some of its
quote's numbers (the AI often splits one sentence into two facts), the answer becomes the exact
sentence, so the user sees all its numbers in the document's own words.
Each chapter has its own time budget. Replies are saved, so the same book costs no quota twice.
"""

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter

from learnbot import config, study
from learnbot.answer import AI_BUSY_STATUS, ANSWERED, REFUSED, attempts_text
from learnbot.baseline import NOT_FOUND
from learnbot.eval_check import normalize
from learnbot.llm import AllProvidersFailed
from learnbot.proof import shown_quote

FOCUS_CHECK = "proof:quote_not_focused"

PROMPT = """You write facts for one chapter of a study book, using ONLY the numbered pieces of text below, taken from the user's document.

Rules:
""" + study.SOURCE_RULES + """
10. Give up to {max_facts} different facts about the topic, the most useful first. Each fact has its own quote.
11. "question" is one short question about the topic. "answer" is the short exact answer, in simple English. Add no other facts.

Reply with JSON only, in one of these two forms:
{{"found": true, "facts": [{{"question": "...", "answer": "...", "source": {{"doc": "file.pdf", "page": 12, "quote": "..."}}}}]}}
{{"found": false}}

Topic: {topic}

Pieces:
{pieces}
"""


@dataclass
class Fact:
    question: str
    text: str
    sources: list
    status: str = ANSWERED  # lets a fact be scored like a chat answer
    pieces: list = field(default_factory=list)


@dataclass
class Chapter:
    topic: str
    status: str  # ANSWERED, REFUSED or AI_BUSY_STATUS
    text: str = ""  # why there are no facts
    facts: list = field(default_factory=list)
    pieces: list = field(default_factory=list)
    dropped: int = 0
    reason: str = ""  # why not answered, or the checks that dropped facts
    detail: str = ""
    provider: str = ""
    attempts: str = ""
    seconds: float = 0.0


def build_prompt(topic, pieces):
    blocks = [f"[{i}] doc: {c.doc} | page: {c.page} | title: {c.title}\n{c.text}"
              for i, c in enumerate(pieces, start=1)]
    return PROMPT.format(topic=topic.strip(), pieces="\n\n".join(blocks), max_facts=config.BOOK_FACTS_PER_CHAPTER)


def reply_facts(text):
    """The list of facts in the AI's JSON ([] if it found none). Raises ValueError."""
    data = json.loads(study.FENCE.sub("", text or ""))
    if not isinstance(data, dict) or not isinstance(data.get("found"), bool):
        raise ValueError("reply has no found: true/false")
    if not data["found"]:
        return []
    facts = data.get("facts")
    if not isinstance(facts, list):
        raise ValueError("facts is not a list")
    return facts


def checked_fact(topic, raw, pieces, searcher):
    """(Fact, "") if every check passes, else (None, the failed check)."""
    try:
        reply = study.parse_item(json.dumps({"found": True, **raw}))
    except (ValueError, KeyError, TypeError):
        return None, "bad_fact"
    # The AI gave only some of the sentence's numbers or dropped a condition: show the sentence.
    sources, reason, _ = study.check_with_sentence(topic, reply, pieces, searcher, (FOCUS_CHECK, study.CONDITION_CHECK, study.LIMIT_CHECK, study.WORDS_CHECK))
    if reason:
        return None, reason
    return Fact(reply["question"], reply["answer"], sources, pieces=pieces), ""


def make_chapter(topic, searcher, chain):
    """One Chapter (never raises for AI errors)."""
    start = perf_counter()
    pieces = study.topic_pieces(topic, searcher)

    def done(status, text="", **kw):
        return Chapter(topic, status, text, pieces=pieces, seconds=perf_counter() - start, **kw)

    if not pieces:
        return done(REFUSED, NOT_FOUND, reason="no_topic_words")
    budget = config.QUESTION_TIME_BUDGET_S - (perf_counter() - start)
    try:
        text, provider, _ = chain.ask(build_prompt(topic, pieces), budget_s=budget)
    except AllProvidersFailed as failed:
        return done(AI_BUSY_STATUS, study.AI_BUSY_ITEM, reason="ai_busy", detail=attempts_text(failed.attempts))
    info = {"provider": provider, "attempts": attempts_text(getattr(chain, "last_attempts", []))}
    try:
        raws = reply_facts(text)
    except (ValueError, TypeError):
        return done(REFUSED, NOT_FOUND, reason="bad_json", **info)
    if not raws:
        return done(REFUSED, NOT_FOUND, reason="llm_not_found", **info)
    facts, reasons, seen = [], [], set()
    for raw in raws[:config.BOOK_FACTS_PER_CHAPTER]:
        fact, reason = checked_fact(topic, raw, pieces, searcher) if isinstance(raw, dict) else (None, "bad_fact")
        quote = normalize(fact.sources[0]["quote"]) if fact else ""
        if fact and quote not in seen:
            seen.add(quote)
            facts.append(fact)
        else:
            reasons.append(reason or "same_quote")
    reason = ", ".join(reasons)
    if not facts:
        return done(REFUSED, study.nothing_kept(topic, len(reasons), "fact"), dropped=len(reasons), reason=reason, **info)
    return done(ANSWERED, facts=facts, dropped=len(reasons), reason=reason, **info)


def make_book(topics, searcher, chain):
    """One Chapter per topic. Raises ValueError if there are too many or no topics."""
    topics = [t.strip() for t in topics if t.strip()]
    if not topics or len(topics) > config.BOOK_MAX_TOPICS:
        raise ValueError(f"A book needs 1 to {config.BOOK_MAX_TOPICS} topics.")
    return [make_chapter(topic, searcher, chain) for topic in topics]


def render(doc, chapters):
    """The book as Markdown. Every fact shows its page, section and quote."""
    lines = [f"# Study book: {doc}", "", "Every fact below has its page and exact quote from the document.", ""]
    for chapter in chapters:
        lines += [f"## {chapter.topic}", ""]
        if not chapter.facts:
            lines += [chapter.text, ""]
        for fact in chapter.facts:
            lines += [f"**{fact.question}**", "", fact.text, ""]
            for s in fact.sources:
                section = f" ({s['title']})" if s.get("title") else ""
                lines += [f"{s.get('where') or 'Page ' + str(s['page'])}{section}", ""]
                if normalize(fact.text) != normalize(s["quote"]):  # the answer may be the sentence itself
                    lines += [f"> \"{shown_quote(s)}\"", ""]
    return "\n".join(lines)


def save_book(doc, chapters, storage_dir=None):
    """Write the book to config.STORAGE_DIR/books. The same document + topics: the same file."""
    stem = re.sub(r"[^A-Za-z0-9]+", "-", Path(doc).stem).strip("-")
    digest = hashlib.sha256("\n".join(c.topic for c in chapters).encode("utf-8")).hexdigest()[:8]
    path = Path(storage_dir or config.STORAGE_DIR) / "books" / f"{stem}-{digest}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(doc, chapters), encoding="utf-8")
    return path
