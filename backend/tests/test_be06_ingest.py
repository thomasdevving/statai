"""BE-06.2 to BE-06.4: upload validation, the ingestion job, review-time endpoints."""

from __future__ import annotations

import asyncio
import io
import tempfile
import time
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
from PIL import Image

from app import refcache
from app.config import get_settings
from app.deps import get_store
from app.jobs import ingest
from app.media import videocache
from app.media.ffmpeg import FfmpegError
from app.seed import SEED_RECIPE_ID
from app.store.base import Recipe, utcnow

from .conftest import KEY, requires_ai, requires_ffmpeg
from .helpers import CHECKED_STEP

pytestmark = [requires_ai, requires_ffmpeg]


# --------------------------------------------------------------------------- helpers
def _create(client, auth, title="Sandwich", marks=None) -> dict:
    r = client.post(
        "/recipes",
        headers=auth,
        json={"title": title, "step_marks_s": marks or [], "consent": True},
    )
    assert r.status_code == 201
    return r.json()


def _upload(client, created, data: bytes) -> None:
    r = client.put(created["upload_url"], content=data, headers={"Content-Type": "video/mp4"})
    assert r.status_code == 200


def _wait(client, auth, rid, timeout=20.0) -> dict:
    deadline = time.monotonic() + timeout
    body: dict = {}
    while time.monotonic() < deadline:
        body = client.get(f"/recipes/{rid}", headers=auth).json()
        if body["status"] in ("review", "failed", "published"):
            return body
        time.sleep(0.05)
    raise AssertionError(f"still {body.get('status')} after {timeout} s")


def ingest_video(client, auth, data: bytes, title="Sandwich", marks=None) -> tuple[str, dict]:
    created = _create(client, auth, title, marks)
    rid = created["recipe_id"]
    _upload(client, created, data)
    assert client.post(f"/recipes/{rid}/process", headers=auth).status_code == 202
    return rid, _wait(client, auth, rid)


def _image(client, url) -> Image.Image:
    r = client.get(url)
    assert r.status_code == 200
    return Image.open(io.BytesIO(r.content))


def _draft(windows: list[tuple[float, tuple[float, float] | None]]):
    """A RecipeDraft from the fixture: one step per (timestamp_s, clip window)."""
    from ghostchef_ai import fake

    base = fake.load_fixture()
    steps = []
    for i, (ts, win) in enumerate(windows):
        steps.append(
            base.steps[i].model_copy(
                update={
                    "idx": i + 1,
                    "timestamp_s": ts,
                    "clip_start_s": win[0] if win else None,
                    "clip_end_s": win[1] if win else None,
                }
            )
        )
    return base.model_copy(update={"steps": steps})


def _patch_extract(monkeypatch, fn) -> None:
    import ghostchef_ai

    monkeypatch.setattr(ghostchef_ai, "extract_recipe", fn)


def _spy_extract(monkeypatch, draft=None) -> list[dict]:
    from ghostchef_ai import fake

    calls: list[dict] = []

    async def spy(video_path, *, title_hint=None, step_marks_s=None):
        calls.append({"title_hint": title_hint, "step_marks_s": step_marks_s})
        return draft or fake.load_fixture()

    _patch_extract(monkeypatch, spy)
    return calls


# --------------------------------------------------------------------------- BE-06.2
def test_happy_path_real_stills(client, auth, testsrc_bytes):
    rid, body = ingest_video(client, auth, testsrc_bytes)
    assert body["status"] == "review", body
    assert body["error"] is None
    assert len(body["steps"]) == 6
    for step in body["steps"]:
        assert step["timestamp_s"] <= 4.9
        img = _image(client, step["ref_image_url"])
        assert img.format == "JPEG" and img.size == (1280, 720)
    assert body["video_url"]
    assert client.post(f"/recipes/{rid}/publish", headers=auth).status_code == 200


def test_process_before_upload_409(client, auth):
    created = _create(client, auth)
    r = client.post(f"/recipes/{created['recipe_id']}/process", headers=auth)
    assert r.status_code == 409 and r.json()["error"]["code"] == "upload_missing"


