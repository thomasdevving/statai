"""BE-03: input validation, reference cache, budgets, in-flight guard, frames, events, logs."""

from __future__ import annotations

import asyncio
import io
import json
import logging
import os

import httpx
import pytest
from PIL import Image

from app import faults, metrics, refcache
from app.config import get_settings
from app.deps import get_store
from app.media import images
from app.seed import SEED_RECIPE_ID

from .conftest import KEY, requires_ai
from .helpers import CHECKED_IDX, CHECKED_STEP, FIRST_MISTAKE_ID, big_jpeg, post_frame, rid

pytestmark = requires_ai


# --------------------------------------------------------------------------- helpers


def jpeg(w: int, h: int, *, noise: bool = False, quality: int = 85, orientation: int | None = None):
    if noise:
        img = Image.frombytes("RGB", (w, h), os.urandom(w * h * 3))
    else:
        img = Image.new("RGB", (w, h), (120, 90, 60))
    buf = io.BytesIO()
    kwargs = {}
    if orientation is not None:
        exif = Image.Exif()
        exif[0x0112] = orientation
        kwargs["exif"] = exif
    img.save(buf, "JPEG", quality=quality, **kwargs)
    return buf.getvalue()


def padded_jpeg(size: int) -> bytes:
    """A valid JPEG of exactly `size` bytes (trailing bytes after EOI are ignored by decoders)."""
    data = jpeg(640, 480, noise=True)
    assert len(data) < size
    return data + b"\x00" * (size - len(data))


def png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 64)).save(buf, "PNG")
    return buf.getvalue()


def session(client, auth) -> str:
    r = client.post(
        "/sessions", headers=auth, json={"recipe_id": SEED_RECIPE_ID, "client": "web-sim"}
    )
    assert r.status_code == 201
    return r.json()["session_id"]


def size_of(data: bytes) -> tuple[int, int]:
    return Image.open(io.BytesIO(data)).size


async def frames_in(session_id: str) -> list[str]:
    store = get_store()
    root = store.blob_file("frames", session_id)
    return sorted(p.name for p in root.glob("*.jpg")) if root.is_dir() else []


# --------------------------------------------------------------------------- BE-03.2 validation


def test_check_exactly_at_limit_is_accepted_one_byte_over_is_413(client, auth):
    at = padded_jpeg(images.CHECK_MAX_BYTES)
    assert len(at) == images.CHECK_MAX_BYTES
    r = post_frame(client, auth, "check", at)
    assert r.status_code == 200, r.text

    req = rid()
    r = post_frame(client, auth, "check", at + b"\x00", request_id=req)
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "payload_too_large"
    assert r.json()["error"]["request_id"] == req


def test_body_far_over_limit_stopped_by_guard(client, auth):
    r = post_frame(client, auth, "check", b"\xff" * (3 * 1024 * 1024))
    assert r.status_code == 413


def test_non_jpeg_is_415_with_request_id(client, auth):
    for bad in (png(), b"not an image at all" * 100, jpeg(64, 64)[:200]):
        req = rid()
        r = post_frame(client, auth, "check", bad, request_id=req)
        assert r.status_code == 415, r.text
        assert r.json()["error"] == {
            "code": "unsupported_media",
            "message": r.json()["error"]["message"],
            "retryable": False,
            "request_id": req,
        }
        r = post_frame(client, auth, "watch", bad)
        assert r.status_code == 415


def test_huge_canvas_rejected():
    # 8000 x 6000 = 48 MP of a flat colour compresses to a small file.
    data = jpeg(8000, 6000, quality=10)
    assert len(data) < images.CHECK_MAX_BYTES
    with pytest.raises(Exception) as exc:
        images.validate_jpeg_sync(data, images.CHECK_MAX_BYTES)
    assert getattr(exc.value, "status", None) == 413


def test_metadata_or_trailing_bytes_force_reencode():
    plain = jpeg(320, 240)
    assert images.downscale_jpeg_sync(plain, 512) is plain
    out = images.downscale_jpeg_sync(plain + b"hidden trailer", 512)
    assert out != plain + b"hidden trailer" and out.endswith(b"\xff\xd9")
    buf = io.BytesIO()
    Image.new("RGB", (320, 240)).save(buf, "JPEG", comment=b"gps 60.1,24.9")
    commented = buf.getvalue()
    out = images.downscale_jpeg_sync(commented, 512)
    assert b"gps" not in out


