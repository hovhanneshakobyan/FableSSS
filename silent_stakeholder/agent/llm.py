"""Provider selection. Free tiers only — this project has no LLM budget left.

Auto-detects from the environment, first match wins:

    GROQ_API_KEY            -> Groq        console.groq.com/keys
    GOOGLE_API_KEY          -> Gemini      aistudio.google.com/apikey
    (ollama on :11434)      -> Ollama      brew install ollama

Override either half explicitly:

    SS_PROVIDER=groq|gemini|ollama
    SS_MODEL=<model id>

Model ids move faster than this file does. If a default 404s, set SS_MODEL
rather than editing here — the provider's own model list is the source of truth.
"""
from __future__ import annotations
import os
import urllib.error
import urllib.request

# Chosen for tool-calling reliability, which is the failure mode that matters
# in a ReAct loop — a fluent model that mangles arguments is useless here.
DEFAULTS = {
    "groq": "llama-3.3-70b-versatile",
    # Google retires models for NEW keys while still listing them: a fresh key
    # gets 404 "no longer available to new users" on gemini-2.5-flash, and a
    # misleading 429 "limit: 0" on gemini-2.0-flash. Verified working 2026-07-31.
    "gemini": "gemini-3.6-flash",
    "ollama": "qwen2.5:7b",
}

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")


def _ollama_up() -> bool:
    try:
        urllib.request.urlopen(f"{OLLAMA_HOST}/api/tags", timeout=1.5)
        return True
    except (urllib.error.URLError, OSError):
        return False


def detect_provider() -> str | None:
    if p := os.environ.get("SS_PROVIDER"):
        return p.strip().lower()
    if os.environ.get("GROQ_API_KEY"):
        return "groq"
    if os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY"):
        return "gemini"
    if _ollama_up():
        return "ollama"
    return None


SETUP_HELP = """No LLM provider found. Pick one (all free), then re-run:

  Groq    — fastest, solid tool calling
      open https://console.groq.com/keys
      export GROQ_API_KEY=gsk_...

  Gemini  — big context, generous free tier
      open https://aistudio.google.com/apikey
      export GOOGLE_API_KEY=...

  Ollama  — fully offline, no key, no rate limit (weaker at multi-hop)
      brew install ollama && ollama serve
      ollama pull qwen2.5:7b

Then optionally:  export SS_MODEL=<model id>"""


def init_llm(provider: str | None = None, model: str | None = None):
    """Return a chat model with tool calling. Raises SystemExit with help text."""
    provider = provider or detect_provider()
    if provider is None:
        raise SystemExit(SETUP_HELP)
    model = model or os.environ.get("SS_MODEL") or DEFAULTS.get(provider)

    # temperature=0: this agent reports evidence, it does not brainstorm prose.
    # max_retries: free tiers rate-limit per MINUTE as well as per day, and a
    # ReAct run is a burst of calls. Backing off through a per-minute 429 saves
    # the run; a per-day cap will still fail, which is what RATE_HELP explains.
    if provider == "groq":
        from langchain_groq import ChatGroq
        return ChatGroq(model=model, temperature=0, max_retries=4)
    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        key = os.environ.get("GOOGLE_API_KEY") or os.environ["GEMINI_API_KEY"]
        # Newer Gemini models reject `temperature` outright (fixed sampling).
        return ChatGoogleGenerativeAI(model=model, google_api_key=key, max_retries=4)
    if provider == "ollama":
        from langchain_ollama import ChatOllama
        return ChatOllama(model=model, temperature=0, base_url=OLLAMA_HOST)
    raise SystemExit(f"unknown SS_PROVIDER={provider!r} (groq|gemini|ollama)")


RATE_HELP = """Rate limit hit. Measured on free tiers, 2026-07-31:
  groq   llama-3.3-70b-versatile   12k tokens/min, 100k tokens/day (~12 runs)
  gemini gemini-3.6-flash          20 requests/DAY (~2 runs) — burns out fast

A per-minute limit retries itself; a per-day cap does not. Options:
  SS_PROVIDER=groq                 switch provider (both keys can coexist)
  SS_MODEL=llama-3.1-8b-instant    another model = another quota bucket
  SS_MODEL=gemini-3.5-flash-lite   lite tiers usually allow more requests
  SS_PROVIDER=ollama               no quota at all, if you install it"""


def describe_provider() -> str:
    p = detect_provider()
    if p is None:
        return "none"
    return f"{p}/{os.environ.get('SS_MODEL') or DEFAULTS.get(p, '?')}"