def test_size_limit(client, auth, testsrc_bytes, monkeypatch):
    calls = _spy_extract(monkeypatch)
    created = _create(client, auth)
    rid = created["recipe_id"]
    _upload(client, created, testsrc_bytes + b"\0" * (1_300_000))
    monkeypatch.setenv("MAX_VIDEO_MB", "1")
    get_settings.cache_clear()
    assert client.post(f"/recipes/{rid}/process", headers=auth).status_code == 202
    body = _wait(client, auth, rid)
    assert body["status"] == "failed"
    assert body["error"] == "video larger than 1 MB"
    assert calls == []


def test_non_video_upload_is_not_a_readable_mp4(client, auth, monkeypatch):
    calls = _spy_extract(monkeypatch)
    created = _create(client, auth)
    _upload(client, created, b"definitely not an mp4 file\n" * 400)
    rid = created["recipe_id"]
    assert client.post(f"/recipes/{rid}/process", headers=auth).status_code == 202
    body = _wait(client, auth, rid)
    assert (body["status"], body["error"]) == ("failed", "not a readable MP4")
    assert calls == []


def test_upload_never_completed_after_two_hours_listing(client, auth, monkeypatch):
    created = _create(client, auth)
    rid = created["recipe_id"]
    real = utcnow
    monkeypatch.setattr("app.views.utcnow", lambda: real() + timedelta(hours=3))
    items = client.get("/recipes?status=failed", headers=auth).json()["recipes"]
    assert rid in [i["id"] for i in items]
    monkeypatch.undo()
    detail = client.get(f"/recipes/{rid}", headers=auth).json()
    assert (detail["status"], detail["error"]) == ("failed", "upload never completed")


def test_startup_sweep(client, auth):
    store = get_store()

    async def go():
        old = await store.create_recipe(
            Recipe(title="old", status="processing", created_at=utcnow() - timedelta(minutes=20))
        )
        fresh = await store.create_recipe(
            Recipe(title="fresh", status="processing", created_at=utcnow() - timedelta(minutes=5))
        )
        uploading = await store.create_recipe(Recipe(title="up", status="uploading"))
        await ingest.startup_sweep(store)
        assert (await store.get_recipe(old.id)).status == "failed"
        assert (await store.get_recipe(old.id)).error == "interrupted by a restart; upload again"
        assert (await store.get_recipe(fresh.id)).status == "processing"
        assert (await store.get_recipe(uploading.id)).status == "uploading"
        await ingest.startup_sweep(store, now=utcnow() + timedelta(hours=3))
        failed = await store.get_recipe(uploading.id)
        assert (failed.status, failed.error) == ("failed", "upload never completed")
        assert (await store.get_recipe(SEED_RECIPE_ID)).status == "published"

    asyncio.run(go())


# --------------------------------------------------------------------------- the job
@pytest.mark.parametrize(
    ("exc_name", "message"),
    [
        ("AIUnavailable", "Gemini could not process the video"),
        ("AITimeout", "Gemini took too long to read the video; try again"),
        ("AIQuotaError", "Gemini quota reached; try again in a few minutes"),
        ("AIInvalidOutput", "Gemini returned an unusable recipe; try again"),
    ],
)
def test_failing_extract_recipe_is_readable_and_leaks_nothing(
    client, auth, testsrc_bytes, monkeypatch, exc_name, message
):
    import ghostchef_ai

    async def boom(*a, **kw):
        raise getattr(ghostchef_ai, exc_name)("SECRET api key in /tmp/x")

    _patch_extract(monkeypatch, boom)
    rid, body = ingest_video(client, auth, testsrc_bytes)
    assert (body["status"], body["error"]) == ("failed", message)
    assert "SECRET" not in client.get(f"/recipes/{rid}", headers=auth).text


def test_unexpected_exception_is_generic(client, auth, testsrc_bytes, monkeypatch):
    async def boom(*a, **kw):
        raise RuntimeError("SECRET /home/x/.env")

    _patch_extract(monkeypatch, boom)
    _, body = ingest_video(client, auth, testsrc_bytes)
    assert (body["status"], body["error"]) == ("failed", "processing failed")


