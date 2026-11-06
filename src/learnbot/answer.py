"""Answer a question: search -> send top pieces to the AI -> proof check -> show or refuse.

Only an answer that passes the proof check (learnbot.proof) is shown. Anything else is
"Not in this document". If no AI is reachable, the best pieces are shown with an
"AI busy" note, never as an answer. A question about a rule the document marks
"[Reserved]" is answered by code (learnbot.reserved), without the AI.
"""

import json
import re
import time
from dataclasses import dataclass, field, replace

from learnbot import config, proof
from learnbot.baseline import NOT_FOUND
from learnbot.llm import AI_BUSY, AllProvidersFailed
from learnbot.reserved import RESERVED_ANSWER, reserved_source

ANSWERED, REFUSED, AI_BUSY_STATUS = "answered", "not_found", "ai_busy"
AI_BUSY_SCOPED = "The AI is busy right now. Please try again in a minute."

PROMPT = """You answer a question using ONLY the numbered pieces of text below, taken from the user's documents.

Rules:
1. Use only the pieces. Do not use your own knowledge.
2. If the pieces do not clearly answer the question, reply {{"found": false}}.
3. Copy numbers, units, lights and signals exactly as written. Never round, convert or spell out numbers.
4. "quote" must be copied word for word from ONE piece: one continuous passage that contains the answer and the conditions named in the question (for example a vessel length). Quote only the sentence or list item that answers the question, never a whole list. Do not change any word or punctuation inside it.
5. "doc" and "page" must be those of the piece you quote.
6. If the question names a specific set or version of rules, quote only from a piece of that set (the piece title shows it).
7. Answer only what the question asks. Do not add other facts, sentences or numbers from the pieces, even if they are true. Keep "answer" short and in simple English, and include every number that answers the question.
8. In "answer", write numbers and number words exactly as they are written in your quote (if the quote says "one", write "one"; if it says "4", write "4"). Do not add rule or section numbers to the answer.
9. If a piece shows that a rule or paragraph is "[Reserved]", that is what the document says about it: answer that it is reserved, and quote it.
10. If the question compares two things, give one source for each. Otherwise give exactly one source.
11. The quote must say the answer about the exact thing the question asks. If it says it about something else, even something closely related, reply {{"found": false}}.

Reply with JSON only, in one of these two forms:
{{"found": true, "answer": "...", "sources": [{{"doc": "file.pdf", "page": 12, "quote": "..."}}]}}
{{"found": false}}

Question: {question}

Pieces:
{pieces}
"""


def build_prompt(question, pieces):
    blocks = [f"[{i}] doc: {c.doc} | page: {c.page} | title: {c.title}\n{c.text}"
              for i, c in enumerate(pieces, start=1)]
    return PROMPT.format(question=question.strip(), pieces="\n\n".join(blocks))


def parse_reply(text):
    """The AI's JSON as a dict with found / answer / sources (page as int). Raises ValueError."""
    text = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", text or "")
    data = json.loads(text)
    if not isinstance(data, dict) or not isinstance(data.get("found"), bool):
        raise ValueError("reply has no found: true/false")
    if not data["found"]:
        return {"found": False}
    sources = []
    for s in data.get("sources") or []:
        sources.append({"doc": str(s["doc"]).strip(), "page": int(s["page"]), "quote": str(s["quote"])})
    return {"found": True, "answer": str(data.get("answer") or ""), "sources": sources}


@dataclass
class Answer:
    status: str  # ANSWERED, REFUSED or AI_BUSY_STATUS
    text: str  # the answer, NOT_FOUND, or the AI busy note
    pieces: list  # pieces sent to the AI (shown with the AI busy note)
    sources: list = field(default_factory=list)  # [{doc, page, quote, title, lead?}] when answered
    reason: str = ""  # why not answered: no_pieces, llm_not_found, bad_json, proof:<check>, ai_busy
    detail: str = ""
    provider: str = ""
    cached: bool = False
    attempts: str = ""  # e.g. "gemini:m timeout 15.0 s -> groq:m ok 4.2 s"
    seconds: float = 0.0


def attempts_text(attempts):
    return " -> ".join(f"{label} {kind} {seconds:.1f} s" for label, kind, seconds in attempts)


def answer_within(question, searcher, chain, refusal):
    """answer_question for a limited scope (a notebook, one page), with that scope's refusal.
    The AI busy note has no pieces to offer, because the scope may be very small."""
    ans = answer_question(question, searcher, chain)
    if ans.status == REFUSED:
        return replace(ans, text=refusal)
    if ans.status == AI_BUSY_STATUS:
        return replace(ans, text=AI_BUSY_SCOPED)
    return ans


def answer_question(question, searcher, chain, prompt=None):
    """Search, ask the AI, check the proof. Returns an Answer (never raises for AI errors).
    prompt(question, pieces) -> text; default: the document prompt."""
    start = time.perf_counter()
    pieces = searcher.search(question)

    def done(status, text, **kw):
        return Answer(status, text, pieces, seconds=time.perf_counter() - start, **kw)

    if not pieces:
        return done(REFUSED, NOT_FOUND, reason="no_pieces")
    if not proof.compares(question, searcher.rule_sets):
        reserved = reserved_source(question, pieces, searcher.library.page_text, searcher.rule_sets)
        if reserved:
            return done(ANSWERED, RESERVED_ANSWER, sources=[reserved], provider="code:reserved")
    budget = config.QUESTION_TIME_BUDGET_S - (time.perf_counter() - start)
    try:
        text, provider, cached = chain.ask((prompt or build_prompt)(question, pieces), budget_s=budget)
    except AllProvidersFailed as failed:
        return done(AI_BUSY_STATUS, AI_BUSY, reason="ai_busy", detail=attempts_text(failed.attempts))
    info = {"provider": provider, "cached": cached, "attempts": attempts_text(getattr(chain, "last_attempts", []))}
    try:
        reply = parse_reply(text)
    except (ValueError, KeyError, TypeError):
        return done(REFUSED, NOT_FOUND, reason="bad_json", **info)
    if not reply["found"]:
        return done(REFUSED, NOT_FOUND, reason="llm_not_found", **info)
    reranker = getattr(searcher, "reranker", None)
    topic_score = (lambda q, t: float(reranker.scores(q, [t])[0])) if reranker else None
    result = proof.check(question, reply, pieces, searcher.library.page_text, searcher.rule_sets, topic_score)
    if not result.ok:
        return done(REFUSED, NOT_FOUND, reason=f"proof:{result.reason}", detail=result.detail, **info)
    # The source title (rule / section) comes from our piece, not from the AI. A list quote
    # may have been narrowed to its one answering item (proof.shown_quote shows it).
    sources = [{**s, "title": proof.quoted_pieces(s, pieces)[0].title} for s in result.sources]
    return done(ANSWERED, reply["answer"], sources=sources, **info)
