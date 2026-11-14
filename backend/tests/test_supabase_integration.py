"""Opt-in: SupabaseStore against the real project (BE-02.3).

    RUN_SUPABASE_TESTS=1 pytest -q tests/test_supabase_integration.py

Skipped unless RUN_SUPABASE_TESTS=1 and SUPABASE_URL is set (environment or backend/.env).
Uses a throwaway recipe id and removes everything it created.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator

import httpx
import pytest

from app.config import Settings
from app.store.base import Event, Recipe, Session, Step
from app.store.ops import purge_recipe

_settings = Settings()
pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_SUPABASE_TESTS") != "1"
    or not _settings.supabase_url
    or _settings.supabase_service_key is None,
    reason="set RUN_SUPABASE_TESTS=1 and SUPABASE_URL / SUPABASE_SERVICE_KEY",
)

# Smallest thing Storage accepts as video/mp4 (Storage checks the declared type, not the bytes).
TINY_MP4 = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2" + b"\x00\x00\x00\x08free"
TINY_JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 16 + b"\xff\xd9"


@pytest.fixture
async def store_and_recipe() -> AsyncIterator[tuple[object, str]]:
    from app.store.supabase_store import SupabaseStore

    assert _settings.supabase_url and _settings.supabase_service_key
    store = SupabaseStore(_settings.supabase_url, _settings.supabase_service_key.get_secret_value())
    recipe_id = str(uuid.uuid4())
    try:
        yield store, recipe_id
    finally:
        await purge_recipe(store, recipe_id)
        for bucket in ("videos", "media"):
            await store.delete_prefix(bucket, recipe_id)


async def test_crud_round_trip(store_and_recipe):
    store, rid = store_and_recipe
    created = await store.create_recipe(
        Recipe(id=rid, title="it-test", status="uploading", step_marks_s=[1.5, 3.0])
    )
    assert created.id == rid and created.step_marks_s == [1.5, 3.0]
    assert (await store.get_recipe(rid)).title == "it-test"
    assert await store.get_recipe("not-a-uuid") is None
    assert any(r.id == rid for r in await store.list_recipes(status="uploading"))

    updated = await store.update_recipe(rid, status="review", transcript="hello")
    assert updated.status == "review" and updated.transcript == "hello"
    assert await store.update_recipe(str(uuid.uuid4()), status="review") is None

    steps = [
        Step(
            recipe_id=rid,
            idx=i,
            title=f"s{i}",
            key_line="k",
            instruction="do",
            timestamp_s=i * 1.25,
            success_criteria=["a", "b"],
            watch_fors=[{"id": "w", "mistake": "m", "headline": "h", "fix": "f", "spoken": "s"}],
            timer_s=30 if i == 2 else None,
        )
        for i in (2, 1)
    ]
    stored = await store.replace_steps(rid, steps)
    assert [s.idx for s in stored] == [1, 2]
    assert stored[0].timestamp_s == 1.25 and stored[1].timer_s == 30
    assert stored[1].watch_fors[0]["id"] == "w"
    with pytest.raises(ValueError):
        await store.replace_steps(rid, [steps[0], steps[0]])

    step = await store.update_step(stored[0].id, title="renamed", ref_image_path="x/ref.jpg")
    assert step.title == "renamed" and (await store.get_step(step.id)).ref_image_path == "x/ref.jpg"

    sess = await store.create_session(Session(recipe_id=rid, client="web-sim", device_label="it"))
    assert (await store.get_session(sess.id)).client == "web-sim"
    assert any(s.id == sess.id for s in await store.list_sessions(active=True, recipe_id=rid))

    e1 = await store.append_event(
        Event(session_id=sess.id, kind="step_change", step_id=stored[0].id, payload={"a": 1})
    )
    # Unknown step id: the event is kept with step_id = null.
    e2 = await store.append_event(
        Event(session_id=sess.id, kind="check_pass", step_id=str(uuid.uuid4()))
    )
    assert e2.step_id is None
    with pytest.raises(KeyError):
        await store.append_event(Event(session_id=str(uuid.uuid4()), kind="session_end"))
    events = await store.list_events(sess.id)
    assert [e.id for e in events] == [e1.id, e2.id] and events[0].payload == {"a": 1}

    # Replacing steps nulls event.step_id ("on delete set null").
    await store.replace_steps(rid, steps)
    assert (await store.list_events(sess.id))[0].step_id is None

    finished = await store.update_session(sess.id, finished_at=e2.created_at)
    assert finished.finished_at is not None
    assert any(s.id == sess.id for s in await store.list_sessions(active=False, recipe_id=rid))

    # Cascade: deleting the recipe removes steps, sessions and events.
    await store.put_blob("frames", f"{sess.id}/{uuid.uuid4()}.jpg", TINY_JPEG, "image/jpeg")
    assert await purge_recipe(store, rid) is not None
    assert await store.get_recipe(rid) is None
    assert await store.list_steps(rid) == []
    assert await store.get_session(sess.id) is None
    assert await store.list_events(sess.id) == []
    assert not await store.blob_exists("frames", f"{sess.id}/x.jpg")
    assert await store.delete_recipe(rid) is False


async def test_blob_round_trip(store_and_recipe):
    store, rid = store_and_recipe
    path = f"{rid}/steps/1/ref.jpg"
    assert not await store.blob_exists("media", path)
    assert await store.get_blob("media", path) is None
    assert await store.signed_url("media", path, 600) is None  # missing object: no 500

    await store.put_blob("media", path, TINY_JPEG, "image/jpeg")
    await store.put_blob("media", path, TINY_JPEG, "image/jpeg")  # upsert
    assert await store.blob_exists("media", path)
    assert await store.get_blob("media", path) == TINY_JPEG

    url = await store.signed_url("media", path, 600)
    assert url == await store.signed_url("media", path, 600)  # cached
    r = httpx.get(url, timeout=30)
    assert r.status_code == 200 and r.content == TINY_JPEG

    await store.put_blob("media", f"{rid}/steps/2/ref.jpg", TINY_JPEG, "image/jpeg")
    await store.delete_blob("media", path)
    assert not await store.blob_exists("media", path)
    await store.delete_prefix("media", rid)
    assert not await store.blob_exists("media", f"{rid}/steps/2/ref.jpg")


async def test_signed_upload_round_trip(store_and_recipe):
    store, rid = store_and_recipe
    path = f"{rid}/source.mp4"
    up = await store.signed_upload("videos", path)
    assert up["upload_token"] and up["upload_url"].startswith(_settings.supabase_url)
    assert up["resumable_endpoint"].endswith(".storage.supabase.co/storage/v1/upload/resumable")

    r = httpx.put(
        up["upload_url"], content=TINY_MP4, headers={"Content-Type": "video/mp4"}, timeout=60
    )
    assert r.status_code == 200, r.status_code
    assert await store.blob_exists("videos", path)

    # The bucket itself refuses other types.
    other = await store.signed_upload("videos", f"{rid}/other.mp4")
    r = httpx.put(
        other["upload_url"], content=b"text", headers={"Content-Type": "text/plain"}, timeout=60
    )
    assert r.status_code >= 400


async def test_started_before_and_delete_session(store_and_recipe):
    from datetime import timedelta

    from app.store.base import utcnow

    store, rid = store_and_recipe
    await store.create_recipe(Recipe(id=rid, title="it-cleanup", status="review"))
    old = await store.create_session(
        Session(recipe_id=rid, client="web-sim", started_at=utcnow() - timedelta(hours=9))
    )
    new = await store.create_session(Session(recipe_id=rid, client="web-sim"))
    await store.append_event(Event(session_id=old.id, kind="step_change"))
    found = await store.list_sessions(recipe_id=rid, started_before=utcnow() - timedelta(hours=6))
    assert [s.id for s in found] == [old.id]
    assert await store.delete_session(old.id) is True
    assert await store.delete_session(old.id) is False
    assert await store.list_events(old.id) == []
    assert await store.get_session(new.id) is not None