def test_no_steps_fails(client, auth, testsrc_bytes, monkeypatch):
    _spy_extract(monkeypatch, _draft([]))
    _, body = ingest_video(client, auth, testsrc_bytes)
    assert (body["status"], body["error"]) == ("failed", "no steps found in the video")


def test_clamping_and_marks(client, auth, testsrc_bytes, monkeypatch):
    draft = _draft([(0.0, (0.5, 2.5)), (99.0, (3.0, 3.5)), (4.0, (4.0, 9.0))])
    calls = _spy_extract(monkeypatch, draft)
    rid, body = ingest_video(client, auth, testsrc_bytes, marks=[1, 99])
    assert body["status"] == "review", body
    assert calls[0]["step_marks_s"] == [1.0]
    assert calls[0]["title_hint"] == "Sandwich"
    s1, s2, s3 = body["steps"]
    assert (s1["clip_start_s"], s1["clip_end_s"]) == (0.5, 2.5) and s1["clip_url"]
    assert (s2["clip_start_s"], s2["clip_end_s"]) == (None, None) and s2["clip_url"] is None
    assert s3["clip_start_s"] == 4.0 and 4.9 <= s3["clip_end_s"] <= 5.1 and s3["clip_url"]
    assert s2["timestamp_s"] <= 4.9
    clip = client.get(s1["clip_url"])
    assert clip.status_code == 200 and clip.headers["content-type"] == "video/mp4"
    assert b"ftyp" in clip.content[:64]


def test_clip_window_capped_at_six_seconds(client, auth, testsrc_long_mp4, monkeypatch):
    _spy_extract(monkeypatch, _draft([(1.0, (0.0, 8.0))]))
    _, body = ingest_video(client, auth, testsrc_long_mp4.read_bytes())
    step = body["steps"][0]
    assert (step["clip_start_s"], step["clip_end_s"]) == (0.0, 6.0)


def test_failing_still_leaves_step_without_reference(client, auth, testsrc_bytes, monkeypatch):
    real = ingest.extract_still
    calls = 0

    async def flaky(path, at_s, out_path, **kw):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise FfmpegError("boom")
        await real(path, at_s, out_path, **kw)

    monkeypatch.setattr(ingest, "extract_still", flaky)
    rid, body = ingest_video(client, auth, testsrc_bytes)
    assert body["status"] == "review"
    assert [s["ref_image_url"] is None for s in body["steps"]] == [
        False, True, False, False, False, False,
    ]  # fmt: skip
    r = client.post(f"/recipes/{rid}/publish", headers=auth)
    assert r.status_code == 409 and "[2]" in r.json()["error"]["message"]


def test_failing_clip_keeps_the_still(client, auth, testsrc_bytes, monkeypatch):
    async def boom(*a, **kw):
        raise FfmpegError("boom")

    monkeypatch.setattr(ingest, "extract_clip", boom)
    _spy_extract(monkeypatch, _draft([(1.0, (0.0, 3.0)), (2.0, None)]))
    _, body = ingest_video(client, auth, testsrc_bytes)
    assert body["status"] == "review"
    assert all(s["ref_image_url"] and s["clip_url"] is None for s in body["steps"])


@pytest.mark.parametrize("fail", [False, True])
def test_temp_dir_is_cleaned(client, auth, testsrc_bytes, monkeypatch, tmp_path, fail):
    tmp = tmp_path / "tmp"
    tmp.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(tmp))
    if fail:

        async def boom(*a, **kw):
            raise RuntimeError("x")

        _patch_extract(monkeypatch, boom)
    _, body = ingest_video(client, auth, testsrc_bytes)
    assert body["status"] == ("failed" if fail else "review")
    assert [p for p in tmp.iterdir() if p.name.startswith("ghostchef-ingest-")] == []


