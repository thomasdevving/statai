from __future__ import annotations

from datetime import timedelta

import pytest

from app.store.base import Event, Recipe, Session, Step, utcnow
from app.store.memory import MemoryStore
from app.store.paths import BadPath


@pytest.fixture
def store(tmp_path) -> MemoryStore:
    return MemoryStore(tmp_path / "data", "http://test.local")


def _step(recipe_id: str, idx: int) -> Step:
    return Step(
        recipe_id=recipe_id,
        idx=idx,
        title=f"S{idx}",
        key_line="k",
        instruction="i",
        timestamp_s=float(idx),
    )


async def test_recipe_crud(store):
    r = await store.create_recipe(Recipe(title="A", status="uploading"))
    assert (await store.get_recipe(r.id)).title == "A"
    await store.create_recipe(Recipe(title="B", status="published"))
    assert len(await store.list_recipes()) == 2
    assert [x.title for x in await store.list_recipes("published")] == ["B"]
    u = await store.update_recipe(r.id, title="A2", status="processing")
    assert (u.title, u.status) == ("A2", "processing")
    assert await store.update_recipe("missing", title="x") is None
    # returned objects are copies
    u.title = "mutated"
    assert (await store.get_recipe(r.id)).title == "A2"


async def test_steps_ordered_and_replaced(store):
    r = await store.create_recipe(Recipe(title="A", status="review"))
    await store.replace_steps(r.id, [_step(r.id, 2), _step(r.id, 1)])
    steps = await store.list_steps(r.id)
    assert [s.idx for s in steps] == [1, 2]
    s1 = await store.update_step(steps[0].id, title="New")
    assert s1.title == "New"
    assert (await store.get_step(steps[0].id)).title == "New"
    await store.replace_steps(r.id, [_step(r.id, 1)])
    assert len(await store.list_steps(r.id)) == 1
    with pytest.raises(ValueError):
        await store.replace_steps(r.id, [_step(r.id, 1), _step(r.id, 1)])


async def test_sessions_and_events(store):
    r = await store.create_recipe(Recipe(title="A", status="published"))
    s_old = await store.create_session(
        Session(recipe_id=r.id, client="ios", started_at=utcnow() - timedelta(minutes=5))
    )
    s_new = await store.create_session(Session(recipe_id=r.id, client="web-sim"))
    await store.update_session(s_old.id, finished_at=utcnow())
    assert [s.id for s in await store.list_sessions()] == [s_new.id, s_old.id]
    assert [s.id for s in await store.list_sessions(active=True)] == [s_new.id]
    assert len(await store.list_sessions(limit=1)) == 1
    await store.append_event(Event(session_id=s_new.id, kind="step_change", payload={"to_idx": 2}))
    await store.append_event(Event(session_id=s_new.id, kind="question"))
    assert [e.kind for e in await store.list_events(s_new.id)] == ["step_change", "question"]
    with pytest.raises(KeyError):
        await store.append_event(Event(session_id="missing", kind="question"))


async def test_cascade_delete(store):
    r = await store.create_recipe(Recipe(title="A", status="published"))
    other = await store.create_recipe(Recipe(title="B", status="published"))
    await store.replace_steps(r.id, [_step(r.id, 1)])
    await store.replace_steps(other.id, [_step(other.id, 1)])
    s = await store.create_session(Session(recipe_id=r.id, client="ios"))
    await store.append_event(Event(session_id=s.id, kind="question"))
    assert await store.delete_recipe(r.id) is True
    assert await store.get_recipe(r.id) is None
    assert await store.list_steps(r.id) == []
    assert await store.get_session(s.id) is None
    assert await store.list_events(s.id) == []
    assert len(await store.list_steps(other.id)) == 1
    assert await store.delete_recipe(r.id) is False


async def test_blob_round_trip(store):
    path = "r1/steps/1/ref.jpg"
    assert await store.blob_exists("media", path) is False
    assert await store.get_blob("media", path) is None
    await store.put_blob("media", path, b"\xff\xd8data", "image/jpeg")
    assert await store.blob_exists("media", path) is True
    assert await store.get_blob("media", path) == b"\xff\xd8data"
    assert (store.data_dir / "media" / path).is_file()
    url = await store.signed_url("media", path, 60)
    assert url == "http://test.local/local-files/media/r1/steps/1/ref.jpg"
    await store.delete_blob("media", path)
    assert await store.blob_exists("media", path) is False


async def test_delete_prefix(store):
    await store.put_blob("media", "r1/steps/1/ref.jpg", b"a", "image/jpeg")
    await store.put_blob("media", "r1/steps/2/ref.jpg", b"b", "image/jpeg")
    await store.put_blob("media", "r2/steps/1/ref.jpg", b"c", "image/jpeg")
    await store.delete_prefix("media", "r1")
    assert not await store.blob_exists("media", "r1/steps/1/ref.jpg")
    assert await store.blob_exists("media", "r2/steps/1/ref.jpg")
    await store.delete_prefix("media", "does-not-exist")  # no error


@pytest.mark.parametrize(
    "bucket,path",
    [
        ("media", "../secret"),
        ("media", "a/../../b"),
        ("media", "/etc/passwd"),
        ("media", "a//b"),
        ("media", ""),
        ("other", "a.jpg"),
        ("media", "a\\..\\b"),
        ("media", ".hidden"),
    ],
)
async def test_bad_paths_rejected(store, bucket, path):
    with pytest.raises(BadPath):
        await store.put_blob(bucket, path, b"x", "image/jpeg")


async def test_signed_upload_token_single_use(store):
    up = await store.signed_upload("videos", "r1/source.mp4")
    assert up["resumable_endpoint"] is None
    assert up["upload_url"].startswith("http://test.local/local-upload/videos/r1/source.mp4?token=")
    assert up["expires_at"] > utcnow() + timedelta(minutes=119)
    tok = up["upload_token"]
    assert store.consume_upload_token("videos", "r1/source.mp4", "wrong") is False
    assert store.consume_upload_token("videos", "r2/source.mp4", tok) is False
    assert store.consume_upload_token("videos", "r1/source.mp4", tok) is True
    assert store.consume_upload_token("videos", "r1/source.mp4", tok) is False
