"""Configuration: fake mode, model IDs, fixture location. Read from the environment each call."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load ai/.env or ./.env if present, never overriding variables already set.
load_dotenv(override=False)

# PLACEHOLDERS, not verified against our key. Taken from the public models page on 2026-11-13
# (docs/EVENT-CONTEXT.md §5). AI-02 verifies the real choice and records it in ai/STATUS.md.
_DEFAULT_MODELS = {
    "video": "gemini-3.8-flash",
    "check": "gemini-3.8-flash",
    "watch": "gemini-3.5-flash-lite",
    "live": "gemini-3.8-live",
}
_ENV_KEYS = {
    "video": "GHOSTCHEF_MODEL_VIDEO",
    "check": "GHOSTCHEF_MODEL_CHECK",
    "watch": "GHOSTCHEF_MODEL_WATCH",
    "live": "GHOSTCHEF_MODEL_LIVE",
}
_TRUE = {"1", "true", "yes"}


def is_fake() -> bool:
    return os.environ.get("GHOSTCHEF_AI_FAKE", "").strip().lower() in _TRUE


def model_ids() -> dict[str, str]:
    if is_fake():
        return dict.fromkeys(_DEFAULT_MODELS, "fake")
    return {k: os.environ.get(_ENV_KEYS[k]) or v for k, v in _DEFAULT_MODELS.items()}


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
