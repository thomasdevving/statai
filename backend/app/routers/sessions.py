from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app import metrics
from app.config import get_settings
from app.deps import get_store
from app.errors import not_found
from app.routers.latest_frame import latest_frame_url
from app.schemas import (
    EventCreate,
    EventCreated,
    LastResult,
    Latency,
    Monitor,
    MonitorSession,
    SessionCreate,
    SessionCreated,
    SessionDetail,
    SessionList,
    SessionListItem,
    SessionSummary,
)
from app.store.base import Event, Session, Step, Store, utcnow
from app.views import event_out, load_session, parse_uuid, step_out

router = APIRouter(tags=["sessions"])

StoreDep = Annotated[Store, Depends(get_store)]

MONITOR_EVENTS = 30
ACTIVE_WINDOW = timedelta(hours=3)
MONITOR_CACHE_S = 3.0

# session_end is idempotent: serialise it so two concurrent calls cannot both append.
_end_lock = asyncio.Lock()


@dataclass
class _MonitorCtx:
    session: Session
    recipe_title: str | None
    steps: list[Step]
    loaded_at: float


# session_id -> session, recipe title and steps, reused for MONITOR_CACHE_S (monitor polls 1/s).
_monitor_cache: dict[str, _MonitorCtx] = {}
# Bumped on every eviction, so a monitor load that started before a session_end or delete
# never writes its (now stale) result back into the cache.
_generation = 0


def reset() -> None:
    _monitor_cache.clear()


def evict(session_id: str) -> None:
    """Drop cached monitor state for a session (ended or deleted)."""
    global _generation
    _generation += 1
    _monitor_cache.pop(session_id, None)


async def _monitor_ctx(store: Store, session_id: str) -> _MonitorCtx:
    now = time.monotonic()
    sid = parse_uuid(session_id, "session_id")
    hit = _monitor_cache.get(sid)
    if hit is not None and now - hit.loaded_at < MONITOR_CACHE_S:
        return hit
    gen = _generation
    session = await load_session(store, sid)
    recipe = await store.get_recipe(session.recipe_id)
    steps = await store.list_steps(session.recipe_id)
    ctx = _MonitorCtx(session, recipe.title if recipe else None, steps, now)
    if gen != _generation:
        return ctx  # something was evicted while loading: answer, but do not cache
    if len(_monitor_cache) > 256:
        for k in [k for k, v in _monitor_cache.items() if now - v.loaded_at >= MONITOR_CACHE_S]:
            del _monitor_cache[k]
    _monitor_cache[sid] = ctx
    return ctx


@router.post("/sessions", status_code=201, response_model=SessionCreated)
async def create_session(body: SessionCreate, store: StoreDep) -> SessionCreated:
    recipe = await store.get_recipe(parse_uuid(body.recipe_id, "recipe_id"))
    if recipe is None:
        raise not_found("recipe")
    session = await store.create_session(
        Session(recipe_id=recipe.id, client=body.client, device_label=body.device_label)
    )
    return SessionCreated(session_id=session.id, started_at=session.started_at)


@router.post("/sessions/{session_id}/events", status_code=201, response_model=EventCreated)
async def post_event(session_id: str, body: EventCreate, store: StoreDep) -> EventCreated:
    session = await load_session(store, session_id)
    step_id = parse_uuid(body.step_id, "step_id") if body.step_id else None
    request_id = parse_uuid(body.request_id, "request_id") if body.request_id else None
    event = Event(
        session_id=session.id,
        kind=body.kind,
        step_id=step_id,
        request_id=request_id,
        payload=body.payload,
    )
    if body.kind != "session_end":
        return EventCreated(event_id=(await store.append_event(event)).id)

    # Idempotent: a repeated session_end returns the first one's id and changes nothing.
    # Keyed on the existing event, not on finished_at, so a retry after a failed
    # update_session repairs finished_at instead of appending a second session_end.
    async with _end_lock:
        session = await load_session(store, session.id)
        stored = next(
            (e for e in await store.list_events(session.id) if e.kind == "session_end"), None
        )
        if stored is None:
            stored = await store.append_event(event)
        if session.finished_at is None:
            evict(session.id)
            await store.update_session(session.id, finished_at=stored.created_at)
    evict(session.id)
    return EventCreated(event_id=stored.id)