async def test_only_one_ingestion_at_a_time(app, testsrc_bytes, monkeypatch):
    from ghostchef_ai import fake

    active = peak = 0
    release = asyncio.Event()

    async def gated(video_path, *, title_hint=None, step_marks_s=None):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await release.wait()
        active -= 1
        return fake.load_fixture()

    _patch_extract(monkeypatch, gated)
    h = {"X-Demo-Key": KEY}
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://t"
        ) as c:
            ids = []
            for _ in range(2):
                created = (
                    await c.post("/recipes", headers=h, json={"title": "S", "consent": True})
                ).json()
                up = await c.put(
                    created["upload_url"].replace("http://t", ""), content=testsrc_bytes
                )
                assert up.status_code == 200
                assert (
                    await c.post(f"/recipes/{created['recipe_id']}/process", headers=h)
                ).status_code == 202
                ids.append(created["recipe_id"])
            await asyncio.sleep(1.0)
            assert peak == 1 and active == 1
            statuses = [(await c.get(f"/recipes/{i}", headers=h)).json()["status"] for i in ids]
            assert statuses == ["processing", "processing"]
            release.set()
            await ingest.wait_all()
            statuses = [(await c.get(f"/recipes/{i}", headers=h)).json()["status"] for i in ids]
            assert statuses == ["review", "review"]
            assert peak == 1


async def test_delete_mid_job_leaves_no_media(app, testsrc_bytes, monkeypatch):
    real = ingest.extract_still
    reached = asyncio.Event()
    release = asyncio.Event()

    async def gated(path, at_s, out_path, **kw):
        reached.set()
        await release.wait()
        await real(path, at_s, out_path, **kw)

    monkeypatch.setattr(ingest, "extract_still", gated)
    h = {"X-Demo-Key": KEY}
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://t"
        ) as c:
            created = (
                await c.post("/recipes", headers=h, json={"title": "S", "consent": True})
            ).json()
            rid = created["recipe_id"]
            await c.put(created["upload_url"].replace("http://t", ""), content=testsrc_bytes)
            await c.post(f"/recipes/{rid}/process", headers=h)
            await asyncio.wait_for(reached.wait(), 20)
            assert (await c.delete(f"/recipes/{rid}", headers=h)).status_code == 204
            release.set()
            await ingest.wait_all()
            assert (await c.get(f"/recipes/{rid}", headers=h)).status_code == 404
    data = get_settings().data_path
    assert not (data / "media" / rid).exists()
    assert not (data / "videos" / rid).exists()


# --------------------------------------------------------------------------- Supabase download
def _supabase_store(handler):
    from types import SimpleNamespace

    from app.store.supabase_store import SupabaseStore

    class Bucket:
        def create_signed_url(self, path, ttl):
            return {"signedURL": "https://abc.supabase.co/storage/v1/object/sign/videos/x?token=t"}

    client = SimpleNamespace(storage=SimpleNamespace(from_=lambda name: Bucket()))
    store = SupabaseStore("https://abc.supabase.co", "sb_secret_x", client=client)
    store._http = httpx.Client(transport=httpx.MockTransport(handler))
    return store


async def test_supabase_download_writes_file(tmp_path):
    store = _supabase_store(lambda req: httpx.Response(200, content=b"x" * 3000))
    dest = tmp_path / "v.mp4"
    assert await store.download_to_file("videos", "r/source.mp4", dest, 10_000) is True
    assert dest.stat().st_size == 3000


async def test_supabase_download_over_limit_by_content_length(tmp_path):
    from app.store.base import BlobTooLarge

    store = _supabase_store(lambda req: httpx.Response(200, content=b"x" * 3000))
    dest = tmp_path / "v.mp4"
    with pytest.raises(BlobTooLarge):
        await store.download_to_file("videos", "r/source.mp4", dest, 1000)
    assert not dest.exists()


async def test_supabase_download_over_limit_chunked_leaves_no_partial(tmp_path):
    from app.store.base import BlobTooLarge

    def chunks():
        for _ in range(6):
            yield b"x" * 500

    store = _supabase_store(lambda req: httpx.Response(200, content=chunks()))
    dest = tmp_path / "v.mp4"
    with pytest.raises(BlobTooLarge):
        await store.download_to_file("videos", "r/source.mp4", dest, 1200)
    assert not dest.exists()


