"""AI chain with fake providers: timeout, fallback, no retry on limits, cache. No network."""

import time

import pytest

from learnbot import llm
from learnbot.llm import (
    AllProvidersFailed, CallLimitReached, LLMChain, LLMDailyLimit, LLMError, LLMRateLimit, LLMTimeout, LLMUnavailable, Provider,
    ReplyCache, classify,
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


def test_two_slow_or_down_failures_in_a_row_skip_main_ai():
    for failure in ["sleep", HttpError(503), HttpError(504)]:
        gemini = Fake("gemini", failure, timeout_s=0.05)
        groq = Fake("groq", "ok")
        chain = LLMChain([gemini, groq])
        for question in ["q1", "q2", "q3", "q4"]:
            assert chain.ask(question)[1] == "groq:fake-model"
        assert gemini.calls == 2 and groq.calls == 4  # q3 and q4 go straight to the fallback
        assert chain.last_attempts[0][:2] == ("gemini:fake-model", "switched_off")


def test_success_resets_the_failure_count():
    class Flaky(Fake):
        def _call(self, prompt):
            self.calls += 1
            if self.calls % 2:  # fails, works, fails, works ...
                raise HttpError(503)
            return "ok"

    gemini, groq = Flaky("gemini", None), Fake("groq", "ok")
    chain = LLMChain([gemini, groq])
    for question in ["q1", "q2", "q3", "q4", "q5", "q6"]:
        chain.ask(question)
    assert gemini.calls == 6 and "gemini:fake-model" not in chain.switched_off


def test_any_error_twice_in_a_row_skips_main_ai():
    # e.g. a bad setting gives HTTP 400 on every call: stop after 2, do not spend 37 calls.
    gemini, groq = Fake("gemini", HttpError(400)), Fake("groq", "ok")
    chain = LLMChain([gemini, groq])
    for question in ["q1", "q2", "q3", "q4"]:
        chain.ask(question)
    assert gemini.calls == 2 and groq.calls == 4
    assert chain.calls == 6


def test_gemini_server_deadline_is_at_least_10_s(monkeypatch):
    seen = {}

    class FakeClient:
        def __init__(self, api_key, http_options):
            seen["timeout_ms"] = http_options.timeout

    monkeypatch.setattr("google.genai.Client", FakeClient)
    provider = llm.GeminiProvider("fake-key", model="m", timeout_s=7)
    assert provider.timeout_s == 7  # our own clock stops waiting after 7 s
    assert seen["timeout_ms"] == 10_000  # Google rejects server deadlines under 10 s


def test_minute_limit_sends_only_this_question_to_the_fallback():
    gemini = Fake("gemini", HttpError(429, "quotaId: GenerateRequestsPerMinutePerProjectPerModel"))
    chain = LLMChain([gemini, Fake("groq", "ok")])
    chain.ask("q1")
    assert "gemini:fake-model" not in chain.switched_off  # tried again on the next question
    chain.ask("q2")
    assert "gemini:fake-model" in chain.switched_off  # 2 in a row -> skipped
    assert gemini.calls == 2


def test_daily_or_unknown_limit_switches_off_at_once():
    assert isinstance(classify(HttpError(429, "GenerateRequestsPerDayPerProjectPerModel")), LLMDailyLimit)
    assert isinstance(classify(HttpError(429, "Rate limit reached on tokens per day (TPD)")), LLMDailyLimit)
    assert isinstance(classify(HttpError(429, "Too many requests")), LLMDailyLimit)
    minute = classify(HttpError(429, "Rate limit reached on tokens per minute (TPM)"))
    assert isinstance(minute, LLMRateLimit) and not isinstance(minute, LLMDailyLimit)


def test_other_error_is_not_retried():
    gemini, groq = Fake("gemini", RuntimeError("server error")), Fake("groq", "ok")
    LLMChain([gemini, groq]).ask("q")
    assert gemini.calls == 1 and groq.calls == 1


def test_all_failed_reports_kinds_without_message_text():
    gemini = Fake("gemini", HttpError(429, "key AIzaSECRET123 over quota"))
    groq = Fake("groq", HttpError(500, "key gsk_SECRET456 broken"))
    with pytest.raises(AllProvidersFailed) as info:
        LLMChain([gemini, groq]).ask("q")
    assert [a[:2] for a in info.value.attempts] == [("gemini:fake-model", "daily_limit"), ("groq:fake-model", "error 500")]
    assert "SECRET" not in str(info.value) and "SECRET" not in repr(info.value.attempts)


def test_classify_errors():
    assert isinstance(classify(HttpError(429)), LLMRateLimit)
    assert isinstance(classify(HttpError(503)), LLMUnavailable)
    assert isinstance(classify(HttpError(504)), LLMUnavailable)

    class RateLimitError(Exception):
        pass

    class APITimeoutError(Exception):
        pass

    assert isinstance(classify(RateLimitError()), LLMRateLimit)
    assert isinstance(classify(APITimeoutError()), LLMTimeout)
    assert type(classify(ValueError("x"))) is LLMError
    assert str(classify(ValueError("secret"))) == ""
    bad = classify(HttpError(400, "Manually set deadline 7s is too short; key AIzaSECRET"))
    assert bad.kind == "error 400" and "SECRET" not in bad.kind + str(bad)


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


def test_main_ai_gets_short_timeout_fallback_longer(monkeypatch):
    class Made:
        def __init__(self, key, timeout_s=None):
            self.timeout_s, self.label = timeout_s, type(self).__name__

    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: None)  # never read the real .env
    monkeypatch.setattr(llm, "GeminiProvider", type("GeminiProvider", (Made,), {}))
    monkeypatch.setattr(llm, "GroqProvider", type("GroqProvider", (Made,), {}))
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    monkeypatch.setenv("GROQ_API_KEY", "fake")
    chain = llm.default_chain(cache=False)
    assert [(p.label, p.timeout_s) for p in chain.providers] == [
        ("GeminiProvider", llm.config.MAIN_LLM_TIMEOUT_S), ("GroqProvider", llm.config.FALLBACK_LLM_TIMEOUT_S)]
    monkeypatch.delenv("GEMINI_API_KEY")
    only_groq = llm.default_chain(cache=False)
    assert only_groq.providers[0].timeout_s == llm.config.MAIN_LLM_TIMEOUT_S  # the only AI is the main AI