def test_unknown_session_ids_do_not_grow_metrics(client, auth):
    import uuid

    for _ in range(5):
        r = post_frame(client, auth, "check", png(), session_id=str(uuid.uuid4()))
        assert r.status_code == 404
    assert metrics._sessions == {}
    assert metrics.errors_total["not_found"] == 5


def test_downscale_untouched_when_within_limit():
    data = jpeg(1280, 720)
    assert images.downscale_jpeg_sync(data, 1280) is data
    small = jpeg(512, 300)
    assert images.downscale_jpeg_sync(small, 512) is small


def test_downscale_large_frame_to_long_edge():
    out = images.downscale_jpeg_sync(jpeg(2560, 1440), 1280)
    assert size_of(out) == (1280, 720)
    out = images.downscale_jpeg_sync(jpeg(1280, 720), 512)
    assert size_of(out) == (512, 288)


def test_downscale_applies_exif_orientation_before_measuring():
    # Stored 2000x1000 with orientation 6 (rotate 90): upright it is 1000x2000 (portrait).
    rotated = jpeg(2000, 1000, orientation=6)
    out = images.downscale_jpeg_sync(rotated, 1280)
    assert size_of(out) == (640, 1280)
    assert Image.open(io.BytesIO(out)).getexif().get(0x0112) is None  # baked in, EXIF gone
    # Upright 600x1300 is over 1280 even though the stored width is only 1300 x 600.
    out = images.downscale_jpeg_sync(jpeg(1300, 600, orientation=8), 1280)
    assert size_of(out)[1] == 1280


async def test_frame_is_prepared_in_one_thread_call(monkeypatch):
    calls = []

    async def fake_to_thread(fn, *a, **k):
        calls.append(fn.__name__)
        return fn(*a, **k)

    monkeypatch.setattr(images.asyncio, "to_thread", fake_to_thread)
    await images.prepare_check_frame(jpeg(100, 100))
    await images.prepare_watch_frame(jpeg(100, 100))
    assert calls == ["_prepare_sync", "_prepare_sync"]


def test_small_frame_with_exif_is_rotated_and_stripped():
    # 400x200 stored, orientation 6: within the limit, but must reach the model upright and
    # without EXIF (location data never stored).
    out = images.downscale_jpeg_sync(jpeg(400, 200, orientation=6), 1280)
    assert size_of(out) == (200, 400)
    assert not Image.open(io.BytesIO(out)).getexif()


def test_mpo_camera_jpeg_is_accepted(client, auth):
    a = Image.frombytes("RGB", (640, 480), os.urandom(640 * 480 * 3))
    buf = io.BytesIO()
    a.save(buf, "MPO", save_all=True, append_images=[a.copy()])
    data = buf.getvalue()
    assert Image.open(io.BytesIO(data)).format == "MPO"
    assert post_frame(client, auth, "check", data).status_code == 200
    assert post_frame(client, auth, "watch", data).status_code == 200


