from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app import metrics
from app.config import get_settings
from app.deps import get_store
from app.errors import not_found
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
from app.store.base import Event, Session, Store
from app.views import event_out, load_session, parse_uuid, step_out

router = APIRouter(tags=["sessions"])

StoreDep = Annotated[Store, Depends(get_store)]

MONITOR_EVENTS = 30


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
    event = await store.append_event(
        Event(
            session_id=session.id,
            kind=body.kind,
            step_id=step_id,
            request_id=request_id,
            payload=body.payload,
        )
    )
    if body.kind == "session_end" and session.finished_at is None:
        await store.update_session(session.id, finished_at=event.created_at)
    return EventCreated(event_id=event.id)


@router.get("/sessions", response_model=SessionList)
async def list_sessions(
    store: StoreDep,
    active: Annotated[bool | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> SessionList:
    items = []
    for s in await store.list_sessions(active=active, limit=limit):
        recipe = await store.get_recipe(s.recipe_id)
        items.append(
            SessionListItem(
                id=s.id,
                recipe_id=s.recipe_id,
                recipe_title=recipe.title if recipe else None,
                client=s.client,
                device_label=s.device_label,
                started_at=s.started_at,
                finished_at=s.finished_at,
            )
        )
    return SessionList(sessions=items)


def summarize(steps_total: int, events: list[Event]) -> SessionSummary:
    # A step "passed first try" when its first check with a verdict is a pass.
    # check_unsure is not a verdict (the model could not judge), so it is skipped here.
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
    session = await load_session(store, session_id)
    recipe = await store.get_recipe(session.recipe_id)
    events = await store.list_events(session.id)
    steps = await store.list_steps(session.recipe_id)

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
        if m.last_frame_path:
            last_frame_url = await store.signed_url(
                "frames", m.last_frame_path, get_settings().signed_url_ttl_s
            )
            last_frame_at = m.last_frame_at
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
        recipe_title=recipe.title if recipe else None,
        current_step=await step_out(store, current) if current else None,
        last_frame_url=last_frame_url,
        last_frame_at=last_frame_at,
        last_result=last_result,
        events=[event_out(e) for e in reversed(events[-MONITOR_EVENTS:])],
        latency=Latency(**metrics.latency(session.id)),
    )
