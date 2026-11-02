"""List the Gemini and Groq models your keys can use (names only, no generation).

Run:  .venv\\Scripts\\python scripts\\list_models.py
Keys are read from .env and never printed: only "set" / "not set" is shown.
"""

import os
import sys

from dotenv import load_dotenv

TIMEOUT_S = 15


def error_text(exc):
    """Short, key-free description of an error (type and HTTP status only)."""
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    return f"{type(exc).__name__}" + (f" (HTTP {status})" if status else "")


def gemini_models(key):
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=TIMEOUT_S * 1000))
    names = []
    for m in client.models.list():
        if "generateContent" in (m.supported_actions or []):
            names.append(m.name.removeprefix("models/"))
    return sorted(names)


def groq_models(key):
    from groq import Groq

    client = Groq(api_key=key, timeout=TIMEOUT_S, max_retries=0)
    return sorted(m.id for m in client.models.list().data)


def main():
    sys.stdout.reconfigure(errors="replace")
    load_dotenv()
    for label, env, lister in [("Gemini", "GEMINI_API_KEY", gemini_models), ("Groq", "GROQ_API_KEY", groq_models)]:
        key = os.getenv(env)
        print(f"{env}: {'set' if key else 'not set'}")
        if not key:
            continue
        try:
            names = lister(key)
        except Exception as exc:  # noqa: BLE001 - show a friendly, key-free message
            print(f"  {label}: could not list models: {error_text(exc)}")
            continue
        print(f"  {label}: {len(names)} models")
        for name in names:
            print(f"    {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
