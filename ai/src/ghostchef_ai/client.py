"""Model clients, time budgets, error mapping, call budget, and a JSON-from-images helper.

Two providers sit behind one helper, `image_json`:
- gemini: the product (Google DeepMind challenge). Real clients are created lazily.
- openai: a TEMPORARY development stand-in while Gemini access is pending. Never report its
  results as Gemini results. Video and Live are Gemini-only and have no OpenAI path.

Every paid call goes through `call_with_budget`, which enforces the timeout and the
per-process call cap (config.max_calls) and maps provider errors to AIError subclasses.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
from collections.abc import Awaitable
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, TypeVar

from pydantic import ValidationError

from ghostchef_ai.config import max_calls, provider
from ghostchef_ai.errors import AIError, AIInvalidOutput, AIQuotaError, AITimeout, AIUnavailable

T = TypeVar("T")


# --------------------------------------------------------------------------- budget and usage


@dataclass
class Usage:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    by_model: dict[str, list[int]] = field(default_factory=dict)  # model -> [calls, in, out]

    def add(self, model: str, input_tokens: int, output_tokens: int) -> None:
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        row = self.by_model.setdefault(model, [0, 0, 0])
        row[0] += 1
        row[1] += input_tokens
        row[2] += output_tokens


usage = Usage()


def reset_usage() -> None:
    global usage
    usage = Usage()


def _spend_one_call() -> None:
    cap = max_calls()
    if cap and usage.calls >= cap:
        raise AIQuotaError(
            f"call budget exhausted ({usage.calls}/{cap} calls in this process); "
            "raise GHOSTCHEF_MAX_CALLS deliberately if you mean to spend more"
        )
    usage.calls += 1


async def call_with_budget(coro: Awaitable[T], timeout_s: float) -> T:
    """Count one paid call against the cap, await it within timeout_s, map errors."""
    try:
        _spend_one_call()
    except AIQuotaError:
        if asyncio.iscoroutine(coro):
            coro.close()
        raise
    try:
        return await asyncio.wait_for(coro, timeout=timeout_s)
    except AIError:
        raise
    except Exception as exc:  # noqa: BLE001 — every provider error is mapped below
        raise map_error(exc) from exc


# --------------------------------------------------------------------------- error mapping


def _status_of(exc: BaseException) -> int | None:
    for attr in ("status_code", "code"):
        v = getattr(exc, attr, None)
        if isinstance(v, int):
            return v
    return None


def map_error(exc: BaseException) -> AIError:
    """Translate any provider / transport / parsing error into an AIError subclass.

    Works on class names and status codes, so it covers google-genai and openai without
    importing either. Messages never include request headers or keys.
    """
    if isinstance(exc, AIError):
        return exc
    name = type(exc).__name__
    if isinstance(exc, TimeoutError | asyncio.TimeoutError) or "Timeout" in name:
        return AITimeout(f"model did not answer in time ({name})")
    if isinstance(exc, ValidationError | json.JSONDecodeError) or name in (
        "LengthFinishReasonError", "ContentFilterFinishReasonError", "APIResponseValidationError"
    ):
        return AIInvalidOutput(f"model output did not match the schema ({name}: {exc})"[:500])
    status = _status_of(exc)
    if status == 504 or "DEADLINE_EXCEEDED" in str(exc):
        return AITimeout(f"model timed out on the server ({name})")
    if status == 429 or name == "RateLimitError" or "RESOURCE_EXHAUSTED" in str(exc):
        return AIQuotaError(f"rate limit or quota exhausted ({name})")
    msg = str(exc).splitlines()[0][:300] if str(exc) else ""
    err = AIUnavailable(f"{name}{f' {status}' if status else ''}: {msg}")
    err.status = status  # lets callers tell a request rejection (400) from an outage (5xx)
    return err


# --------------------------------------------------------------------------- clients


@lru_cache(maxsize=2)
def gemini_client(api_version: str | None = None):
    """google-genai client. api_version='v1beta' is needed for ephemeral tokens (AI-05)."""
    if not os.environ.get("GEMINI_API_KEY"):
        raise AIUnavailable("GEMINI_API_KEY is not set (ai/.env)")
    from google import genai

    opts = {"api_version": api_version} if api_version else None
    return genai.Client(api_key=os.environ["GEMINI_API_KEY"], http_options=opts)


@lru_cache(maxsize=1)
def openai_client():
    """AsyncOpenAI client for the temporary stand-in. Retries are ours, not the SDK's."""
    if not os.environ.get("OPENAI_API_KEY"):
        raise AIUnavailable("OPENAI_API_KEY is not set (ai/.env)")
    try:
        from openai import AsyncOpenAI
    except ImportError as exc:
        raise AIUnavailable('openai package missing: pip install -e ".[openai]"') from exc
    return AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"], max_retries=0)


def reset_clients() -> None:
    gemini_client.cache_clear()
    openai_client.cache_clear()


# --------------------------------------------------------------------------- image -> JSON

# Parameters some OpenAI models reject (e.g. reasoning models and temperature). Learned per
# model from the first 400 response, which is not billed, then left out.
_openai_unsupported: dict[str, set[str]] = {}


@dataclass
class ImageJsonResult:
    data: dict[str, Any]
    model: str
    input_tokens: int
    output_tokens: int


