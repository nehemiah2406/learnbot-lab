"""AI calls: Gemini (main) and Groq (fallback), with timeouts, no retries and a cache.

- Every call has a timeout (main AI config.MAIN_LLM_TIMEOUT_S, fallback
  config.FALLBACK_LLM_TIMEOUT_S), set in the SDK and checked again here.
- The AIs of one question share a time budget (ask(..., budget_s=...)): a fallback only
  gets the time that is left, and is skipped if less than config.MIN_AI_TIME_S is left.
- Nothing is retried. A daily limit (HTTP 429, or a 429 that does not say "per minute")
  switches that provider off for the rest of the run, so quota is never spent on it.
  config.MAX_FAILURES_IN_A_ROW failures in a row of any other kind (timeout, 503, 504,
  per-minute limit, or e.g. a 400 from a bad setting) switch it off too, but only for a
  while: every config.RETRY_SWITCHED_OFF_EVERY questions it is tried once more, and if
  it answers it is used again. One failure only sends that question to the fallback.
- If every provider fails, the caller shows a friendly "AI busy" note instead.
- Error messages never contain keys: only the error kind (and HTTP status) is kept.
- An optional call limit (LLMChain.max_calls, used by the eval scripts) is checked
  before EVERY real call; when it is reached, CallLimitReached stops the run.
- Replies are cached in config.CACHE_DIR by prompt + model names, so the same question
  with the same pieces never spends quota twice.
"""

import concurrent.futures
import hashlib
import json
import os
import re
import time
from pathlib import Path

from learnbot import config

AI_BUSY = "The AI is busy right now. Here are the best matching pieces from your document instead."
GEMINI_MIN_DEADLINE_S = 10  # "Minimum allowed deadline is 10s" (Gemini API, HTTP 400)


class LLMError(Exception):
    kind = "error"


class LLMTimeout(LLMError):
    kind = "timeout"


class LLMRateLimit(LLMError):
    kind = "rate_limit"


class LLMDailyLimit(LLMRateLimit):
    kind = "daily_limit"


class LLMUnavailable(LLMError):
    kind = "unavailable"  # HTTP 503 (overloaded) or 504 (deadline exceeded)


# Words in a 429 message that mean a daily limit (the message itself is never kept).
DAILY_LIMIT = re.compile(r"per ?day|\bRPD\b|\bTPD\b", re.IGNORECASE)
MINUTE_LIMIT = re.compile(r"per ?minute|\bRPM\b|\bTPM\b", re.IGNORECASE)


class CallLimitReached(Exception):
    """The chain's max_calls is used up: no further real call is made (stops an eval run)."""

    def __init__(self, limit):
        super().__init__(f"AI call limit reached ({limit} calls)")
        self.limit = limit


class AllProvidersFailed(Exception):
    def __init__(self, attempts):
        super().__init__("all AI providers failed")
        self.attempts = attempts  # [(provider label, error kind, seconds)]


# Room for calls that timed out on our clock but still run in the background, so a new
# call never waits in the queue.
_executor = concurrent.futures.ThreadPoolExecutor(max_workers=8)


def with_timeout(fn, timeout_s):
    """Run fn() and give up after timeout_s seconds (extra guard on top of the SDK timeout)."""
    future = _executor.submit(fn)
    try:
        return future.result(timeout=timeout_s)
    except concurrent.futures.TimeoutError as exc:
        raise LLMTimeout() from exc


def classify(exc):
    """Map any SDK error to LLMTimeout / LLMRateLimit / LLMError (no message text kept)."""
    if isinstance(exc, LLMError):
        return exc
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    names = [cls.__name__ for cls in type(exc).__mro__]
    if status == 429 or "RateLimitError" in names:
        # A per-minute limit passes soon; anything else (daily or unknown) is a daily limit,
        # so quota is never spent on it again in this run.
        message = str(exc)
        if MINUTE_LIMIT.search(message) and not DAILY_LIMIT.search(message):
            return LLMRateLimit()
        return LLMDailyLimit()
    if any("Timeout" in name for name in names):
        return LLMTimeout()
    if status in (503, 504):
        return LLMUnavailable()
    err = LLMError()
    if isinstance(status, int):
        err.kind = f"error {status}"  # e.g. "error 400": the HTTP status only, no message
    return err


class Provider:
    """One AI model. Subclasses implement _call(prompt) -> reply text."""

    name = "provider"

    def __init__(self, model, timeout_s=None):
        self.model = model
        self.timeout_s = timeout_s or config.FALLBACK_LLM_TIMEOUT_S

    @property
    def label(self):
        return f"{self.name}:{self.model}"

    def ask(self, prompt, timeout_s=None):
        try:
            return with_timeout(lambda: self._call(prompt), timeout_s or self.timeout_s)
        except Exception as exc:  # noqa: BLE001 - every failure becomes a key-free LLMError
            raise classify(exc) from None

    def _call(self, prompt):
        raise NotImplementedError


class GeminiProvider(Provider):
    name = "gemini"

    def __init__(self, api_key, model=None, timeout_s=None):
        super().__init__(model or os.getenv("GEMINI_MODEL") or config.GEMINI_MODEL, timeout_s)
        from google import genai
        from google.genai import types

        self._types = types
        # The SDK sends its timeout to Google as a server deadline, and Google rejects
        # deadlines under 10 s (HTTP 400). Our own clock in Provider.ask() still stops
        # waiting after self.timeout_s.
        server_deadline_s = max(self.timeout_s, GEMINI_MIN_DEADLINE_S)
        self._client = genai.Client(api_key=api_key, http_options=types.HttpOptions(
            timeout=int(server_deadline_s * 1000), retry_options=types.HttpRetryOptions(attempts=1)))

    def _call(self, prompt):
        reply = self._client.models.generate_content(
            model=self.model, contents=prompt,
            config=self._types.GenerateContentConfig(response_mime_type="application/json"))
        return reply.text or ""