@router.get("/sessions", response_model=SessionList)
async def list_sessions(
    store: StoreDep,
    active: Annotated[bool | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> SessionList:
    rows = await store.list_sessions(active=active, limit=limit)
    if active is True:
        # "active" = not finished and started within the last 3 h. Rows are newest first, so
        # filtering after the limit still yields the newest `limit` matching sessions.
        cutoff = utcnow() - ACTIVE_WINDOW
        rows = [s for s in rows if s.started_at >= cutoff]
    titles: dict[str, str | None] = {}
    items = []
    for s in rows:
        if s.recipe_id not in titles:
            recipe = await store.get_recipe(s.recipe_id)
            titles[s.recipe_id] = recipe.title if recipe else None
        items.append(
            SessionListItem(
                id=s.id,
                recipe_id=s.recipe_id,
                recipe_title=titles[s.recipe_id],
                client=s.client,
                device_label=s.device_label,
                started_at=s.started_at,
                finished_at=s.finished_at,
            )
        )
    return SessionList(sessions=items)


def summarize(steps_total: int, events: list[Event]) -> SessionSummary:
    """Done-screen summary (BE-05.3).

    - steps_passed_first_try: steps whose first check event is check_pass. check_unsure is not a
      verdict (the model could not judge) and affects none of the counts, so it is skipped when
      finding the first check. A step with no check does not count.
    - fixes_caught / warnings / questions: counts of check_fix / watch_warn / question.
    """
    first_verdict: dict[str, str] = {}
    for e in events:
        if e.kind in ("check_pass", "check_fix") and e.step_id and e.step_id not in first_verdict:
            first_verdict[e.step_id] = e.kind
    return SessionSummary(
        steps_total=steps_total,
        steps_passed_first_try=sum(1 for k in first_verdict.values() if k == "check_pass"),
        fixes_caught=sum(1 for e in events if e.kind == "check_fix"),
        warnings=sum(1 for e in events if e.kind == "watch_warn"),
        questions=sum(1 for e in events if e.kind == "question"),
    )


@router.get("/sessions/{session_id}", response_model=SessionDetail)
async def get_session(session_id: str, store: StoreDep) -> SessionDetail:
    session = await load_session(store, session_id)
    events = await store.list_events(session.id)
    steps = await store.list_steps(session.recipe_id)
    return SessionDetail(
        id=session.id,
        recipe_id=session.recipe_id,
        client=session.client,
        device_label=session.device_label,
        started_at=session.started_at,
        finished_at=session.finished_at,
        events=[event_out(e) for e in events],
        summary=summarize(len(steps), events),
    )


@router.get("/sessions/{session_id}/monitor", response_model=Monitor)
async def monitor(session_id: str, store: StoreDep) -> Monitor:
    ctx = await _monitor_ctx(store, session_id)
    session, steps = ctx.session, ctx.steps
    events = await store.list_events(session.id)  # the one storage round trip per call

    current_idx = 1
    for e in reversed(events):
        if e.kind == "step_change":
            to_idx = e.payload.get("to_idx")
            if isinstance(to_idx, int) and not isinstance(to_idx, bool):
                current_idx = to_idx
            break
    current = next((s for s in steps if s.idx == current_idx), None)
    if current is None and steps:
        current = steps[0]

    m = metrics.get(session.id)
    last_frame_url = None
    last_frame_at = None
    last_result = None
    if m is not None:
        if m.latest_frame is not None:
            last_frame_url = latest_frame_url(session.id, get_settings().public_base_url)
            last_frame_at = m.latest_frame.at
        if m.last_result:
            last_result = LastResult(**m.last_result)

    return Monitor(
        session=MonitorSession(
            id=session.id,
            client=session.client,
            device_label=session.device_label,
            started_at=session.started_at,
            finished_at=session.finished_at,
        ),
        recipe_title=ctx.recipe_title,
        current_step=await step_out(store, current) if current else None,
        last_frame_url=last_frame_url,
        last_frame_at=last_frame_at,
        last_result=last_result,
        events=[event_out(e) for e in reversed(events[-MONITOR_EVENTS:])],
        latency=Latency(**metrics.latency(session.id)),
    )
