"""AI chain with fake providers: timeout, fallback, no retry on limits, cache. No network."""

import time

import pytest

from learnbot import llm
from learnbot.llm import (
    AllProvidersFailed, LLMChain, LLMError, LLMRateLimit, LLMTimeout, Provider, ReplyCache, classify,
)


class Fake(Provider):
    def __init__(self, name, behaviour, timeout_s=1):
        super().__init__("fake-model", timeout_s)
        self.name = name
        self.behaviour = behaviour  # a reply string, an exception, or "sleep"
        self.calls = 0

    def _call(self, prompt):
        self.calls += 1
        if self.behaviour == "sleep":
            time.sleep(0.5)
            return "too late"
        if isinstance(self.behaviour, Exception):
            raise self.behaviour
        return self.behaviour


class HttpError(Exception):
    def __init__(self, code, message=""):
        super().__init__(message)
        self.code = code


def test_timeout_falls_back_to_second_provider():
    slow, groq = Fake("gemini", "sleep", timeout_s=0.05), Fake("groq", '{"found": false}')
    chain = LLMChain([slow, groq])
    reply, provider, cached = chain.ask("q")
    assert reply == '{"found": false}' and provider == "groq:fake-model" and not cached
    assert [a[:2] for a in chain.last_attempts] == [("gemini:fake-model", "timeout"), ("groq:fake-model", "ok")]
    assert chain.last_attempts[0][2] < 0.4  # gave up at the timeout, did not wait for the reply


def test_daily_limit_is_not_retried_and_switches_provider_off():
    gemini, groq = Fake("gemini", HttpError(429, "quota per day")), Fake("groq", "ok")
    chain = LLMChain([gemini, groq])
    assert chain.ask("q1")[1] == "groq:fake-model"
    assert chain.ask("q2")[1] == "groq:fake-model"
    assert gemini.calls == 1  # never retried, not asked again after the limit
    assert chain.calls == 3


def test_other_error_is_not_retried():
    gemini, groq = Fake("gemini", RuntimeError("server error")), Fake("groq", "ok")
    LLMChain([gemini, groq]).ask("q")
    assert gemini.calls == 1 and groq.calls == 1


def test_all_failed_reports_kinds_without_message_text():
    gemini = Fake("gemini", HttpError(429, "key AIzaSECRET123 over quota"))
    groq = Fake("groq", HttpError(500, "key gsk_SECRET456 broken"))
    with pytest.raises(AllProvidersFailed) as info:
        LLMChain([gemini, groq]).ask("q")
    assert [a[:2] for a in info.value.attempts] == [("gemini:fake-model", "rate_limit"), ("groq:fake-model", "error")]
    assert "SECRET" not in str(info.value) and "SECRET" not in repr(info.value.attempts)


def test_classify_errors():
    assert isinstance(classify(HttpError(429)), LLMRateLimit)

    class RateLimitError(Exception):
        pass

    class APITimeoutError(Exception):
        pass

    assert isinstance(classify(RateLimitError()), LLMRateLimit)
    assert isinstance(classify(APITimeoutError()), LLMTimeout)
    assert type(classify(ValueError("x"))) is LLMError
    assert str(classify(ValueError("secret"))) == ""


def test_cache_saves_quota(tmp_path):
    gemini = Fake("gemini", "answer")
    chain = LLMChain([gemini], ReplyCache(tmp_path))
    assert chain.ask("same prompt") == ("answer", "gemini:fake-model", False)
    assert chain.ask("same prompt") == ("answer", "gemini:fake-model", True)
    assert chain.is_cached("same prompt") and not chain.is_cached("other prompt")
    assert gemini.calls == 1 and chain.calls == 1


def test_failed_calls_are_not_cached(tmp_path):
    chain = LLMChain([Fake("gemini", RuntimeError())], ReplyCache(tmp_path))
    with pytest.raises(AllProvidersFailed):
        chain.ask("p")
    assert not chain.is_cached("p")


def test_default_chain_skips_providers_without_key(monkeypatch):
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: None)  # never read the real .env
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assert llm.default_chain(cache=False).providers == []
