"""Answer a question: search -> send top pieces to the AI -> proof check -> show or refuse.

Only an answer that passes the proof check (learnbot.proof) is shown. Anything else is
"Not in this document". If no AI is reachable, the best pieces are shown with an
"AI busy" note, never as an answer.
"""

import json
import re
import time
from dataclasses import dataclass, field

from learnbot import proof
from learnbot.baseline import NOT_FOUND
from learnbot.llm import AI_BUSY, AllProvidersFailed

ANSWERED, REFUSED, AI_BUSY_STATUS = "answered", "not_found", "ai_busy"

PROMPT = """You answer a question using ONLY the numbered pieces of text below, taken from the user's documents.

Rules:
1. Use only the pieces. Do not use your own knowledge.
2. If the pieces do not clearly answer the question, reply {{"found": false}}.
3. Copy numbers, units, lights and signals exactly as written. Never round, convert or spell out numbers.
4. "quote" must be copied word for word from ONE piece: one continuous passage that contains the answer and the conditions named in the question (for example a vessel length). Do not change any word or punctuation inside it.
5. "doc" and "page" must be those of the piece you quote.
6. If the question names a specific set or version of rules, quote only from a piece of that set (the piece title shows it).
7. Keep "answer" short and in simple English. Use only facts that are in your quotes, including every number that answers the question. Do not add rule or section numbers to the answer.
8. If the question compares two things, give one source for each.

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
    sources: list = field(default_factory=list)  # [{doc, page, quote, title}] when answered
    reason: str = ""  # why not answered: no_pieces, llm_not_found, bad_json, proof:<check>, ai_busy
    detail: str = ""
    provider: str = ""
    cached: bool = False
    attempts: str = ""  # e.g. "gemini:m timeout 15.0 s -> groq:m ok 4.2 s"
    seconds: float = 0.0


def attempts_text(attempts):
    return " -> ".join(f"{label} {kind} {seconds:.1f} s" for label, kind, seconds in attempts)


def answer_question(question, searcher, chain):
    """Search, ask the AI, check the proof. Returns an Answer (never raises for AI errors)."""
    start = time.perf_counter()
    pieces = searcher.search(question)

    def done(status, text, **kw):
        return Answer(status, text, pieces, seconds=time.perf_counter() - start, **kw)

    if not pieces:
        return done(REFUSED, NOT_FOUND, reason="no_pieces")
    try:
        text, provider, cached = chain.ask(build_prompt(question, pieces))
    except AllProvidersFailed as failed:
        return done(AI_BUSY_STATUS, AI_BUSY, reason="ai_busy", detail=attempts_text(failed.attempts))
    info = {"provider": provider, "cached": cached, "attempts": attempts_text(getattr(chain, "last_attempts", []))}
    try:
        reply = parse_reply(text)
    except (ValueError, KeyError, TypeError):
        return done(REFUSED, NOT_FOUND, reason="bad_json", **info)
    if not reply["found"]:
        return done(REFUSED, NOT_FOUND, reason="llm_not_found", **info)
    result = proof.check(question, reply, pieces, searcher.library.page_text, searcher.rule_sets)
    if not result.ok:
        return done(REFUSED, NOT_FOUND, reason=f"proof:{result.reason}", detail=result.detail, **info)
    # The source title (rule / section) comes from our piece, not from the AI.
    sources = [{**s, "title": proof.quoted_pieces(s, pieces)[0].title} for s in reply["sources"]]
    return done(ANSWERED, reply["answer"], sources=sources, **info)