async def test_supabase_download_missing_is_false(tmp_path):
    store = _supabase_store(lambda req: httpx.Response(404, json={"error": "nope"}))
    dest = tmp_path / "v.mp4"
    assert await store.download_to_file("videos", "r/source.mp4", dest, 1000) is False
    assert not dest.exists()


async def test_supabase_download_server_error_maps_to_internal(tmp_path):
    from app.errors import ApiError

    store = _supabase_store(lambda req: httpx.Response(500))
    with pytest.raises(ApiError) as exc:
        await store.download_to_file("videos", "r/source.mp4", tmp_path / "v.mp4", 1000)
    assert exc.value.status == 500 and not (tmp_path / "v.mp4").exists()


# --------------------------------------------------------------------------- review endpoints
def _ref_bytes(rid_step) -> bytes:
    data = asyncio.run(get_store().get_blob("media", rid_step.ref_image_path))
    assert data
    return data


def test_patch_timestamp_reextracts_the_still(client, auth, testsrc_bytes):
    rid, body = ingest_video(client, auth, testsrc_bytes)
    store = get_store()
    step = body["steps"][0]
    before = _ref_bytes(asyncio.run(store.get_step(step["id"])))
    cached_before = asyncio.run(
        refcache.get_ref_image(store, asyncio.run(store.get_step(step["id"])))
    )
    assert cached_before == before

    r = client.patch(f"/steps/{step['id']}", headers=auth, json={"timestamp_s": 1.0})
    assert r.status_code == 200
    out = r.json()
    assert out["timestamp_s"] == 1.0
    fresh = client.get(out["ref_image_url"]).content
    assert fresh != before
    assert Image.open(io.BytesIO(fresh)).size == (1280, 720)
    cached_after = asyncio.run(
        refcache.get_ref_image(store, asyncio.run(store.get_step(step["id"])))
    )
    assert cached_after == fresh


def test_patch_timestamp_reuses_the_cached_download(client, auth, testsrc_bytes, monkeypatch):
    rid, body = ingest_video(client, auth, testsrc_bytes)
    videocache.clear()
    store = get_store()
    downloads = 0
    real = store.download_to_file

    async def counting(*a, **kw):
        nonlocal downloads
        downloads += 1
        return await real(*a, **kw)

    monkeypatch.setattr(store, "download_to_file", counting)
    for ts in (0.5, 1.5, 2.5):
        r = client.patch(f"/steps/{body['steps'][1]['id']}", headers=auth, json={"timestamp_s": ts})
        assert r.status_code == 200
    assert downloads == 1


def test_patch_timestamp_past_the_end_422(client, auth, testsrc_bytes):
    _, body = ingest_video(client, auth, testsrc_bytes)
    step = body["steps"][0]
    r = client.patch(f"/steps/{step['id']}", headers=auth, json={"timestamp_s": 99})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"
    assert "past the end of the video" in r.json()["error"]["message"]
    after = client.get(f"/recipes/{body['id']}", headers=auth).json()["steps"][0]
    assert after["timestamp_s"] == step["timestamp_s"]


def test_patch_timestamp_works_on_published_recipe(client, auth, testsrc_bytes):
    rid, body = ingest_video(client, auth, testsrc_bytes)
    assert client.post(f"/recipes/{rid}/publish", headers=auth).status_code == 200
    r = client.patch(f"/steps/{body['steps'][0]['id']}", headers=auth, json={"timestamp_s": 2.0})
    assert r.status_code == 200 and r.json()["timestamp_s"] == 2.0


def test_patch_timestamp_gives_a_missing_step_its_image(client, auth, testsrc_bytes, monkeypatch):
    real = ingest.extract_still

    async def fail_first(path, at_s, out_path, **kw):
        if at_s > 4.0 and not getattr(fail_first, "done", False):
            fail_first.done = True
            raise FfmpegError("boom")
        await real(path, at_s, out_path, **kw)

    monkeypatch.setattr(ingest, "extract_still", fail_first)
    rid, body = ingest_video(client, auth, testsrc_bytes)
    broken = [s for s in body["steps"] if s["ref_image_url"] is None]
    assert len(broken) == 1
    assert client.post(f"/recipes/{rid}/publish", headers=auth).status_code == 409
    r = client.patch(f"/steps/{broken[0]['id']}", headers=auth, json={"timestamp_s": 1.0})
    assert r.status_code == 200 and r.json()["ref_image_url"]
    assert client.post(f"/recipes/{rid}/publish", headers=auth).status_code == 200