async def image_json(
    *,
    model: str,
    prompt: str,
    images: list[tuple[str, bytes]],
    schema: dict[str, Any],
    schema_name: str,
    timeout_s: float,
    max_output_tokens: int = 200,
    low_detail: bool = True,
) -> ImageJsonResult:
    """One model call: labelled JPEG images + prompt in, schema-valid JSON object out.

    images: [(label, jpeg_bytes)]; each label is sent as text right before its image.
    Raises AIError subclasses only.
    """
    if provider() == "openai":
        return await _openai_image_json(model, prompt, images, schema, schema_name, timeout_s,
                                         max_output_tokens, low_detail)
    return await _gemini_image_json(model, prompt, images, schema, timeout_s,
                                     max_output_tokens, low_detail)


async def _openai_image_json(model, prompt, images, schema, schema_name, timeout_s,
                             max_output_tokens, low_detail) -> ImageJsonResult:
    content: list[dict[str, Any]] = []
    for label, jpeg in images:
        content.append({"type": "text", "text": label})
        content.append({
            "type": "image_url",
            "image_url": {
                "url": "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii"),
                "detail": "low" if low_detail else "auto",
            },
        })
    content.append({"type": "text", "text": prompt})
    params: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": schema_name, "schema": schema, "strict": True},
        },
        "max_completion_tokens": max_output_tokens,
        "temperature": 0,
        "reasoning_effort": "minimal",
    }
    client = openai_client()
    for _ in range(3):  # drop unsupported optional params learned from 400s, then give up
        for p in _openai_unsupported.get(model, ()):
            params.pop(p, None)
        try:
            resp = await call_with_budget(client.chat.completions.create(**params), timeout_s)
            break
        except AIUnavailable as exc:
            bad = [p for p in ("temperature", "reasoning_effort") if p in str(exc) and p in params]
            if not bad:
                raise
            _openai_unsupported.setdefault(model, set()).update(bad)
            usage.calls -= 1  # a rejected request is not billed
    else:
        raise AIUnavailable(f"{model}: could not find accepted request parameters")
    choice = resp.choices[0]
    text = choice.message.content or ""
    in_tok = getattr(resp.usage, "prompt_tokens", 0) or 0
    out_tok = getattr(resp.usage, "completion_tokens", 0) or 0
    usage.add(model, in_tok, out_tok)
    if choice.finish_reason == "length":
        raise AIInvalidOutput(f"{model}: output cut off at {max_output_tokens} tokens")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise map_error(exc) from exc
    return ImageJsonResult(data, getattr(resp, "model", model), in_tok, out_tok)


# Thinking levels to try, lightest first; None = send no thinking config. A model that rejects
# a level (unbilled 400, e.g. "Thinking level MINIMAL is not supported") moves to the next one.
_GEMINI_THINKING_ORDER = ("MINIMAL", "LOW", None)
_gemini_thinking_level: dict[str, str | None] = {}
# Kept for tests and callers that only need "does this model reject thinking config".
_gemini_no_thinking_cfg: set[str] = set()


async def _gemini_image_json(model, prompt, images, schema, timeout_s, max_output_tokens,
                             low_detail) -> ImageJsonResult:
    from google.genai import types

    parts: list[Any] = []
    for label, jpeg in images:
        parts.append(label)
        parts.append(types.Part.from_bytes(data=jpeg, mime_type="image/jpeg"))
    parts.append(prompt)

    def config(level: str | None) -> types.GenerateContentConfig:
        return types.GenerateContentConfig(
            temperature=0,
            max_output_tokens=max_output_tokens,
            response_mime_type="application/json",
            response_json_schema=schema,
            media_resolution=(types.MediaResolution.MEDIA_RESOLUTION_LOW if low_detail
                              else types.MediaResolution.MEDIA_RESOLUTION_MEDIUM),
            # Thinking tokens count against max_output_tokens; keep them light for latency.
            thinking_config=(types.ThinkingConfig(thinking_level=getattr(types.ThinkingLevel,
                                                                         level))
                             if level else None),
        )

    aio = gemini_client().aio.models
    if model in _gemini_no_thinking_cfg:
        levels = [None]
    elif model in _gemini_thinking_level:
        levels = [_gemini_thinking_level[model]]
    else:
        levels = list(_GEMINI_THINKING_ORDER)
    for i, level in enumerate(levels):
        try:
            resp = await call_with_budget(
                aio.generate_content(model=model, contents=parts, config=config(level)),
                timeout_s)
            _gemini_thinking_level[model] = level
            break
        except AIUnavailable as exc:
            last = i == len(levels) - 1
            if last or level is None or "thinking" not in str(exc).lower():
                raise
            usage.calls -= 1  # a rejected request is not billed
            if levels[i + 1] is None:
                _gemini_no_thinking_cfg.add(model)
    meta = getattr(resp, "usage_metadata", None)
    in_tok = getattr(meta, "prompt_token_count", 0) or 0
    out_tok = (getattr(meta, "candidates_token_count", 0) or 0) + (
        getattr(meta, "thoughts_token_count", 0) or 0)
    usage.add(model, in_tok, out_tok)
    cands = getattr(resp, "candidates", None) or []
    finish = getattr(getattr(cands[0], "finish_reason", None), "name", "") if cands else ""
    if finish == "MAX_TOKENS":
        raise AIInvalidOutput(f"{model}: output cut off at {max_output_tokens} tokens "
                              f"(thinking tokens count against this limit)")
    text = resp.text or ""
    if not text.strip():
        raise AIInvalidOutput(f"{model}: empty answer (finish reason {finish or 'unknown'})")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise map_error(exc) from exc
    return ImageJsonResult(data, model, in_tok, out_tok)
