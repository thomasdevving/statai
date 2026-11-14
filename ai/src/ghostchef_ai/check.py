"""check_frame for real: learner frame + chef reference + step criteria -> pass / fix / unsure.

ai/tasks/04 (AI-04.2). The model returns a small JSON object; display strings come from the
recipe's watch_fors where they exist, and every rule below runs in code, not in the prompt.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from ghostchef_ai import client, prompts
from ghostchef_ai.config import model_ids
from ghostchef_ai.errors import AIError, AIInvalidOutput, AITimeout
from ghostchef_ai.schemas import CheckResult, StepSpec, clamp_words

log = logging.getLogger(__name__)

REF_LABEL = "REFERENCE (chef, correct result of this step):"
LEARNER_LABEL = "LEARNER (current state):"
REF_NOTE = "The REFERENCE photo shows the chef's correct result of this step."
NO_REF_NOTE = ("No reference photo is available for this step: judge from the success criteria "
               "only.")

# Thinking tokens count against this limit (ai/STATUS.md, AI-02 findings). The answer itself is
# ~100-150 tokens of pretty-printed JSON. The lite model at MINIMAL thinking needs ~400; models
# that only accept LOW thinking (gemini-3.8-flash) think for several hundred tokens more.
MAX_OUTPUT_TOKENS = 1024
# Media resolution for check: False = MEDIUM (more detail for the judgement), True = LOW.
LOW_DETAIL = False
# A pass or fix below this confidence is reported as unsure (AI-04.2 rule 5).
MIN_CONFIDENCE = 0.5
HEADLINE_WORDS = 4
FIX_WORDS = 8

PASS_HEADLINE = "Looks right"
PASS_SPOKEN = "That looks right. On to the next step."
FIX_HEADLINE = "Not quite right"
FIX_FIX = "Compare with the chef's photo"
UNSURE_HEADLINE = "Can't tell"
UNSURE_FIX = "Hold still and look straight at it"
UNSURE_SPOKEN = ("I can't tell from this view. Hold still, look straight at your work, and "
                 "check again.")


class RawCheck(BaseModel):
    """What the model returns. `evidence` is logged, never returned to clients."""

    evidence: str = ""
    verdict: Literal["pass", "fix", "unsure"]
    mistake_id: str | None = None
    headline: str = ""
    fix: str = ""
    spoken: str = ""
    confidence: float


@dataclass
class CheckOutcome:
    result: CheckResult
    raw: RawCheck
    latency_ms: int
    attempts: int


def response_schema(step: StepSpec) -> dict[str, Any]:
    ids = [w.id for w in step.watch_fors]
    mistake = ({"type": ["string", "null"], "enum": [*ids, None]} if ids else {"type": "null"})
    return {
        "type": "object",
        "properties": {
            # First, so the model looks before it decides.
            "evidence": {"type": "string",
                         "description": "Per criterion: met / not met / hidden, a few words each."},
            "verdict": {"type": "string", "enum": ["pass", "fix", "unsure"]},
            "mistake_id": mistake,
            "headline": {"type": "string", "description": "At most 4 words."},
            "fix": {"type": "string", "description": "At most 8 words; empty for pass."},
            "spoken": {"type": "string", "description": "One sentence, at most 20 words."},
            "confidence": {"type": "number", "description": "0 to 1."},
        },
        "required": ["evidence", "verdict", "mistake_id", "headline", "fix", "spoken",
                     "confidence"],
        "additionalProperties": False,
    }


def step_json(step: StepSpec) -> str:
    return json.dumps({
        "title": step.title,
        "instruction": step.instruction,
        "success_criteria": step.success_criteria,
        "watch_fors": [{"id": w.id, "mistake": w.mistake} for w in step.watch_fors],
    }, indent=2, ensure_ascii=False)


def build_prompt(step: StepSpec, has_ref: bool) -> str:
    return prompts.render("check", REFERENCE_NOTE=REF_NOTE if has_ref else NO_REF_NOTE,
                          STEP_JSON=step_json(step))


def build_images(frame_jpeg: bytes, ref_image_jpeg: bytes | None) -> list[tuple[str, bytes]]:
    images = [(REF_LABEL, ref_image_jpeg)] if ref_image_jpeg else []
    return [*images, (LEARNER_LABEL, frame_jpeg)]


def _spoken_from(headline: str, fix: str) -> str:
    parts = [p.strip().rstrip(".") for p in (headline, fix) if p.strip()]
    return ". ".join(parts) + "." if parts else ""


def postprocess(raw: RawCheck, step: StepSpec, model: str) -> CheckResult:
    """Apply AI-04.2's post-processing rules, in the task's order."""
    verdict = raw.verdict
    headline, fix, spoken = raw.headline.strip(), raw.fix.strip(), raw.spoken.strip()

    # 1. Unknown mistake_id -> None. Only a fix names a mistake (API-CONTRACT §3.1).
    known = step.watch_for(raw.mistake_id)
    mistake_id = known.id if known and verdict == "fix" else None

    # 2. A known mistake's strings replace the model's own.
    if mistake_id and known:
        headline, fix, spoken = known.headline, known.fix, known.spoken

    # 3. pass: no fix, no mistake, a default headline.
    if verdict == "pass":
        fix, mistake_id = "", None
        headline = headline or PASS_HEADLINE
        spoken = spoken or PASS_SPOKEN
    elif verdict == "fix":
        headline = headline or FIX_HEADLINE
        fix = fix or FIX_FIX
    else:
        headline = headline or UNSURE_HEADLINE
        fix = fix or UNSURE_FIX
        spoken = spoken or UNSURE_SPOKEN

    # 4. Word limits.
    headline = clamp_words(headline, HEADLINE_WORDS)
    fix = clamp_words(fix, FIX_WORDS)

    # 5. Confidence 0..1; a low-confidence pass or fix becomes unsure.
    confidence = min(1.0, max(0.0, float(raw.confidence)))
    if verdict in ("pass", "fix") and confidence < MIN_CONFIDENCE:
        verdict, mistake_id = "unsure", None
        headline, fix, spoken = UNSURE_HEADLINE, UNSURE_FIX, UNSURE_SPOKEN

    # 6. The model actually used.
    return CheckResult(verdict=verdict, mistake_id=mistake_id, headline=headline, fix=fix,
                       spoken=spoken or _spoken_from(headline, fix), confidence=confidence,
                       model=model)


async def _attempt(frame_jpeg, step, ref_image_jpeg, model, timeout_s, low_detail) -> RawCheck:
    res = await client.image_json(
        model=model,
        prompt=build_prompt(step, ref_image_jpeg is not None),
        images=build_images(frame_jpeg, ref_image_jpeg),
        schema=response_schema(step),
        schema_name="check_result",
        timeout_s=timeout_s,
        max_output_tokens=MAX_OUTPUT_TOKENS,
        low_detail=low_detail,
    )
    try:
        return RawCheck.model_validate(res.data)
    except ValidationError as exc:
        raise AIInvalidOutput(f"check output did not match the schema: {exc}"[:500]) from exc


async def run_check(frame_jpeg: bytes, step: StepSpec, ref_image_jpeg: bytes | None, *,
                    timeout_s: float = 8.0, model: str | None = None,
                    low_detail: bool | None = None) -> CheckOutcome:
    """check_frame plus what eval scripts need (raw answer with evidence, latency, attempts).

    The whole call, including the one retry on AIInvalidOutput, stays within timeout_s.
    """
    model = model or model_ids()["check"]
    low_detail = LOW_DETAIL if low_detail is None else low_detail
    start = time.perf_counter()
    deadline = start + timeout_s
    attempts = 0
    while True:
        attempts += 1
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            raise AITimeout(f"check_frame used its {timeout_s:g} s budget")
        try:
            raw = await asyncio.wait_for(
                _attempt(frame_jpeg, step, ref_image_jpeg, model, remaining, low_detail),
                timeout=remaining)
            break
        except AIInvalidOutput:
            if attempts >= 2:
                raise
            log.warning("check_frame: invalid output from %s, retrying once", model)
        except AIError:
            raise
        except Exception as exc:  # noqa: BLE001 — includes asyncio.TimeoutError
            raise client.map_error(exc) from exc
    latency_ms = round((time.perf_counter() - start) * 1000)
    result = postprocess(raw, step, model)
    log.info("check_frame step=%s verdict=%s->%s mistake=%s conf=%.2f %d ms evidence=%r",
             step.idx, raw.verdict, result.verdict, result.mistake_id, result.confidence,
             latency_ms, raw.evidence)
    return CheckOutcome(result=result, raw=raw, latency_ms=latency_ms, attempts=attempts)


async def check_frame(frame_jpeg: bytes, step: StepSpec, ref_image_jpeg: bytes | None, *,
                      timeout_s: float = 8.0) -> CheckResult:
    return (await run_check(frame_jpeg, step, ref_image_jpeg, timeout_s=timeout_s)).result