def test_patch_timestamp_with_source_video_gone(client, auth, testsrc_bytes):
    rid, body = ingest_video(client, auth, testsrc_bytes)
    videocache.clear()
    asyncio.run(get_store().delete_prefix("videos", rid))
    r = client.patch(f"/steps/{body['steps'][0]['id']}", headers=auth, json={"timestamp_s": 1.0})
    assert r.status_code == 409
    assert r.json()["error"]["message"] == "source video is gone"


def test_patch_timestamp_extraction_failure_keeps_old_still(
    client, auth, testsrc_bytes, monkeypatch
):
    from app.routers import steps as steps_router

    _, body = ingest_video(client, auth, testsrc_bytes)
    step = body["steps"][0]
    before = client.get(step["ref_image_url"]).content

    async def boom(*a, **kw):
        raise FfmpegError("boom", "stderr text")

    monkeypatch.setattr(steps_router, "extract_still", boom)
    r = client.patch(f"/steps/{step['id']}", headers=auth, json={"timestamp_s": 1.0})
    assert r.status_code == 500
    assert r.json()["error"]["message"] == "could not extract a frame"
    assert client.get(step["ref_image_url"]).content == before


def test_patch_timestamp_on_seeded_step_is_stored_without_extraction(client, auth):
    before = client.get(f"/recipes/{SEED_RECIPE_ID}", headers=auth).json()
    step = next(s for s in before["steps"] if s["id"] == CHECKED_STEP)
    image = client.get(step["ref_image_url"]).content
    r = client.patch(f"/steps/{CHECKED_STEP}", headers=auth, json={"timestamp_s": 80.5})
    assert r.status_code == 200 and r.json()["timestamp_s"] == 80.5
    assert client.get(r.json()["ref_image_url"]).content == image


def test_delete_seed_recipe_needs_force(client, auth):
    r = client.delete(f"/recipes/{SEED_RECIPE_ID}", headers=auth)
    assert r.status_code == 409
    err = r.json()["error"]
    assert err["code"] == "recipe_not_ready"
    assert err["message"] == "the demo recipe is protected; add ?force=true to delete it"
    assert client.get(f"/recipes/{SEED_RECIPE_ID}", headers=auth).status_code == 200
    assert client.delete(f"/recipes/{SEED_RECIPE_ID}?force=true", headers=auth).status_code == 204


def test_delete_other_recipe_needs_no_force(client, auth):
    rid = _create(client, auth)["recipe_id"]
    assert client.delete(f"/recipes/{rid}", headers=auth).status_code == 204
    assert client.get(f"/recipes/{SEED_RECIPE_ID}", headers=auth).status_code == 200


def test_video_cache_is_bounded(tmp_path, testsrc_mp4):
    async def go():
        info = {"duration_s": 5.0, "width": 1, "height": 1, "rotation": 0}
        for i in range(4):
            f = Path(tmp_path) / f"v{i}.mp4"
            f.write_bytes(b"x")
            await videocache.put(f"r{i}", f, info)
        assert list(videocache._entries) == ["r2", "r3"]
        assert len(list(videocache._cache_dir().iterdir())) == 2
        videocache.clear()

    asyncio.run(go())


# --------------------------------------------------------------------------- review-round fixes
async def test_startup_sweep_runs_in_the_background(app, monkeypatch):
    started = asyncio.Event()

    async def hangs(store, now=None):
        started.set()
        await asyncio.sleep(3600)

    monkeypatch.setattr(ingest, "startup_sweep", hangs)
    cm = app.router.lifespan_context(app)
    await asyncio.wait_for(cm.__aenter__(), 5)  # boot is not held up by the sweep
    await asyncio.wait_for(started.wait(), 5)
    await asyncio.wait_for(cm.__aexit__(None, None, None), 5)  # and shutdown cancels it