class GroqProvider(Provider):
    name = "groq"

    def __init__(self, api_key, model=None, timeout_s=None):
        super().__init__(model or os.getenv("GROQ_MODEL") or config.GROQ_MODEL, timeout_s)
        from groq import Groq

        self._client = Groq(api_key=api_key, timeout=self.timeout_s, max_retries=0)

    def _call(self, prompt):
        reply = self._client.chat.completions.create(
            model=self.model, temperature=0, response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt}])
        return reply.choices[0].message.content or ""


class ReplyCache:
    """AI replies saved as JSON files, one per (models, prompt)."""

    def __init__(self, cache_dir=None):
        self.dir = Path(cache_dir or config.CACHE_DIR) / "llm"

    @staticmethod
    def key(labels, prompt):
        data = json.dumps({"v": config.PROMPT_VERSION, "models": labels, "prompt": prompt})
        return hashlib.sha256(data.encode("utf-8")).hexdigest()

    def get(self, key):
        path = self.dir / f"{key}.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None

    def put(self, key, record):
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / f"{key}.json").write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")


class LLMChain:
    """Ask providers in order; first success wins. Counts real (not cached) calls."""

    def __init__(self, providers, cache=None, read_cache=True, max_calls=None):
        self.providers = list(providers)
        self.max_calls = max_calls  # None = no limit (the app); checked before every call
        self.cache = cache
        self.read_cache = read_cache  # False: ask again, but still save the new replies
        self.switched_off = set()  # providers skipped (daily limit: for the rest of the run)
        self.daily_limit = set()  # switched off for good: never tried again in this run
        self.failures_in_a_row = {}  # provider label -> failures since its last success
        self.questions_off = {}  # provider label -> questions skipped since it was last tried
        self.calls = 0
        self.last_attempts = []  # [(provider label, "ok" or error kind, seconds)] of the last ask()

    def count_call(self):
        """Count one real call, or raise CallLimitReached if max_calls is used up."""
        if self.max_calls is not None and self.calls >= self.max_calls:
            raise CallLimitReached(self.max_calls)
        self.calls += 1

    def cache_key(self, prompt):
        return ReplyCache.key([p.label for p in self.providers], prompt)

    def is_cached(self, prompt):
        return self.cache is not None and self.read_cache and self.cache.get(self.cache_key(prompt)) is not None

    def ask(self, prompt, budget_s=None):
        """(reply text, provider label, from cache?) or raises AllProvidersFailed.
        budget_s: seconds all providers together may use for this prompt (None = no limit)."""
        key = self.cache_key(prompt)
        deadline = None if budget_s is None else time.perf_counter() + budget_s
        attempts = self.last_attempts = []
        if self.cache is not None and self.read_cache:
            hit = self.cache.get(key)
            if hit is not None:
                return hit["reply"], hit["provider"], True
        for p in self.providers:
            if p.label in self.switched_off:
                waited = self.questions_off.get(p.label, 0) + 1
                if p.label in self.daily_limit or waited < config.RETRY_SWITCHED_OFF_EVERY:
                    self.questions_off[p.label] = waited
                    attempts.append((p.label, "switched_off", 0.0))
                    continue
                self.questions_off[p.label] = 0  # try it once more on this question
            timeout = p.timeout_s
            if deadline is not None:
                left = deadline - time.perf_counter()
                if left < config.MIN_AI_TIME_S:
                    attempts.append((p.label, "no_time_left", 0.0))
                    continue
                timeout = min(timeout, left)
            self.count_call()
            start = time.perf_counter()
            try:
                reply = p.ask(prompt, timeout)
            except LLMError as err:
                attempts.append((p.label, err.kind, time.perf_counter() - start))
                if isinstance(err, LLMDailyLimit):
                    self.switched_off.add(p.label)
                    self.daily_limit.add(p.label)
                else:  # timeout, 503/504, per-minute limit, or any other error (e.g. a bad setting)
                    self.failures_in_a_row[p.label] = self.failures_in_a_row.get(p.label, 0) + 1
                    if self.failures_in_a_row[p.label] >= config.MAX_FAILURES_IN_A_ROW:
                        self.switched_off.add(p.label)
                continue
            self.failures_in_a_row[p.label] = 0
            self.switched_off.discard(p.label)  # answered again: use it again
            attempts.append((p.label, "ok", time.perf_counter() - start))
            if self.cache is not None:
                self.cache.put(key, {"provider": p.label, "reply": reply})
            return reply, p.label, False
        raise AllProvidersFailed(attempts)


def default_chain(cache=True):
    """Gemini then Groq, keys from .env (never printed). Providers without a key are skipped."""
    from dotenv import load_dotenv

    load_dotenv()
    makers = [(GeminiProvider, "GEMINI_API_KEY"), (GroqProvider, "GROQ_API_KEY")]
    providers = []
    for maker, env in makers:
        if os.getenv(env):
            # The first (main) AI gets the short timeout, every fallback the longer one.
            timeout = config.FALLBACK_LLM_TIMEOUT_S if providers else config.MAIN_LLM_TIMEOUT_S
            providers.append(maker(os.getenv(env), timeout_s=timeout))
    return LLMChain(providers, ReplyCache() if cache else None)