def test_truncated_large_frame_is_415_on_reencode_path():
    data = jpeg(2000, 1500, noise=True, quality=70)
    with pytest.raises(Exception) as exc:
        images.downscale_jpeg_sync(data[: len(data) // 2], 1280)
    assert getattr(exc.value, "status", None) == 415


def test_watch_frame_over_200kb_is_downscaled_not_rejected(client, auth, monkeypatch, caplog):
    import ghostchef_ai

    seen: list[bytes] = []
    real = ghostchef_ai.watch_frame

    async def spy(frame_jpeg, step, *, timeout_s=3.5):
        seen.append(frame_jpeg)
        return await real(frame_jpeg, step, timeout_s=timeout_s)

    monkeypatch.setattr(ghostchef_ai, "watch_frame", spy)
    big = jpeg(400, 400, noise=True, quality=98)
    assert images.WATCH_SOFT_BYTES < len(big) < images.WATCH_MAX_BYTES
    with caplog.at_level(logging.WARNING, logger="ghostchef.images"):
        r = post_frame(client, auth, "watch", big)
    assert r.status_code == 200, r.text
    assert len(seen[0]) < len(big)
    assert max(size_of(seen[0])) <= images.WATCH_LONG_EDGE
    assert any("over the" in rec.getMessage() for rec in caplog.records)

    # Over the 1.5 MB hard limit a watch frame is rejected.
    r = post_frame(client, auth, "watch", padded_jpeg(images.WATCH_MAX_BYTES + 1))
    assert r.status_code == 413


def test_watch_frame_large_dimensions_downscaled_to_512(client, auth, monkeypatch):
    import ghostchef_ai

    seen: list[bytes] = []

    async def spy(frame_jpeg, step, *, timeout_s=3.5):
        seen.append(frame_jpeg)
        return ghostchef_ai.WatchResult(
            status="ok",
            mistake_id=None,
            headline="",
            fix="",
            spoken="",
            confidence=0.0,
            model="spy",
        )

    monkeypatch.setattr(ghostchef_ai, "watch_frame", spy)
    assert post_frame(client, auth, "watch", jpeg(1280, 720)).status_code == 200
    assert size_of(seen[0]) == (512, 288)


def test_ids_must_be_uuids(client, auth):
    assert post_frame(client, auth, "check", big_jpeg(), step_id="x").status_code == 422
    assert post_frame(client, auth, "check", big_jpeg(), request_id="x").status_code == 422
    req = rid()
    r = post_frame(client, auth, "watch", big_jpeg(), session_id="nope", request_id=req)
    assert r.status_code == 422
    assert r.json()["error"]["request_id"] == req


def test_framework_errors_on_frame_routes_carry_request_id_when_known(client, auth):
    r = client.get("/check", headers=auth)
    assert r.status_code == 405
    assert r.json()["error"]["code"] == "method_not_allowed"
    assert metrics.errors_total["method_not_allowed"] == 1


def test_missing_fields_still_echo_request_id(client, auth):
    req = rid()
    r = client.post("/check", headers=auth, data={"step_id": CHECKED_STEP, "request_id": req})
    assert r.status_code == 422
    assert r.json()["error"]["request_id"] == req
    r = client.post(
        "/watch",
        headers=auth,
        data={"request_id": req},
        files={"frame": ("f.jpg", big_jpeg(), "image/jpeg")},
    )
    assert r.status_code == 422
    assert r.json()["error"]["request_id"] == req


def test_unknown_step_404_carries_request_id(client, auth):
    import uuid

    req = rid()
    r = post_frame(client, auth, "check", big_jpeg(), step_id=str(uuid.uuid4()), request_id=req)
    assert r.status_code == 404
    assert r.json()["error"]["request_id"] == req


# --------------------------------------------------------------------------- BE-03.3 ref cache


def test_two_checks_on_same_step_read_the_ref_blob_once(client, auth, monkeypatch):
    store = get_store()
    reads: list[tuple[str, str]] = []
    real = store.get_blob

    async def counting(bucket, path):
        reads.append((bucket, path))
        return await real(bucket, path)

    monkeypatch.setattr(store, "get_blob", counting)
    refcache.clear()
    assert post_frame(client, auth, "check", big_jpeg()).status_code == 200
    assert post_frame(client, auth, "check", big_jpeg()).status_code == 200
    assert [r for r in reads if r[0] == "media"] == [
        ("media", f"{SEED_RECIPE_ID}/steps/{CHECKED_IDX}/ref.jpg")
    ]


def test_ref_cache_invalidated_by_step_patch_and_recipe_delete(client, auth, monkeypatch):
    import ghostchef_ai

    refs: list[bytes | None] = []

    async def spy(frame_jpeg, step, ref_image_jpeg, *, timeout_s=8.0):
        refs.append(ref_image_jpeg)
        return ghostchef_ai.CheckResult(
            verdict="pass",
            mistake_id=None,
            headline="Looks right",
            fix="",
            spoken="ok",
            confidence=0.9,
            model="spy",
        )

    monkeypatch.setattr(ghostchef_ai, "check_frame", spy)
    refcache.clear()
    post_frame(client, auth, "check", big_jpeg())
    assert len(refcache._cache) == 1
    r = client.patch(f"/steps/{CHECKED_STEP}", headers=auth, json={"key_line": "Thin even layer"})
    assert r.status_code == 200
    assert len(refcache._cache) == 0

    post_frame(client, auth, "check", big_jpeg())
    assert len(refcache._cache) == 1
    assert client.delete(f"/recipes/{SEED_RECIPE_ID}?force=true", headers=auth).status_code == 204
    assert len(refcache._cache) == 0
    assert refs[0] is not None and refs[0] == refs[1]


async def test_step_without_ref_image_passes_none():
    from app.store.base import Step

    step = Step(
        recipe_id=SEED_RECIPE_ID, idx=9, title="t", key_line="k", instruction="i", timestamp_s=0.0
    )
    assert await refcache.get_ref_image(get_store(), step) is None


async def test_ref_cache_is_bounded():
    from app.store.base import Step

    class Blobs:
        async def get_blob(self, bucket, path):
            return path.encode()

    refcache.clear()
    for i in range(refcache.MAX_ENTRIES + 10):
        step = Step(
            recipe_id="r",
            idx=i,
            title="t",
            key_line="k",
            instruction="i",
            timestamp_s=0.0,
            ref_image_path=f"r/steps/{i}/ref.jpg",
        )
        assert await refcache.get_ref_image(Blobs(), step) == step.ref_image_path.encode()
    assert len(refcache._cache) == refcache.MAX_ENTRIES
    assert refcache.invalidate_recipe("r") is None and len(refcache._cache) == 0


# --------------------------------------------------------------------------- BE-03.4 budgets


def test_slow_watch_frame_gives_504(client, auth, monkeypatch):
    """A hang inside the package that ignores timeout_s still returns 504 (wait_for)."""
    import ghostchef_ai

    async def hang(frame_jpeg, step, *, timeout_s=3.5):
        await asyncio.sleep(30)

    monkeypatch.setenv("WATCH_BUDGET_S", "0.2")
    get_settings.cache_clear()
    monkeypatch.setattr(ghostchef_ai, "watch_frame", hang)
    sid = session(client, auth)
    req = rid()
    r = post_frame(client, auth, "watch", big_jpeg(), session_id=sid, request_id=req)
    assert r.status_code == 504
    assert r.json()["error"]["code"] == "model_timeout"
    assert r.json()["error"]["retryable"] is True
    assert r.json()["error"]["request_id"] == req
    # The in-flight flag was cleared: the next call is not 429.
    monkeypatch.undo()
    monkeypatch.setenv("DEMO_API_KEY", KEY)
    get_settings.cache_clear()
    assert post_frame(client, auth, "watch", big_jpeg(), session_id=sid).status_code == 200


def test_budget_is_passed_to_the_package(client, auth, monkeypatch):
    import ghostchef_ai

    seen = {}

    async def spy(frame_jpeg, step, ref, *, timeout_s=8.0):
        seen["check"] = timeout_s
        raise ghostchef_ai.AIQuotaError("quota")

    monkeypatch.setenv("CHECK_BUDGET_S", "6.5")
    get_settings.cache_clear()
    monkeypatch.setattr(ghostchef_ai, "check_frame", spy)
    req = rid()
    r = post_frame(client, auth, "check", big_jpeg(), request_id=req)
    assert seen["check"] == 6.5
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "quota_exhausted"
    assert r.json()["error"]["request_id"] == req


def test_quota_error_on_watch_gives_429(client, auth, monkeypatch):
    import ghostchef_ai

    async def quota(*a, **k):
        raise ghostchef_ai.AIQuotaError("rate limited")

    monkeypatch.setattr(ghostchef_ai, "watch_frame", quota)
    sid = session(client, auth)
    r = post_frame(client, auth, "watch", big_jpeg(), session_id=sid)
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "quota_exhausted"
    assert r.json()["error"]["retryable"] is True
    # flag cleared after an error too (the BE-07 cool-down would otherwise hold the next watch)
    faults.reset()
    monkeypatch.undo()
    monkeypatch.setenv("DEMO_API_KEY", KEY)
    get_settings.cache_clear()
    assert post_frame(client, auth, "watch", big_jpeg(), session_id=sid).status_code == 200
    assert metrics.get(sid).errors["quota_exhausted"] == 1


async def test_second_watch_in_flight_gets_429(monkeypatch):
    import ghostchef_ai

    from app.main import create_app
    from app.seed import seed_fixture

    started = asyncio.Event()

    async def slow(frame_jpeg, step, *, timeout_s=3.5):
        started.set()
        await asyncio.sleep(0.5)
        return ghostchef_ai.WatchResult(
            status="ok",
            mistake_id=None,
            headline="",
            fix="",
            spoken="",
            confidence=0.1,
            model="slow",
        )

    monkeypatch.setattr(ghostchef_ai, "watch_frame", slow)
    app = create_app()
    await seed_fixture(get_store())
    headers = {"X-Demo-Key": KEY}
    frame = big_jpeg()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        r = await c.post(
            "/sessions", headers=headers, json={"recipe_id": SEED_RECIPE_ID, "client": "ios"}
        )
        sid = r.json()["session_id"]

        def call(req: str):
            return c.post(
                "/watch",
                headers=headers,
                data={"step_id": CHECKED_STEP, "request_id": req, "session_id": sid},
                files={"frame": ("f.jpg", frame, "image/jpeg")},
            )

        first_req, second_req = rid(), rid()
        first = asyncio.create_task(call(first_req))
        await started.wait()
        second = await call(second_req)
        assert second.status_code == 429
        assert second.json()["error"] == {
            "code": "quota_exhausted",
            "message": "watch already in flight",
            "retryable": True,
            "request_id": second_req,
        }
        assert (await first).status_code == 200
        # A call without a session id is never guarded.
        started.clear()
        a = asyncio.create_task(
            c.post(
                "/watch",
                headers=headers,
                data={"step_id": CHECKED_STEP, "request_id": rid()},
                files={"frame": ("f.jpg", frame, "image/jpeg")},
            )
        )
        await started.wait()
        b = await c.post(
            "/watch",
            headers=headers,
            data={"step_id": CHECKED_STEP, "request_id": rid()},
            files={"frame": ("f.jpg", frame, "image/jpeg")},
        )
        assert b.status_code == 200 and (await a).status_code == 200
        # The flag is gone once the first call finished.
        assert (await call(rid())).status_code == 200


def test_disconnected_client_records_nothing(client, auth, monkeypatch):
    from starlette.requests import Request

    async def gone(self):
        return True

    monkeypatch.setattr(Request, "is_disconnected", gone)
    sid = session(client, auth)
    post_frame(client, auth, "check", big_jpeg(), session_id=sid)  # fake: fix
    events = client.get(f"/sessions/{sid}", headers=auth).json()["events"]
    assert events == []
    assert metrics.get(sid).last_result is None
    assert metrics.latency(sid)["n_check"] == 0


# --------------------------------------------------------------------------- BE-03.5 frames


def test_latest_frame_served_and_changes(client, auth):
    sid = session(client, auth)
    m = client.get(f"/sessions/{sid}/monitor", headers=auth).json()
    assert m["last_frame_url"] is None

    first = jpeg(320, 240)
    post_frame(client, auth, "watch", first, session_id=sid)
    m = client.get(f"/sessions/{sid}/monitor", headers=auth).json()
    url = m["last_frame_url"]
    assert f"/sessions/{sid}/latest-frame.jpg?t=" in url
    r = client.get(url)  # no X-Demo-Key: an <img> cannot send it
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"
    assert r.headers["cache-control"] == "no-store"
    assert r.content == first
    at1 = m["last_frame_at"]

    second = jpeg(330, 250)
    post_frame(client, auth, "check", second, session_id=sid)
    m2 = client.get(f"/sessions/{sid}/monitor", headers=auth).json()
    assert m2["last_frame_url"] == url  # same token for the session
    assert client.get(url).content == second
    assert m2["last_frame_at"] >= at1


def test_latest_frame_token_required(client, auth):
    sid = session(client, auth)
    post_frame(client, auth, "watch", jpeg(320, 240), session_id=sid)
    base = f"/sessions/{sid}/latest-frame.jpg"
    assert client.get(base).status_code == 404
    assert client.get(base + "?t=wrong").status_code == 404
    assert client.get(base + "?t=wrong", headers=auth).status_code == 404
    other = session(client, auth)
    token = metrics.get(sid).frame_token
    assert client.get(f"/sessions/{other}/latest-frame.jpg?t={token}").status_code == 404
    assert client.get(f"/sessions/not-a-uuid/latest-frame.jpg?t={token}").status_code == 404
    # The route is open only for this exact shape; other session routes still need the key.
    assert client.get(f"/sessions/{sid}").status_code == 401


async def test_warn_stores_frame_and_event_ok_stores_neither(client, auth):
    sid = session(client, auth)
    reqs = [rid() for _ in range(4)]
    statuses = [
        post_frame(client, auth, "watch", big_jpeg(), session_id=sid, request_id=r).json()["status"]
        for r in reqs
    ]
    assert statuses == ["ok", "ok", "ok", "warn"]
    events = client.get(f"/sessions/{sid}", headers=auth).json()["events"]
    assert [e["kind"] for e in events] == ["watch_warn"]
    ev = events[0]
    assert ev["request_id"] == reqs[3]
    assert ev["payload"]["frame_path"] == f"{sid}/{reqs[3]}.jpg"
    assert ev["payload"]["status"] == "warn" and ev["payload"]["mistake_id"] == FIRST_MISTAKE_ID
    assert await frames_in(sid) == [f"{reqs[3]}.jpg"]
    # metrics saw all four
    assert metrics.latency(sid)["n_watch"] == 4


async def test_every_check_frame_is_stored(client, auth):
    sid = session(client, auth)
    reqs = [rid(), rid()]
    for r in reqs:
        assert (
            post_frame(client, auth, "check", big_jpeg(), session_id=sid, request_id=r).status_code
            == 200
        )
    assert await frames_in(sid) == sorted(f"{r}.jpg" for r in reqs)
    kinds = [e["kind"] for e in client.get(f"/sessions/{sid}", headers=auth).json()["events"]]
    assert kinds == ["check_fix", "check_pass"]


async def test_failed_ai_call_produces_no_event(client, auth, monkeypatch):
    import ghostchef_ai

    async def broken(*a, **k):
        raise ghostchef_ai.AIUnavailable("503 high demand")

    monkeypatch.setattr(ghostchef_ai, "check_frame", broken)
    sid = session(client, auth)
    r = post_frame(client, auth, "check", big_jpeg(), session_id=sid)
    assert r.status_code == 503
    assert client.get(f"/sessions/{sid}", headers=auth).json()["events"] == []
    assert await frames_in(sid) == []
    assert metrics.get(sid).errors == {"model_unavailable": 1}
    assert metrics.errors_total["model_unavailable"] == 1
    # The monitor still shows what the wearer was looking at.
    m = client.get(f"/sessions/{sid}/monitor", headers=auth).json()
    assert m["last_frame_url"] is not None and m["last_result"] is None


def test_frame_storage_failure_keeps_event_without_frame_path(client, auth, monkeypatch):
    store = get_store()

    async def fail(*a, **k):
        raise RuntimeError("storage down")

    monkeypatch.setattr(store, "put_blob", fail)
    sid = session(client, auth)
    r = post_frame(client, auth, "check", big_jpeg(), session_id=sid)
    assert r.status_code == 200
    events = client.get(f"/sessions/{sid}", headers=auth).json()["events"]
    assert [e["kind"] for e in events] == ["check_fix"]
    assert "frame_path" not in events[0]["payload"]


def test_ring_buffer_bounded():
    for i in range(metrics.RING + 20):
        metrics.record("s", "watch", i, {}, None)  # type: ignore[arg-type]
    assert metrics.latency("s")["n_watch"] == metrics.RING


# --------------------------------------------------------------------------- BE-03.6 logging


def _call_lines(caplog) -> list[dict]:
    from app.logs import JsonFormatter

    fmt = JsonFormatter()
    return [json.loads(fmt.format(r)) for r in caplog.records if r.name == "ghostchef.calls"]


def test_one_log_line_per_call(client, auth, caplog):
    sid = session(client, auth)
    req = rid()
    with caplog.at_level(logging.INFO, logger="ghostchef.calls"):
        post_frame(client, auth, "check", big_jpeg(), session_id=sid, request_id=req)
        post_frame(client, auth, "watch", png(), session_id=sid)
    lines = _call_lines(caplog)
    assert len(lines) == 2
    ok, bad = lines
    assert ok["endpoint"] == "/check" and ok["session_id"] == sid and ok["request_id"] == req
    assert ok["step_idx"] == CHECKED_IDX
    assert ok["verdict"] == "fix" and ok["mistake_id"] == FIRST_MISTAKE_ID
    assert ok["http_status"] == 200 and ok["model"] == "fake"
    assert isinstance(ok["latency_ms"], int) and isinstance(ok["confidence"], float)
    assert bad["endpoint"] == "/watch" and bad["http_status"] == 415
    assert bad["error"] == "unsupported_media"
    raw = " ".join(json.dumps(x) for x in lines)
    assert KEY not in raw


def test_access_log_redacts_frame_token():
    from app.logs import RedactQueryFilter

    rec = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        "",
        0,
        '%s - "%s %s HTTP/%s" %d',
        ("1.2.3.4", "GET", "/sessions/x/latest-frame.jpg?t=SECRET&a=1", "1.1", 200),
        None,
    )
    RedactQueryFilter().filter(rec)
    assert "SECRET" not in rec.getMessage() and "t=***" in rec.getMessage()
