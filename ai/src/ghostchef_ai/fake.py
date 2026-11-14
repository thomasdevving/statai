"""Deterministic fake implementations (GHOSTCHEF_AI_FAKE=1). No network, no key.

The sequences are part of the contract other tracks test against (ai/tasks/01, AI-01.4):
- check_frame: frame < 5000 bytes -> unsure. Otherwise, per step: odd calls -> fix with the
  step's first watch-for, even calls -> pass. Steps without watch-fors always pass.
- watch_frame: per step, calls 1-3 ok, 4-6 warn with the first watch-for, then repeat.
"""

from __future__ import annotations

import asyncio
import json
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

from ghostchef_ai.config import fake_delay_s, fixture_dir
from ghostchef_ai.schemas import (
    CheckResult,
    LiveConfig,
    LiveToken,
    RecipeDraft,
    StepSpec,
    WatchResult,
)

MODEL = "fake"
UNJUDGEABLE_BYTES = 5000

_check_calls: Counter[tuple[int, str]] = Counter()
_watch_calls: Counter[tuple[int, str]] = Counter()


def reset() -> None:
    """Clear the per-step call counters (tests, backend test fixtures)."""
    _check_calls.clear()
    _watch_calls.clear()


def _key(step: StepSpec) -> tuple[int, str]:
    return (step.idx, step.title)


async def _sleep(factor: float) -> None:
    d = fake_delay_s() * factor
    if d > 0:
        await asyncio.sleep(d)


def load_fixture() -> RecipeDraft:
    path = fixture_dir() / "sushi_recipe.json"
    return RecipeDraft.model_validate(json.loads(path.read_text(encoding="utf-8")))


async def extract_recipe(
    video_path: Path, *, title_hint: str | None = None, step_marks_s: list[float] | None = None
) -> RecipeDraft:
    await _sleep(4)
    draft = load_fixture()
    if title_hint:
        draft = draft.model_copy(update={"title": title_hint})
    return draft


async def check_frame(
    frame_jpeg: bytes, step: StepSpec, ref_image_jpeg: bytes | None, *, timeout_s: float = 8.0
) -> CheckResult:
    await _sleep(2.5)
    if len(frame_jpeg) < UNJUDGEABLE_BYTES:
        return CheckResult(
            verdict="unsure",
            mistake_id=None,
            headline="Can't tell",
            fix="Look straight down at board",
            spoken="I can't see the board clearly. Look straight down at it and check again.",
            confidence=0.3,
            model=MODEL,
        )
    _check_calls[_key(step)] += 1
    n = _check_calls[_key(step)]
    if step.watch_fors and n % 2 == 1:
        w = step.watch_fors[0]
        return CheckResult(
            verdict="fix", mistake_id=w.id, headline=w.headline, fix=w.fix,
            spoken=w.spoken, confidence=0.9, model=MODEL,
        )
    return CheckResult(
        verdict="pass", mistake_id=None, headline="Looks right", fix="",
        spoken="That looks right.", confidence=0.9, model=MODEL,
    )


async def watch_frame(frame_jpeg: bytes, step: StepSpec, *, timeout_s: float = 3.5) -> WatchResult:
    await _sleep(1)
    _watch_calls[_key(step)] += 1
    n = _watch_calls[_key(step)]
    if step.watch_fors and ((n - 1) % 6) >= 3:
        w = step.watch_fors[0]
        return WatchResult(
            status="warn", mistake_id=w.id, headline=w.headline, fix=w.fix,
            spoken=w.spoken, confidence=0.9, model=MODEL,
        )
    return WatchResult(
        status="ok", mistake_id=None, headline="", fix="", spoken="", confidence=0.9, model=MODEL
    )


async def mint_live_token(live_config: LiveConfig) -> LiveToken:
    now = datetime.now(tz=UTC)
    return LiveToken(
        token="fake-token",
        expires_at=now + timedelta(minutes=30),
        new_session_expires_at=now + timedelta(minutes=1),
        locked=False,
    )
