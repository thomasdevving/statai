"""watch_frame for real: one low-res frame + the step's known mistakes -> ok / warn.

ai/tasks/04 (AI-04.3). The model never writes text: it returns status, mistake_id and
confidence; headline, fix and spoken are copied from the matching WatchFor. No retry here:
the watcher's next tick is the retry.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from ghostchef_ai import client, prompts
from ghostchef_ai.config import model_ids
from ghostchef_ai.errors import AIError, AIInvalidOutput
from ghostchef_ai.schemas import StepSpec, WatchResult

log = logging.getLogger(__name__)

FRAME_LABEL = "PHOTO (now):"
# The answer is ~30-40 tokens of pretty-printed JSON; the rest is headroom for minimal thinking.
MAX_OUTPUT_TOKENS = 150
# Media resolution for watch: True = LOW (fastest), the AI-02 "lowest setting that works".
LOW_DETAIL = True
# Reported as `model` when no call is made (a step without watch_fors).
NO_CALL_MODEL = "none"


class RawWatch(BaseModel):
    status: Literal["ok", "warn"]
    mistake_id: str | None = None
    confidence: float


@dataclass
class WatchOutcome:
    result: WatchResult
    raw: RawWatch | None
    latency_ms: int


def response_schema(step: StepSpec) -> dict[str, Any]:
    ids = [w.id for w in step.watch_fors]
    return {
        "type": "object",
        "properties": {
            "status": {"type": "string", "enum": ["ok", "warn"]},
            "mistake_id": {"type": ["string", "null"], "enum": [*ids, None]},
            "confidence": {"type": "number", "description": "0 to 1."},
        },
        "required": ["status", "mistake_id", "confidence"],
        "additionalProperties": False,
    }


def build_prompt(step: StepSpec) -> str:
    mistakes = "\n".join(f"- {w.id}: {w.mistake}" for w in step.watch_fors)
    return prompts.render("watch", STEP_TITLE=step.title, MISTAKES=mistakes)


def ok_result(model: str, confidence: float = 0.0) -> WatchResult:
    return WatchResult(status="ok", mistake_id=None, headline="", fix="", spoken="",
                       confidence=confidence, model=model)


def postprocess(raw: RawWatch, step: StepSpec, model: str) -> WatchResult:
    confidence = min(1.0, max(0.0, float(raw.confidence)))
    known = step.watch_for(raw.mistake_id)
    if raw.status == "warn" and known:
        return WatchResult(status="warn", mistake_id=known.id, headline=known.headline,
                           fix=known.fix, spoken=known.spoken, confidence=confidence,
                           model=model)
    if raw.status == "warn":
        # warn with a null or unknown id: the watcher never invents mistakes (§3.2).
        return ok_result(model)
    return ok_result(model, confidence)


async def run_watch(frame_jpeg: bytes, step: StepSpec, *, timeout_s: float = 3.5,
                    model: str | None = None, low_detail: bool | None = None) -> WatchOutcome:
    """watch_frame plus what eval scripts need (raw answer, latency)."""
    if not step.watch_fors:
        return WatchOutcome(result=ok_result(NO_CALL_MODEL), raw=None, latency_ms=0)
    model = model or model_ids()["watch"]
    low_detail = LOW_DETAIL if low_detail is None else low_detail
    start = time.perf_counter()
    try:
        res = await asyncio.wait_for(client.image_json(
            model=model,
            prompt=build_prompt(step),
            images=[(FRAME_LABEL, frame_jpeg)],
            schema=response_schema(step),
            schema_name="watch_result",
            timeout_s=timeout_s,
            max_output_tokens=MAX_OUTPUT_TOKENS,
            low_detail=low_detail,
        ), timeout=timeout_s)
        raw = RawWatch.model_validate(res.data)
    except ValidationError as exc:
        raise AIInvalidOutput(f"watch output did not match the schema: {exc}"[:500]) from exc
    except AIError:
        raise
    except Exception as exc:  # noqa: BLE001 — includes asyncio.TimeoutError
        raise client.map_error(exc) from exc
    latency_ms = round((time.perf_counter() - start) * 1000)
    result = postprocess(raw, step, model)
    log.info("watch_frame step=%s status=%s->%s mistake=%s conf=%.2f %d ms", step.idx,
             raw.status, result.status, result.mistake_id, result.confidence, latency_ms)
    return WatchOutcome(result=result, raw=raw, latency_ms=latency_ms)


async def watch_frame(frame_jpeg: bytes, step: StepSpec, *, timeout_s: float = 3.5) -> WatchResult:
    return (await run_watch(frame_jpeg, step, timeout_s=timeout_s)).result
