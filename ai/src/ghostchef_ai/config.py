"""Configuration: fake mode, model IDs, fixture location. Read from the environment each call."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load ai/.env or ./.env if present, never overriding variables already set.
load_dotenv(override=False)

# Gemini: PLACEHOLDERS, not verified against our key. Taken from the public models page on
# 2026-11-13 (docs/EVENT-CONTEXT.md §5). AI-02 verifies the real choice in ai/STATUS.md.
_GEMINI_MODELS = {
    "video": "gemini-3.8-flash",
    "check": "gemini-3.8-flash",
    "watch": "gemini-3.5-flash-lite",
    "live": "gemini-3.8-live",
}
# OpenAI: TEMPORARY development stand-in while Gemini access is pending (ai/STATUS.md).
# Only check/watch can run on it; video and live are Gemini-only. Chosen by the AI-02 smoke
# test on 2026-11-14 (ai/STATUS.md); overridable with GHOSTCHEF_MODEL_*.
_OPENAI_MODELS = {
    "video": "unsupported-on-openai",
    "check": "gpt-5.4-mini",
    "watch": "gpt-5.4-nano",
    "live": "unsupported-on-openai",
}
_PROVIDERS = {"gemini": _GEMINI_MODELS, "openai": _OPENAI_MODELS}
# Per-process cap on paid model calls. Protects the small OpenAI credit; 0 = unlimited.
_DEFAULT_MAX_CALLS = {"gemini": 0, "openai": 300}
_ENV_KEYS = {
    "video": "GHOSTCHEF_MODEL_VIDEO",
    "check": "GHOSTCHEF_MODEL_CHECK",
    "watch": "GHOSTCHEF_MODEL_WATCH",
    "live": "GHOSTCHEF_MODEL_LIVE",
}
_TRUE = {"1", "true", "yes"}


def is_fake() -> bool:
    return os.environ.get("GHOSTCHEF_AI_FAKE", "").strip().lower() in _TRUE


def provider() -> str:
    """'gemini' (the product) or 'openai' (temporary dev stand-in). GHOSTCHEF_PROVIDER."""
    p = os.environ.get("GHOSTCHEF_PROVIDER", "gemini").strip().lower()
    if p not in _PROVIDERS:
        raise ValueError(f"GHOSTCHEF_PROVIDER must be one of {sorted(_PROVIDERS)}, got {p!r}")
    return p


def model_ids() -> dict[str, str]:
    if is_fake():
        return dict.fromkeys(_GEMINI_MODELS, "fake")
    defaults = _PROVIDERS[provider()]
    return {k: os.environ.get(_ENV_KEYS[k]) or v for k, v in defaults.items()}


def max_calls() -> int:
    """GHOSTCHEF_MAX_CALLS, else the provider default (OpenAI 300, Gemini unlimited)."""
    raw = os.environ.get("GHOSTCHEF_MAX_CALLS")
    if raw:
        return max(0, int(raw))
    return _DEFAULT_MAX_CALLS[provider()]


def fixture_dir() -> Path:
    override = os.environ.get("GHOSTCHEF_FIXTURE_DIR")
    if override:
        return Path(override).expanduser().resolve()
    # src/ghostchef_ai/config.py -> ai/fixtures (works for editable installs)
    return (Path(__file__).resolve().parents[2] / "fixtures").resolve()


def fake_delay_s() -> float:
    try:
        return max(0.0, float(os.environ.get("GHOSTCHEF_AI_FAKE_DELAY", "0.3")))
    except ValueError:
        return 0.3