def test_default_chain_skips_providers_without_key(monkeypatch):
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: None)  # never read the real .env
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assert llm.default_chain(cache=False).providers == []


# --- Fix 4: one time budget per question, shared by the AIs ---------------------------
def test_fallback_gets_only_the_time_left_in_the_budget(monkeypatch):
    monkeypatch.setattr(llm.config, "MIN_AI_TIME_S", 0.05)
    slow = Fake("gemini", "sleep", timeout_s=0.2)
    slow_too = Fake("groq", "sleep", timeout_s=15)
    chain = LLMChain([slow, slow_too])
    start = time.perf_counter()
    with pytest.raises(AllProvidersFailed):
        chain.ask("q", budget_s=0.35)
    # 0.2 s main + at most the 0.15 s left for the fallback, not the fallback's own 15 s.
    assert time.perf_counter() - start < 0.45
    assert [kind for _, kind, _ in chain.last_attempts] == ["timeout", "timeout"]


def test_fallback_is_skipped_when_too_little_time_is_left(monkeypatch):
    monkeypatch.setattr(llm.config, "MIN_AI_TIME_S", 0.5)
    slow, groq = Fake("gemini", "sleep", timeout_s=0.2), Fake("groq", '{"found": false}')
    chain = LLMChain([slow, groq])
    with pytest.raises(AllProvidersFailed) as failed:
        chain.ask("q", budget_s=0.6)
    assert failed.value.attempts[1][:2] == ("groq:fake-model", "no_time_left") and groq.calls == 0


def test_no_budget_keeps_each_providers_timeout():
    slow, groq = Fake("gemini", "sleep", timeout_s=0.05), Fake("groq", '{"found": false}')
    assert LLMChain([slow, groq]).ask("q")[1] == "groq:fake-model"


# --- A switched-off AI is tried again every RETRY_SWITCHED_OFF_EVERY questions -----------
def test_switched_off_main_ai_is_tried_again_every_5_questions_and_used_again():
    class Recovers(Fake):
        def _call(self, prompt):
            self.calls += 1
            if self.calls <= 2:
                raise HttpError(504)  # 2 failures in a row -> switched off
            return "gemini answer"

    gemini, groq = Recovers("gemini", None), Fake("groq", "groq answer")
    chain = LLMChain([gemini, groq])
    used = [chain.ask(f"q{i}")[1] for i in range(1, 9)]
    # q1, q2 fail (switched off); q3-q6 skipped; q7 = 5th question since: tried, answers, used again.
    assert used == ["groq:fake-model"] * 6 + ["gemini:fake-model"] * 2
    assert gemini.calls == 4 and "gemini:fake-model" not in chain.switched_off


def test_switched_off_ai_that_still_fails_stays_off():
    gemini, groq = Fake("gemini", HttpError(503)), Fake("groq", "ok")
    chain = LLMChain([gemini, groq])
    for i in range(12):
        chain.ask(f"q{i}")
    assert gemini.calls == 2 + 2  # 2 failures, then one retry at the 5th and 10th question
    assert "gemini:fake-model" in chain.switched_off


