"""POST /check and POST /watch (API-CONTRACT §3, BE-03)."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Request, UploadFile

from app import ai, metrics, refcache
from app.config import Settings, get_settings
from app.deps import get_store
from app.errors import ApiError, status_of
from app.logs import log_call
from app.media import images
from app.schemas import CheckOut, WatchOut
from app.store.base import Event, Store, utcnow
from app.views import load_session, load_step, parse_uuid, step_spec

router = APIRouter(tags=["check and watch"])
log = logging.getLogger("ghostchef.frames")

StoreDep = Annotated[Store, Depends(get_store)]
SettingsDep = Annotated[Settings, Depends(get_settings)]

Endpoint = Literal["check", "watch"]

# Safety net on top of the budget ghostchef_ai enforces itself (BE-03.4).
BUDGET_GRACE_S = 0.5

# Sessions with a /watch call running. Checked and claimed with no await in between, so two
# overlapping calls for one session cannot both pass.
_watch_inflight: set[str] = set()


def _required(value: str | None, name: str) -> str:
    if value is None or not value.strip():
        raise ApiError(422, "validation_error", f"{name} is required")
    return value


async def _read_frame(frame: UploadFile | None) -> bytes:
    if frame is None:
        raise ApiError(422, "validation_error", "frame is required")
    # Read one byte past the hard limit so validate_jpeg can answer 413.
    return await frame.read(images.CHECK_MAX_BYTES + 1)


async def _with_budget(coro: Any, budget_s: float, request_id: str) -> Any:
    try:
        return await asyncio.wait_for(coro, timeout=budget_s + BUDGET_GRACE_S)
    except TimeoutError:
        raise ApiError(
            504, "model_timeout", f"model did not answer within {budget_s:g} s", True, request_id
        ) from None


async def _persist(
    store: Store,
    *,
    session_id: str,
    kind: str,
    step_id: str,
    request_id: str,
    frame: bytes,
    body: dict[str, Any],
    at: datetime,
) -> None:
    """Runs after the response is sent: storage latency never delays the wearer."""
    payload = dict(body)
    frame_path = f"{session_id}/{request_id}.jpg"
    try:
        await store.put_blob("frames", frame_path, frame, "image/jpeg")
        payload["frame_path"] = frame_path
    except Exception:  # noqa: BLE001 - the event is still worth keeping without its frame
        log.exception("storing frame for session %s failed", session_id)
    try:
        await store.append_event(
            Event(
                session_id=session_id,
                kind=kind,
                step_id=step_id,
                request_id=request_id,
                payload=payload,
                created_at=at,
            )
        )
    except Exception:  # noqa: BLE001 - background task: log, never crash
        log.exception("recording %s event for session %s failed", kind, session_id)


async def _handle(
    endpoint: Endpoint,
    request: Request,
    store: Store,
    settings: Settings,
    background: BackgroundTasks,
    frame: UploadFile | None,
    step_id: str | None,
    request_id: str | None,
    session_id: str | None,
) -> CheckOut | WatchOut:
    ctx: dict[str, Any] = {
        "endpoint": f"/{endpoint}",
        "session_id": None,
        "step_idx": None,
        "request_id": None,
    }
    http_status = 500
    claimed: str | None = None
    try:
        rid = parse_uuid(_required(request_id, "request_id"), "request_id")
        request.state.request_id = rid
        ctx["request_id"] = rid
        sid = parse_uuid(session_id, "session_id") if session_id else None
        request.state.session_id = sid
        ctx["session_id"] = sid
        step_uuid = parse_uuid(_required(step_id, "step_id"), "step_id")

        if endpoint == "watch" and sid is not None:
            if sid in _watch_inflight:
                raise ApiError(429, "quota_exhausted", "watch already in flight", True, rid)
            _watch_inflight.add(sid)
            claimed = sid

        raw = await _read_frame(frame)
        if endpoint == "check":
            data = await images.prepare_check_frame(raw)
        else:
            data = await images.prepare_watch_frame(raw)

        step = await load_step(store, step_uuid)
        ctx["step_idx"] = step.idx
        session = await load_session(store, sid) if sid else None
        if session is not None:
            metrics.set_latest_frame(session.id, data, utcnow(), endpoint)

        g = ai.get()
        spec = step_spec(step)
        if endpoint == "check":
            ref = await refcache.get_ref_image(store, step)
            budget = settings.check_budget_s
            call = g.check_frame(data, spec, ref, timeout_s=budget)
        else:
            budget = settings.watch_budget_s
            call = g.watch_frame(data, spec, timeout_s=budget)
        t0 = time.perf_counter()
        result = await _with_budget(call, budget, rid)
        latency_ms = round((time.perf_counter() - t0) * 1000)

        common = {
            "request_id": rid,
            "step_id": step.id,
            "mistake_id": result.mistake_id,
            "headline": result.headline,
            "fix": result.fix,
            "spoken": result.spoken,
            "confidence": result.confidence,
            "latency_ms": latency_ms,
            "model": result.model,
        }
        out: CheckOut | WatchOut
        if endpoint == "check":
            out = CheckOut(verdict=result.verdict, **common)
            ctx["verdict"] = out.verdict
            kind: str | None = f"check_{out.verdict}"
        else:
            out = WatchOut(status=result.status, **common)
            ctx["status"] = out.status
            kind = "watch_warn" if out.status == "warn" else None
        ctx.update(
            mistake_id=out.mistake_id,
            confidence=out.confidence,
            latency_ms=latency_ms,
            model=out.model,
        )

        if session is not None:
            if await request.is_disconnected():
                # Nobody will see this answer: no event, no stored frame, no monitor result.
                ctx["disconnected"] = True
            else:
                at = utcnow()
                body = out.model_dump(mode="json")
                metrics.record(session.id, endpoint, latency_ms, body, at)
                if kind is not None:
                    background.add_task(
                        _persist,
                        store,
                        session_id=session.id,
                        kind=kind,
                        step_id=step.id,
                        request_id=rid,
                        frame=data,
                        body=body,
                        at=at,
                    )
        http_status = 200
        return out
    except asyncio.CancelledError:
        http_status = 499  # client went away (nginx convention); nothing is recorded
        raise
    except Exception as exc:
        http_status, code = status_of(exc)
        ctx["error"] = code
        raise
    finally:
        if claimed is not None:
            _watch_inflight.discard(claimed)
        ctx["http_status"] = http_status
        log_call(ctx)


@router.post("/check", response_model=CheckOut)
async def check(
    request: Request,
    store: StoreDep,
    settings: SettingsDep,
    background: BackgroundTasks,
    frame: Annotated[UploadFile | None, File()] = None,
    step_id: Annotated[str | None, Form()] = None,
    request_id: Annotated[str | None, Form()] = None,
    session_id: Annotated[str | None, Form()] = None,
    captured_at: Annotated[str | None, Form()] = None,
) -> CheckOut | WatchOut:
    # Every field is optional at the framework level and checked in _handle, so that every
    # error response can carry the client's request_id (BE-03.4).
    return await _handle(
        "check", request, store, settings, background, frame, step_id, request_id, session_id
    )


@router.post("/watch", response_model=WatchOut)
async def watch(
    request: Request,
    store: StoreDep,
    settings: SettingsDep,
    background: BackgroundTasks,
    frame: Annotated[UploadFile | None, File()] = None,
    step_id: Annotated[str | None, Form()] = None,
    request_id: Annotated[str | None, Form()] = None,
    session_id: Annotated[str | None, Form()] = None,
    captured_at: Annotated[str | None, Form()] = None,
) -> CheckOut | WatchOut:
    return await _handle(
        "watch", request, store, settings, background, frame, step_id, request_id, session_id
    )
