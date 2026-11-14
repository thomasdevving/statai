"""extract_recipe for real: chef video -> RecipeDraft (ai/tasks/06, AI-06.2).

Flow: upload the MP4 through the Gemini Files API, wait until it is ACTIVE, one structured
generate call, repair the output in code (a slightly long title must not fail a 3-minute job),
validate against RecipeDraft, retry the generate call once on invalid output, and always delete
the uploaded file. Video understanding is Gemini-only; the OpenAI stand-in has no path here.

The package reads nothing from disk except `video_path` and never calls ffmpeg: timestamps may
exceed the real video length, and the backend clamps them with ffprobe (API-CONTRACT §7).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from ghostchef_ai import client, prompts
from ghostchef_ai.config import model_ids, provider
from ghostchef_ai.errors import AIError, AIInvalidOutput, AIUnavailable
from ghostchef_ai.schemas import RecipeDraft, clamp_words

log = logging.getLogger(__name__)

TIMEOUT_S = 180.0             # the generate call (background job, not interactive)
PROCESSING_TIMEOUT_S = 300.0  # Files API: upload -> ACTIVE
POLL_INTERVAL_S = 2.0
# Thinking tokens count against this limit; a 10-step recipe plus a transcript is a few
# thousand tokens of JSON.
MAX_OUTPUT_TOKENS = 16384
THINKING_ORDER = ("MINIMAL", "LOW", None)

TITLE_WORDS, KEY_LINE_WORDS, HEADLINE_WORDS, FIX_WORDS = 4, 8, 4, 8
MAX_STEPS = 10
WATCH_FOR_FIELDS = ("mistake", "headline", "fix", "spoken")

_NULLABLE_STR = {"type": ["string", "null"]}
_NULLABLE_NUM = {"type": ["number", "null"]}

# What the model returns. Lenient on purpose: word limits and id format are repaired in code,
# then RecipeDraft validates the result.
RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "transcript": {"type": "string"},
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "key_line": {"type": "string"},
                    "instruction": {"type": "string"},
                    "chef_quote": _NULLABLE_STR,
                    "timestamp_s": {"type": "number"},
                    "clip_start_s": _NULLABLE_NUM,
                    "clip_end_s": _NULLABLE_NUM,
                    "success_criteria": {"type": "array", "items": {"type": "string"}},
                    "watch_fors": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "mistake": {"type": "string"},
                                "headline": {"type": "string"},
                                "fix": {"type": "string"},
                                "spoken": {"type": "string"},
                            },
                            "required": ["id", "mistake", "headline", "fix", "spoken"],
                        },
                    },
                    "timer_s": {"type": ["integer", "null"]},
                },
                "required": ["title", "key_line", "instruction", "chef_quote", "timestamp_s",
                             "clip_start_s", "clip_end_s", "success_criteria", "watch_fors",
                             "timer_s"],
            },
        },
    },
    "required": ["title", "transcript", "steps"],
}


# --------------------------------------------------------------------------- prompt


def build_prompt(title_hint: str | None, step_marks_s: list[float] | None) -> str:
    hint = (f'Title hint from the uploader: "{title_hint}".' if title_hint
            else "No title hint was given.")
    if step_marks_s:
        marks = ", ".join(f"{m:g}" for m in step_marks_s)
        mark_text = (f"While recording, the expert marked a new step at these seconds: {marks}. "
                     "Treat them as hints for step boundaries: you may merge, split, or ignore "
                     "a mark when the step rules below require it.")
    else:
        mark_text = "No step marks were given."
    return prompts.render("extract", TITLE_HINT=hint, STEP_MARKS=mark_text)


# --------------------------------------------------------------------------- repair


def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")
    if not s:
        return "mistake"
    return s if s[0].isalpha() else f"m_{s}"


def _num(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f == f and abs(f) != float("inf") else None  # drop NaN / inf


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _repair_watch_fors(items: Any) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for w in items if isinstance(items, list) else []:
        if not isinstance(w, dict):
            continue
        fields = {k: _text(w.get(k)) for k in WATCH_FOR_FIELDS}
        if not all(fields.values()):  # drop entries missing any string
            continue
        base = slugify(_text(w.get("id")) or fields["mistake"])
        wid, n = base, 2
        while wid in seen:  # de-duplicate within a step: id, id_2, id_3
            wid, n = f"{base}_{n}", n + 1
        seen.add(wid)
        out.append({
            "id": wid,
            "mistake": fields["mistake"],
            "headline": clamp_words(fields["headline"], HEADLINE_WORDS),
            "fix": clamp_words(fields["fix"], FIX_WORDS),
            "spoken": fields["spoken"],
        })
    return out


def repair(data: Any, *, title_hint: str | None = None) -> dict[str, Any]:
    """Make model output fit RecipeDraft without losing usable steps (AI-06.2 step 3)."""
    if not isinstance(data, dict):
        raise AIInvalidOutput("extraction output is not a JSON object")
    steps: list[dict[str, Any]] = []
    for s in data.get("steps") or []:
        if not isinstance(s, dict):
            continue
        title = clamp_words(_text(s.get("title")), TITLE_WORDS)
        instruction = _text(s.get("instruction"))
        if not title or not instruction:
            continue  # a step without a name or an instruction is not usable
        ts = _num(s.get("timestamp_s"))
        ts = max(0.0, ts) if ts is not None else 0.0
        start, end = _num(s.get("clip_start_s")), _num(s.get("clip_end_s"))
        start = max(0.0, start) if start is not None else None
        end = max(0.0, end) if end is not None else None
        if start is None or end is None or end <= start:
            start = end = None
        timer = _num(s.get("timer_s"))
        criteria = [c.strip() for c in s.get("success_criteria") or []
                    if isinstance(c, str) and c.strip()]
        steps.append({
            "title": title,
            "key_line": clamp_words(_text(s.get("key_line")) or title, KEY_LINE_WORDS),
            "instruction": instruction,
            "chef_quote": _text(s.get("chef_quote")) or None,
            "timestamp_s": ts,
            "clip_start_s": start,
            "clip_end_s": end,
            "success_criteria": criteria,
            "watch_fors": _repair_watch_fors(s.get("watch_fors")),
            "timer_s": int(timer) if timer and timer > 0 else None,
        })
    steps.sort(key=lambda s: s["timestamp_s"])  # stable: equal times keep model order
    steps = steps[:MAX_STEPS]
    for i, s in enumerate(steps, start=1):
        s["idx"] = i
    title = _text(data.get("title")) or _text(title_hint) or "Untitled recipe"
    return {"title": title, "transcript": _text(data.get("transcript")), "steps": steps}


def validate(data: Any, *, title_hint: str | None = None) -> RecipeDraft:
    fixed = repair(data, title_hint=title_hint)
    if not fixed["steps"]:
        raise AIInvalidOutput("extraction returned no usable steps")
    try:
        return RecipeDraft.model_validate(fixed)
    except ValidationError as exc:
        raise AIInvalidOutput(f"extraction output did not validate: {exc}"[:500]) from exc


# --------------------------------------------------------------------------- Gemini calls


def _state(f: Any) -> str:
    st = getattr(f, "state", None)
    return getattr(st, "name", None) or str(st or "")


async def _wait_active(aio_files: Any, f: Any, timeout_s: float) -> Any:
    deadline = time.monotonic() + timeout_s
    while _state(f).endswith("PROCESSING"):
        if time.monotonic() > deadline:
            raise AIUnavailable(f"video still processing after {timeout_s:g} s")
        await asyncio.sleep(POLL_INTERVAL_S)
        f = await aio_files.get(name=f.name)
    if not _state(f).endswith("ACTIVE"):
        raise AIUnavailable(f"video processing failed (state {_state(f) or 'unknown'})")
    return f


def _config(level: str | None):
    from google.genai import types

    return types.GenerateContentConfig(
        temperature=0,
        max_output_tokens=MAX_OUTPUT_TOKENS,
        response_mime_type="application/json",
        response_json_schema=RESPONSE_SCHEMA,
        thinking_config=(types.ThinkingConfig(thinking_level=getattr(types.ThinkingLevel, level))
                         if level else None),
    )


async def _generate(aio_models: Any, model: str, uploaded: Any, prompt: str,
                    timeout_s: float) -> Any:
    """One generate call; steps down the thinking level if the model rejects it (unbilled)."""
    for level in THINKING_ORDER:
        try:
            return await client.call_with_budget(
                aio_models.generate_content(model=model, contents=[uploaded, prompt],
                                            config=_config(level)),
                timeout_s)
        except AIUnavailable as exc:
            if level is None or "thinking" not in str(exc).lower():
                raise
            client.usage.calls -= 1  # a rejected request is not billed
            log.info("extract: %s rejects thinking %s", model, level)
    raise AIUnavailable(f"{model}: no accepted thinking setting")  # pragma: no cover


def _parse(resp: Any, model: str) -> Any:
    meta = getattr(resp, "usage_metadata", None)
    client.usage.add(model, getattr(meta, "prompt_token_count", 0) or 0,
                     (getattr(meta, "candidates_token_count", 0) or 0)
                     + (getattr(meta, "thoughts_token_count", 0) or 0))
    cands = getattr(resp, "candidates", None) or []
    finish = getattr(getattr(cands[0], "finish_reason", None), "name", "") if cands else ""
    if finish == "MAX_TOKENS":
        raise AIInvalidOutput(f"{model}: extraction cut off at {MAX_OUTPUT_TOKENS} tokens")
    text = getattr(resp, "text", None) or ""
    if not text.strip():
        raise AIInvalidOutput(f"{model}: empty extraction (finish reason {finish or 'unknown'})")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise AIInvalidOutput(f"{model}: extraction is not JSON ({exc})") from exc


@dataclass
class ExtractOutcome:
    draft: RecipeDraft
    model: str
    upload_s: float
    generate_s: float
    attempts: int


async def run_extract(video_path: Path, *, title_hint: str | None = None,
                      step_marks_s: list[float] | None = None, model: str | None = None,
                      timeout_s: float = TIMEOUT_S) -> ExtractOutcome:
    """extract_recipe plus timings for the CLI and STATUS."""
    if provider() != "gemini":
        raise AIUnavailable("extract_recipe needs Gemini (video is not supported on the "
                            f"{provider()} stand-in); set GHOSTCHEF_PROVIDER=gemini")
    path = Path(video_path)
    if not path.is_file():
        raise AIUnavailable(f"video not found: {path}")
    model = model or model_ids()["video"]
    prompt = build_prompt(title_hint, step_marks_s)
    aio = client.gemini_client().aio
    t0 = time.perf_counter()
    try:
        uploaded = await aio.files.upload(file=str(path))
    except AIError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise client.map_error(exc) from exc
    try:
        try:
            uploaded = await _wait_active(aio.files, uploaded, PROCESSING_TIMEOUT_S)
        except AIError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise client.map_error(exc) from exc
        t1 = time.perf_counter()
        attempts = 0
        while True:
            attempts += 1
            try:
                resp = await _generate(aio.models, model, uploaded, prompt, timeout_s)
                draft = validate(_parse(resp, model), title_hint=title_hint)
                break
            except AIInvalidOutput as exc:
                if attempts >= 2:
                    raise
                log.warning("extract: invalid output, retrying once: %s", exc)
        return ExtractOutcome(draft, model, t1 - t0, time.perf_counter() - t1, attempts)
    finally:
        try:
            await aio.files.delete(name=uploaded.name)
        except Exception as exc:  # noqa: BLE001 — cleanup must never mask the real result
            log.warning("extract: could not delete uploaded file: %s", exc)


async def extract_recipe(video_path: Path, *, title_hint: str | None = None,
                         step_marks_s: list[float] | None = None) -> RecipeDraft:
    out = await run_extract(video_path, title_hint=title_hint, step_marks_s=step_marks_s)
    return out.draft