def test_daily_limit_is_never_tried_again():
    gemini, groq = Fake("gemini", HttpError(429, "quota per day exceeded")), Fake("groq", "ok")
    chain = LLMChain([gemini, groq])
    for i in range(12):
        chain.ask(f"q{i}")
    assert gemini.calls == 1


# --- Eval warm-up: one tiny call to the main AI before a run ---------------------------
def load_eval_script():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "scripts" / "run_answer_eval.py"
    spec = importlib.util.spec_from_file_location("run_answer_eval", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_warm_up_reports_ok_or_the_error_kind():
    script = load_eval_script()
    chain = LLMChain([Fake("gemini", '{"ok": true}'), Fake("groq", "ok")])
    ok, status = script.warm_up(chain)
    assert ok and status.startswith("gemini:fake-model ok") and chain.calls == 1
    chain = LLMChain([Fake("gemini", HttpError(504)), Fake("groq", "ok")])
    ok, status = script.warm_up(chain)
    assert not ok and status.startswith("gemini:fake-model unavailable")


def test_failed_warm_up_starts_the_run_with_main_ai_switched_off():
    # Real case (3 Nov 2026): Gemini failed the warm-up twice, so no hold-out question was
    # asked. Now the run starts as after 2 failures: fallback answers, main retried every 5.
    script = load_eval_script()
    gemini, groq = Fake("gemini", HttpError(503)), Fake("groq", "answer")
    chain = LLMChain([gemini, groq])
    assert script.warm_up(chain)[0] is False and gemini.calls == 1
    for i in range(4):
        assert chain.ask(f"q{i}")[1] == "groq:fake-model"
    assert gemini.calls == 1  # skipped on questions 1-4
    gemini.behaviour = "answer"
    assert chain.ask("q4")[1] == "gemini:fake-model"  # question 5: tried again, used again
    assert chain.ask("q5")[1] == "gemini:fake-model"


def test_warm_up_daily_limit_is_never_tried_again():
    script = load_eval_script()
    gemini, groq = Fake("gemini", HttpError(429, "quota exceeded")), Fake("groq", "answer")
    chain = LLMChain([gemini, groq])
    assert script.warm_up(chain)[0] is False
    for i in range(10):
        chain.ask(f"q{i}")
    assert gemini.calls == 1


# --- Call limit: checked before EVERY real call (warm-up, main AI, fallback) -----------
def test_call_limit_is_checked_before_every_call():
    # Real case (3 Nov 2026): limit 4, warm-up + 2 questions x (Gemini timeout + Groq)
    # made 5 calls, because the limit was only checked before each question.
    script = load_eval_script()
    gemini, groq = Fake("gemini", '{"ok": true}'), Fake("groq", "answer")
    chain = LLMChain([gemini, groq], max_calls=4)
    assert script.warm_up(chain)[0] is True  # call 1
    gemini.behaviour = HttpError(503)
    assert chain.ask("q1")[0] == "answer"  # calls 2 (gemini fails) and 3 (groq)
    with pytest.raises(CallLimitReached):
        chain.ask("q2")  # call 4 = gemini (fails), then groq would be call 5: stopped
    assert chain.calls == 4 and gemini.calls == 3 and groq.calls == 1


def test_call_limit_stops_the_warm_up_too():
    script = load_eval_script()
    gemini = Fake("gemini", '{"ok": true}')
    chain = LLMChain([gemini], max_calls=0)
    with pytest.raises(CallLimitReached):
        script.warm_up(chain)
    assert gemini.calls == 0 and chain.calls == 0


def test_no_call_limit_and_cached_replies_never_count(tmp_path):
    gemini = Fake("gemini", "answer")
    chain = LLMChain([gemini])  # the app: no limit
    for i in range(10):
        chain.ask(f"q{i}")
    assert chain.calls == 10
    cached = LLMChain([gemini], ReplyCache(tmp_path), max_calls=1)
    cached.ask("p")
    assert cached.ask("p")[2] is True and cached.calls == 1  # a cache hit is not a call


def test_fresh_run_asks_again_but_still_saves(tmp_path):
    cache = ReplyCache(tmp_path)
    gemini = Fake("gemini", "answer")
    LLMChain([gemini], cache).ask("p")
    fresh = LLMChain([gemini], cache, read_cache=False)
    assert not fresh.is_cached("p") and fresh.ask("p")[2] is False and gemini.calls == 2
    assert LLMChain([gemini], cache).is_cached("p")
