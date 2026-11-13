"""POST /check and POST /watch (API-CONTRACT §3)."""

from __future__ import annotations

import asyncio
import time
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile

from app import ai, metrics
from app.config import Settings, get_settings
from app.deps import get_store
from app.errors import ApiError
from app.schemas import CheckOut, WatchOut
from app.store.base import Event, Store, utcnow
from app.views import load_recipe, load_session, load_step, parse_uuid, step_spec

router = APIRouter(tags=["check and watch"])

StoreDep = Annotated[Store, Depends(get_store)]
SettingsDep = Annotated[Settings, Depends(get_settings)]

# Hard ceiling on what we read into memory. The contract limits (1.5 MB / 200 KB) and JPEG
# validation are enforced in BE-03.
MAX_FRAME_BYTES = 8 * 1024 * 1024
# Safety net on top of the budget ghostchef_ai enforces itself.
BUDGET_GRACE_S = 1.0


async def _read_frame(frame: UploadFile) -> bytes:
    data = await frame.read(MAX_FRAME_BYTES + 1)
    if len(data) > MAX_FRAME_BYTES:
        raise ApiError(413, "payload_too_large", "frame is too large")
    if not data:
        raise ApiError(422, "validation_error", "frame is empty")
    return data


async def _with_budget(coro: Any, budget_s: float, request_id: str) -> Any:
    try:
        return await asyncio.wait_for(coro, timeout=budget_s + BUDGET_GRACE_S)
    except TimeoutError:
        raise ApiError(
            504, "model_timeout", f"model did not answer within {budget_s:g} s", True, request_id
        ) from None


async def _record(
    store: Store,
    *,
    session_id: str,
    source: Literal["check", "watch"],
    kind: str | None,
    step_id: str,
    request_id: str,
    frame: bytes,
    body: dict[str, Any],
    latency_ms: int,
) -> None:
    frame_path = f"{session_id}/{request_id}.jpg"
    await store.put_blob("frames", frame_path, frame, "image/jpeg")
    at = utcnow()
    if kind is not None:
        await store.append_event(
            Event(
                session_id=session_id,
                kind=kind,
                step_id=step_id,
                request_id=request_id,
                payload={**body, "frame_path": frame_path},
                created_at=at,
            )
        )
    metrics.record(session_id, source, latency_ms, body, at, frame_path)


async def _common(
    request: Request, store: Store, step_id: str, request_id: str, session_id: str | None
):
    request_id = parse_uuid(request_id, "request_id")
    request.state.request_id = request_id
    step = await load_step(store, step_id)
    recipe = await load_recipe(store, step.recipe_id)
    session = await load_session(store, session_id) if session_id else None
    return request_id, step, recipe, session


@router.post("/check", response_model=CheckOut)
async def check(
    request: Request,
    store: StoreDep,
    settings: SettingsDep,
    frame: Annotated[UploadFile, File()],
    step_id: Annotated[str, Form()],
    request_id: Annotated[str, Form()],
    session_id: Annotated[str | None, Form()] = None,
    captured_at: Annotated[str | None, Form()] = None,
) -> CheckOut:
    request_id, step, _recipe, session = await _common(
        request, store, step_id, request_id, session_id
    )
    data = await _read_frame(frame)
    ref = await store.get_blob("media", step.ref_image_path) if step.ref_image_path else None
    g = ai.get()
    spec = step_spec(step)
    t0 = time.perf_counter()
    result = await _with_budget(
        g.check_frame(data, spec, ref, timeout_s=settings.check_budget_s),
        settings.check_budget_s,
        request_id,
    )
    latency_ms = round((time.perf_counter() - t0) * 1000)
    out = CheckOut(
        request_id=request_id,
        step_id=step.id,
        verdict=result.verdict,
        mistake_id=result.mistake_id,
        headline=result.headline,
        fix=result.fix,
        spoken=result.spoken,
        confidence=result.confidence,
        latency_ms=latency_ms,
        model=result.model,
    )
    if session is not None:
        await _record(
            store,
            session_id=session.id,
            source="check",
            kind=f"check_{out.verdict}",
            step_id=step.id,
            request_id=request_id,
            frame=data,
            body=out.model_dump(mode="json"),
            latency_ms=latency_ms,
        )
    return out


@router.post("/watch", response_model=WatchOut)
async def watch(
    request: Request,
    store: StoreDep,
    settings: SettingsDep,
    frame: Annotated[UploadFile, File()],
    step_id: Annotated[str, Form()],
    request_id: Annotated[str, Form()],
    session_id: Annotated[str | None, Form()] = None,
    captured_at: Annotated[str | None, Form()] = None,
) -> WatchOut:
    request_id, step, _recipe, session = await _common(
        request, store, step_id, request_id, session_id
    )
    data = await _read_frame(frame)
    g = ai.get()
    spec = step_spec(step)
    t0 = time.perf_counter()
    result = await _with_budget(
        g.watch_frame(data, spec, timeout_s=settings.watch_budget_s),
        settings.watch_budget_s,
        request_id,
    )
    latency_ms = round((time.perf_counter() - t0) * 1000)
    out = WatchOut(
        request_id=request_id,
        step_id=step.id,
        status=result.status,
        mistake_id=result.mistake_id,
        headline=result.headline,
        fix=result.fix,
        spoken=result.spoken,
        confidence=result.confidence,
        latency_ms=latency_ms,
        model=result.model,
    )
    if session is not None:
        await _record(
            store,
            session_id=session.id,
            source="watch",
            kind="watch_warn" if out.status == "warn" else None,
            step_id=step.id,
            request_id=request_id,
            frame=data,
            body=out.model_dump(mode="json"),
            latency_ms=latency_ms,
        )
    return out
