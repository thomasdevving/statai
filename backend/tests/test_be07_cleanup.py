"""BE-07.5: scripts/cleanup.py and the Store methods it relies on."""

from __future__ import annotations

import importlib.util
import os
import time
from datetime import timedelta
from pathlib import Path

import pytest

from app.deps import get_store
from app.seed import SEED_RECIPE_ID
from app.store.base import Event, Recipe, Session, utcnow

_spec = importlib.util.spec_from_file_location(
    "cleanup_script", Path(__file__).resolve().parents[1] / "scripts" / "cleanup.py"
)
cleanup = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cleanup)


async def _session(store, recipe_id, age_h, with_frame=True):
    s = await store.create_session(
        Session(recipe_id=recipe_id, client="t", started_at=utcnow() - timedelta(hours=age_h))
    )
    await store.append_event(Event(session_id=s.id, kind="step_change"))
    if with_frame:
        await store.put_blob("frames", f"{s.id}/a.jpg", b"jpg", "image/jpeg")
    return s


async def test_store_started_before_and_delete_session():
    store = get_store()
    await store.create_recipe(Recipe(id=SEED_RECIPE_ID, title="seed", status="published"))
    old = await _session(store, SEED_RECIPE_ID, 10)
    new = await _session(store, SEED_RECIPE_ID, 1)
    cutoff = utcnow() - timedelta(hours=6)
    assert [s.id for s in await store.list_sessions(started_before=cutoff)] == [old.id]
    assert await store.delete_session(old.id) is True
    assert await store.delete_session(old.id) is False
    assert await store.get_session(old.id) is None and await store.list_events(old.id) == []
    assert await store.get_session(new.id) is not None


async def test_old_sessions_deleted_with_frames_recent_kept():
    store = get_store()
    await store.create_recipe(Recipe(id=SEED_RECIPE_ID, title="seed", status="published"))
    old = await _session(store, SEED_RECIPE_ID, 7)
    new = await _session(store, SEED_RECIPE_ID, 0.5)
    found = await cleanup.old_sessions(store, 6)
    assert [s.id for s in found] == [old.id]
    for s in found:
        await cleanup.delete_session_fully(store, s)
    assert await store.get_session(old.id) is None
    assert not await store.blob_exists("frames", f"{old.id}/a.jpg")
    assert await store.get_session(new.id) is not None
    assert await store.blob_exists("frames", f"{new.id}/a.jpg")
    assert await store.get_recipe(SEED_RECIPE_ID) is not None  # the recipe itself stays


async def test_failed_recipes_listed_but_never_the_seed():
    store = get_store()
    await store.create_recipe(Recipe(id=SEED_RECIPE_ID, title="seed", status="failed"))
    bad = await store.create_recipe(Recipe(title="bad", status="failed"))
    await store.create_recipe(Recipe(title="fine", status="review"))
    await store.put_blob("videos", f"{bad.id}/source.mp4", b"v", "video/mp4")
    assert [r.id for r in await cleanup.failed_recipes(store)] == [bad.id]
    await cleanup.purge_recipe(store, bad.id)
    assert await store.get_recipe(bad.id) is None
    assert not await store.blob_exists("videos", f"{bad.id}/source.mp4")
    assert await store.get_recipe(SEED_RECIPE_ID) is not None


def _age(path: Path, hours: float) -> None:
    t = time.time() - hours * 3600
    for p in [*path.rglob("*"), path]:
        os.utime(p, (t, t))


async def test_memory_mode_dry_run_then_yes(capsys):
    store = get_store()
    await store.put_blob("frames", "11111111-1111-4111-8111-111111111111/a.jpg", b"x", "image/jpeg")
    await store.put_blob("frames", "22222222-2222-4222-8222-222222222222/a.jpg", b"x", "image/jpeg")
    old = store.data_dir / "frames" / "11111111-1111-4111-8111-111111111111"
    _age(old, 9)

    assert await cleanup.run(6, yes=False) == 0
    out = capsys.readouterr().out
    assert "memory mode" in out and "dry run" in out and "frame folders to delete: 1" in out
    assert old.is_dir()

    assert await cleanup.run(6, yes=True) == 0
    assert not old.exists()
    assert (store.data_dir / "frames" / "22222222-2222-4222-8222-222222222222").is_dir()


async def test_run_on_empty_memory_store_is_harmless(capsys):
    assert await cleanup.run(6, yes=True) == 0
    assert "deleted 0 frame folder(s)" in capsys.readouterr().out


@pytest.mark.parametrize("hours", [0, 6])
async def test_run_with_rows_in_a_supabase_like_store(capsys, hours, monkeypatch):
    """The non-memory branch against MemoryStore rows (the script only uses the Store protocol)."""
    store = get_store()
    await store.create_recipe(Recipe(id=SEED_RECIPE_ID, title="seed", status="published"))
    old = await _session(store, SEED_RECIPE_ID, 10)
    bad = await store.create_recipe(Recipe(title="bad", status="failed"))

    class Wrapper:
        """Not a MemoryStore, so run() takes the row path."""

        def __getattr__(self, name):
            return getattr(store, name)

    monkeypatch.setattr(cleanup, "get_store", lambda: Wrapper())
    assert await cleanup.run(hours, yes=False) == 0
    assert await store.get_session(old.id) is not None and await store.get_recipe(bad.id)
    assert "dry run: nothing deleted" in capsys.readouterr().out

    assert await cleanup.run(hours, yes=True) == 0
    assert await store.get_session(old.id) is None
    assert await store.get_recipe(bad.id) is None
    assert await store.get_recipe(SEED_RECIPE_ID) is not None
