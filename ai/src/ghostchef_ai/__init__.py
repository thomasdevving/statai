"""ghostchef_ai — the complete public surface (docs/API-CONTRACT.md §7).

Every async function dispatches per call: fake mode (GHOSTCHEF_AI_FAKE=1) -> ghostchef_ai.fake,
otherwise the real implementation: check.check_frame and watch.watch_frame (AI-04),
live.mint_live_token (AI-05), ingest.extract_recipe (AI-06).
"""

from __future__ import annotations

from pathlib import Path

from ghostchef_ai import check, fake, ingest, watch
from ghostchef_ai.config import is_fake, model_ids
from ghostchef_ai.errors import AIError, AIInvalidOutput, AIQuotaError, AITimeout, AIUnavailable
from ghostchef_ai.live import build_live_config
from ghostchef_ai.live import mint_live_token as _real_mint_live_token
from ghostchef_ai.schemas import (
    CheckResult,
    LiveConfig,
    LiveToken,
    RecipeDraft,
    StepSpec,
    WatchFor,
    WatchResult,
)

__all__ = [
    "WatchFor", "StepSpec", "RecipeDraft", "CheckResult", "WatchResult", "LiveConfig", "LiveToken",
    "AIError", "AITimeout", "AIQuotaError", "AIUnavailable", "AIInvalidOutput",
    "extract_recipe", "check_frame", "watch_frame", "build_live_config", "mint_live_token",
    "model_ids",
]


async def extract_recipe(
    video_path: Path, *, title_hint: str | None = None, step_marks_s: list[float] | None = None
) -> RecipeDraft:
    if is_fake():
        return await fake.extract_recipe(
            video_path, title_hint=title_hint, step_marks_s=step_marks_s
        )
    return await ingest.extract_recipe(video_path, title_hint=title_hint,
                                       step_marks_s=step_marks_s)


async def check_frame(
    frame_jpeg: bytes, step: StepSpec, ref_image_jpeg: bytes | None, *, timeout_s: float = 8.0
) -> CheckResult:
    if is_fake():
        return await fake.check_frame(frame_jpeg, step, ref_image_jpeg, timeout_s=timeout_s)
    return await check.check_frame(frame_jpeg, step, ref_image_jpeg, timeout_s=timeout_s)


async def watch_frame(frame_jpeg: bytes, step: StepSpec, *, timeout_s: float = 3.5) -> WatchResult:
    if is_fake():
        return await fake.watch_frame(frame_jpeg, step, timeout_s=timeout_s)
    return await watch.watch_frame(frame_jpeg, step, timeout_s=timeout_s)


async def mint_live_token(live_config: LiveConfig) -> LiveToken:
    if is_fake():
        return await fake.mint_live_token(live_config)
    return await _real_mint_live_token(live_config)