async def test_failing_startup_sweep_does_not_break_boot(app, monkeypatch, caplog):
    async def boom(store, now=None):
        raise RuntimeError("storage down")

    monkeypatch.setattr(ingest, "startup_sweep", boom)
    async with app.router.lifespan_context(app):
        await asyncio.sleep(0.1)
    assert "startup sweep failed" in caplog.text


def test_patch_step_racing_delete_is_404_and_leaves_no_orphan(
    client, auth, testsrc_bytes, monkeypatch
):
    from app.store.ops import purge_recipe

    rid, body = ingest_video(client, auth, testsrc_bytes)
    store = get_store()
    real = store.put_blob

    async def put_then_purge(bucket, path, data, content_type):
        await real(bucket, path, data, content_type)
        await purge_recipe(store, rid)
        await real(bucket, path, data, content_type)  # the late write after the purge

    monkeypatch.setattr(store, "put_blob", put_then_purge)
    r = client.patch(f"/steps/{body['steps'][0]['id']}", headers=auth, json={"timestamp_s": 1.0})
    assert r.status_code == 404
    assert not (get_settings().data_path / "media" / rid).exists()


def test_videocache_purges_idle_entries_on_a_timer(tmp_path, monkeypatch):
    monkeypatch.setattr(videocache, "TTL_S", 0.2)
    info = {"duration_s": 5.0, "width": 1, "height": 1, "rotation": 0}

    async def go():
        f = tmp_path / "v.mp4"
        f.write_bytes(b"x")
        await videocache.put("r1", f, info)
        cached = videocache._cache_dir() / "r1.mp4"
        assert cached.is_file()
        await asyncio.sleep(0.6)  # nothing touches the cache meanwhile
        assert not videocache._entries and not cached.exists()
        videocache.clear()

    asyncio.run(go())


def test_videocache_evict_beats_an_inflight_download(tmp_path):
    release = asyncio.Event()

    class SlowStore:
        async def download_to_file(self, bucket, path, dest, max_bytes):
            dest.write_bytes(b"x")
            await release.wait()
            return True

    async def fake_probe(path):
        return {"duration_s": 5.0, "width": 1, "height": 1, "rotation": 0}

    async def go():
        recipe = Recipe(title="t", status="review", video_path="r/source.mp4")
        task = asyncio.create_task(videocache.get_or_download(SlowStore(), recipe))
        await asyncio.sleep(0.1)
        videocache.evict(recipe.id)
        release.set()
        assert await task is None
        assert not videocache._entries
        assert not (videocache._cache_dir() / f"{recipe.id}.mp4").exists()
        assert not videocache._inflight and not videocache._cancelled
        videocache.clear()

    import app.media.videocache as vc

    orig = vc.probe
    vc.probe = fake_probe
    try:
        asyncio.run(go())
    finally:
        vc.probe = orig


async def test_sweep_leaves_a_running_job_alone(app, testsrc_bytes, monkeypatch):
    from ghostchef_ai import fake

    release = asyncio.Event()
    started = asyncio.Event()

    async def gated(video_path, *, title_hint=None, step_marks_s=None):
        started.set()
        await release.wait()
        return fake.load_fixture()

    _patch_extract(monkeypatch, gated)
    h = {"X-Demo-Key": KEY}
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://t"
        ) as c:
            created = (
                await c.post("/recipes", headers=h, json={"title": "S", "consent": True})
            ).json()
            rid = created["recipe_id"]
            await c.put(created["upload_url"].replace("http://t", ""), content=testsrc_bytes)
            store = get_store()
            await store.update_recipe(rid, created_at=utcnow() - timedelta(minutes=30))
            await c.post(f"/recipes/{rid}/process", headers=h)
            await asyncio.wait_for(started.wait(), 20)
            await ingest.startup_sweep(store)
            assert (await store.get_recipe(rid)).status == "processing"
            release.set()
            await ingest.wait_all()
            assert (await store.get_recipe(rid)).status == "review"
            # once the job is over the guard is gone: a stale `processing` recipe is swept
            await store.update_recipe(rid, status="processing")
            await ingest.startup_sweep(store)
            assert (await store.get_recipe(rid)).status == "failed"
