"""BE-05: real /live-token handler (fake AI), complete monitor, sessions list and summary."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import timedelta

import pytest

from app.deps import get_store
from app.routers import live
from app.routers.sessions import summarize
from app.seed import SEED_RECIPE_ID, seed_step_id
from app.store.base import Event, utcnow
from tests.conftest import requires_ai
from tests.helpers import CHECKED_STEP, RECIPE_TITLE, big_jpeg, post_frame

pytestmark = requires_ai


def _session(client, auth) -> str:
    r = client.post(
        "/sessions",
        headers=auth,
        json={"recipe_id": SEED_RECIPE_ID, "client": "web-sim", "device_label": "pytest"},
    )
    assert r.status_code == 201
    return r.json()["session_id"]


def _event(client, auth, sid, kind, **kw):
    r = client.post(f"/sessions/{sid}/events", headers=auth, json={"kind": kind, **kw})
    assert r.status_code == 201, r.text
    return r.json()["event_id"]


def _step_change(client, auth, sid, to_idx, from_idx=1):
    return _event(
        client,
        auth,
        sid,
        "step_change",
        step_id=seed_step_id(SEED_RECIPE_ID, to_idx),
        payload={"from_idx": from_idx, "to_idx": to_idx, "via": "tap"},
    )


def _monitor(client, auth, sid):
    r = client.get(f"/sessions/{sid}/monitor", headers=auth)
    assert r.status_code == 200, r.text
    return r.json()


def _expire_monitor_cache():
    from app.routers import sessions

    sessions.reset()


# ------------------------------------------------------------------ BE-05.1 /live-token


def test_live_token_shape_fake(client, auth):
    sid = _session(client, auth)
    r = client.get(f"/live-token?recipe_id={SEED_RECIPE_ID}&session_id={sid}", headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert body["token"] == "fake-token"
    assert body["api_version"] == "v1beta"
    assert body["locked"] is False
    assert body["model"]
    assert body["config"]["response_modalities"] == ["AUDIO"]
    assert body["config"]["session_resumption"] is True
    assert body["expires_at"] > body["new_session_expires_at"]


def test_live_token_unpublished_recipe_409(client, auth):
    asyncio.run(get_store().update_recipe(SEED_RECIPE_ID, status="review"))
    r = client.get(f"/live-token?recipe_id={SEED_RECIPE_ID}", headers=auth)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "recipe_not_ready"


def test_live_token_bad_session(client, auth):
    r = client.get(
        f"/live-token?recipe_id={SEED_RECIPE_ID}&session_id={uuid.uuid4()}", headers=auth
    )
    assert r.status_code == 404
    r = client.get(f"/live-token?recipe_id={SEED_RECIPE_ID}&session_id=nope", headers=auth)
    assert r.status_code == 422


def test_live_token_three_second_guard(client, auth):
    sid = _session(client, auth)
    url = f"/live-token?recipe_id={SEED_RECIPE_ID}&session_id={sid}"
    assert client.get(url, headers=auth).status_code == 200
    r = client.get(url, headers=auth)
    assert r.status_code == 429
    err = r.json()["error"]
    assert err["code"] == "quota_exhausted" and err["retryable"] is True
    # Another session is not affected; neither is a call without session_id.
    other = _session(client, auth)
    assert (
        client.get(
            f"/live-token?recipe_id={SEED_RECIPE_ID}&session_id={other}", headers=auth
        ).status_code
        == 200
    )
    assert client.get(f"/live-token?recipe_id={SEED_RECIPE_ID}", headers=auth).status_code == 200
    # After 3 s the same session gets a token again.
    live._last_mint[sid] -= live.GUARD_S
    assert client.get(url, headers=auth).status_code == 200


def test_live_config_cached_token_not(client, auth, monkeypatch):
    from app import ai

    g = ai.get()
    builds = []
    mints = []
    real_build, real_mint = g.build_live_config, g.mint_live_token

    def build(*a, **kw):
        builds.append(1)
        return real_build(*a, **kw)

    async def mint(cfg):
        mints.append(1)
        return await real_mint(cfg)

    monkeypatch.setattr(g, "build_live_config", build)
    monkeypatch.setattr(g, "mint_live_token", mint)
    url = f"/live-token?recipe_id={SEED_RECIPE_ID}"
    for _ in range(3):
        assert client.get(url, headers=auth).status_code == 200
    assert (len(builds), len(mints)) == (1, 3)

    # A changed step changes the hash, so the config is rebuilt (and replaces the old entry).
    r = client.patch(
        f"/steps/{CHECKED_STEP}", headers=auth, json={"instruction": "Spread it thin."}
    )
    assert r.status_code == 200
    assert client.get(url, headers=auth).status_code == 200
    assert len(builds) == 2
    assert "Spread it thin." in client.get(url, headers=auth).json()["config"]["system_instruction"]
    assert len(builds) == 2
    assert sum(k.startswith(SEED_RECIPE_ID) for k in live._config_cache) == 1


def test_live_token_never_logged(client, auth, caplog):
    caplog.set_level(logging.INFO, logger="ghostchef")
    assert client.get(f"/live-token?recipe_id={SEED_RECIPE_ID}", headers=auth).status_code == 200
    recs = [r for r in caplog.records if r.name == "ghostchef.live"]
    assert len(recs) == 1
    assert set(recs[0].fields) == {"recipe_id", "model", "locked", "expires_at"}
    for r in caplog.records:
        assert "fake-token" not in r.getMessage()
        assert "fake-token" not in str(getattr(r, "fields", ""))


def test_live_token_ai_error_maps(client, auth, monkeypatch):
    from app import ai

    g = ai.get()

    async def boom(cfg):
        raise g.AIUnavailable("not ready")

    monkeypatch.setattr(g, "mint_live_token", boom)
    r = client.get(f"/live-token?recipe_id={SEED_RECIPE_ID}", headers=auth)
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "model_unavailable"


# ------------------------------------------------------------------ BE-05.2 monitor


def test_monitor_empty_session(client, auth):
    sid = _session(client, auth)
    m = _monitor(client, auth, sid)
    assert m["current_step"]["idx"] == 1
    assert m["current_step"]["ref_image_url"]
    assert m["last_frame_url"] is None and m["last_frame_at"] is None
    assert m["last_result"] is None
    assert m["events"] == []
    assert m["latency"] == {
        "check_p50_ms": None,
        "check_max_ms": None,
        "watch_p50_ms": None,
        "watch_max_ms": None,
        "n_check": 0,
        "n_watch": 0,
    }


def test_monitor_follows_step_change(client, auth):
    sid = _session(client, auth)
    _step_change(client, auth, sid, 4)
    assert _monitor(client, auth, sid)["current_step"]["idx"] == 4
    _step_change(client, auth, sid, 2, from_idx=4)
    _event(client, auth, sid, "question", payload={"caption": "how thin"})
    m = _monitor(client, auth, sid)
    assert m["current_step"]["idx"] == 2  # latest step_change, not a later non-step event
    assert m["current_step"]["id"] == seed_step_id(SEED_RECIPE_ID, 2)
    assert [e["kind"] for e in m["events"]] == ["question", "step_change", "step_change"]
    # Unknown index falls back to step 1.
    _step_change(client, auth, sid, 99, from_idx=2)
    assert _monitor(client, auth, sid)["current_step"]["idx"] == 1


def test_monitor_ok_watch_in_last_result_not_events(client, auth):
    sid = _session(client, auth)
    r = post_frame(client, auth, "watch", big_jpeg(), session_id=sid)
    assert r.json()["status"] == "ok"
    m = _monitor(client, auth, sid)
    assert m["last_result"]["source"] == "watch"
    assert m["last_result"]["body"]["status"] == "ok"
    assert m["last_result"]["body"]["request_id"] == r.json()["request_id"]
    assert m["events"] == []
    assert m["last_frame_url"] and m["last_frame_at"]
    img = client.get(m["last_frame_url"])
    assert img.status_code == 200 and img.headers["content-type"] == "image/jpeg"
    assert (m["latency"]["n_watch"], m["latency"]["n_check"]) == (1, 0)


def test_monitor_after_warn(client, auth):
    sid = _session(client, auth)
    for _ in range(3):
        assert (
            post_frame(client, auth, "watch", big_jpeg(), session_id=sid).json()["status"] == "ok"
        )
    r = post_frame(client, auth, "watch", big_jpeg(), session_id=sid)
    assert r.json()["status"] == "warn"
    m = _monitor(client, auth, sid)
    assert m["last_result"]["body"]["status"] == "warn"
    assert [e["kind"] for e in m["events"]] == ["watch_warn"]
    assert m["events"][0]["payload"]["mistake_id"] == r.json()["mistake_id"]
    assert m["latency"]["n_watch"] == 4


def test_monitor_after_check(client, auth):
    sid = _session(client, auth)
    post_frame(client, auth, "watch", big_jpeg(), session_id=sid)
    r = post_frame(client, auth, "check", big_jpeg(), session_id=sid)
    assert r.status_code == 200
    m = _monitor(client, auth, sid)
    assert m["last_result"]["source"] == "check"
    assert m["last_result"]["body"]["verdict"] == r.json()["verdict"]
    assert [e["kind"] for e in m["events"]] == [f"check_{r.json()['verdict']}"]
    lat = m["latency"]
    assert lat["n_check"] == 1 and lat["check_p50_ms"] is not None
    assert lat["check_max_ms"] >= lat["check_p50_ms"]


def test_monitor_last_30_events_newest_first(client, auth):
    sid = _session(client, auth)
    ids = [_event(client, auth, sid, "show_me") for _ in range(35)]
    m = _monitor(client, auth, sid)
    assert [e["id"] for e in m["events"]] == list(reversed(ids[-30:]))


def test_monitor_after_restart_state_lost(client, auth):
    from app import metrics

    sid = _session(client, auth)
    post_frame(client, auth, "watch", big_jpeg(), session_id=sid)
    metrics.reset()  # what a process restart does to in-memory state
    _expire_monitor_cache()
    m = _monitor(client, auth, sid)
    assert m["last_frame_url"] is None and m["last_result"] is None
    assert m["latency"]["n_watch"] == 0


def test_monitor_cache_uses_one_store_query(client, auth, monkeypatch):
    sid = _session(client, auth)
    _monitor(client, auth, sid)  # warm
    store = get_store()
    calls = []
    for name in ("get_session", "get_recipe", "list_steps", "list_events"):
        orig = getattr(store, name)

        def wrap(*a, _orig=orig, _name=name, **kw):
            calls.append(_name)
            return _orig(*a, **kw)

        monkeypatch.setattr(store, name, wrap)
    _monitor(client, auth, sid)
    assert calls == ["list_events"]


def test_monitor_sees_session_end_immediately(client, auth):
    sid = _session(client, auth)
    assert _monitor(client, auth, sid)["session"]["finished_at"] is None
    _event(client, auth, sid, "session_end")
    assert _monitor(client, auth, sid)["session"]["finished_at"] is not None


def test_monitor_60_calls_fast(client, auth):
    sid = _session(client, auth)
    _step_change(client, auth, sid, 3)
    post_frame(client, auth, "check", big_jpeg(), session_id=sid)
    post_frame(client, auth, "watch", big_jpeg(), session_id=sid)
    for _ in range(30):
        _event(client, auth, sid, "show_me")
    t0 = time.perf_counter()
    for _ in range(60):
        _monitor(client, auth, sid)
    per_call_ms = (time.perf_counter() - t0) * 1000 / 60
    assert per_call_ms < 50, per_call_ms


# ------------------------------------------------------------------ BE-05.3 list + summary


def test_sessions_active_window(client, auth):
    old = _session(client, auth)
    fresh = _session(client, auth)
    ended = _session(client, auth)
    _event(client, auth, ended, "session_end")
    asyncio.run(
        get_store().update_session(old, started_at=utcnow() - timedelta(hours=3, minutes=1))
    )
    body = client.get("/sessions?active=true&limit=5", headers=auth).json()
    assert [s["id"] for s in body["sessions"]] == [fresh]
    assert body["sessions"][0]["recipe_title"] == RECIPE_TITLE
    all_ids = [s["id"] for s in client.get("/sessions?limit=5", headers=auth).json()["sessions"]]
    assert set(all_ids) == {old, fresh, ended}


def test_sessions_list_newest_first_and_limit(client, auth):
    ids = [_session(client, auth) for _ in range(4)]
    store = get_store()
    for i, sid in enumerate(ids):
        asyncio.run(store.update_session(sid, started_at=utcnow() - timedelta(minutes=10 - i)))
    body = client.get("/sessions?active=true&limit=3", headers=auth).json()
    assert [s["id"] for s in body["sessions"]] == list(reversed(ids))[:3]


def test_session_end_idempotent(client, auth):
    sid = _session(client, auth)
    first = _event(client, auth, sid, "session_end")
    finished = client.get(f"/sessions/{sid}", headers=auth).json()["finished_at"]
    assert finished is not None
    second = _event(client, auth, sid, "session_end")
    detail = client.get(f"/sessions/{sid}", headers=auth).json()
    assert second == first
    assert detail["finished_at"] == finished
    assert [e["kind"] for e in detail["events"]].count("session_end") == 1


S = [seed_step_id(SEED_RECIPE_ID, i) for i in range(1, 7)]


def _ev(kind: str, step: str | None = None) -> Event:
    return Event(session_id="s", kind=kind, step_id=step)


SUMMARY_CASES = [
    pytest.param([], (6, 0, 0, 0, 0), id="empty"),
    pytest.param(
        [_ev("check_pass", S[0]), _ev("check_pass", S[1]), _ev("check_pass", S[2])],
        (6, 3, 0, 0, 0),
        id="all-pass",
    ),
    pytest.param(
        [_ev("check_fix", S[0]), _ev("check_pass", S[0]), _ev("check_pass", S[1])],
        (6, 1, 1, 0, 0),
        id="fix-then-pass",
    ),
    pytest.param(
        [
            _ev("check_unsure", S[0]),
            _ev("check_pass", S[0]),
            _ev("check_unsure", S[1]),
            _ev("check_unsure", S[2]),
            _ev("check_fix", S[2]),
        ],
        (6, 1, 1, 0, 0),
        id="unsure-ignored",
    ),
    pytest.param(
        [
            _ev("step_change", S[2]),
            _ev("watch_warn", S[2]),
            _ev("watch_warn", S[2]),
            _ev("question", S[2]),
            _ev("check_fix", S[2]),
            _ev("check_fix", S[2]),
            _ev("check_pass", S[2]),
            _ev("question"),
            _ev("warning_shown", S[2]),
            _ev("check_pass", S[3]),
            _ev("check_fix", S[3]),
            _ev("check_pass", None),
            _ev("session_end"),
        ],
        (6, 1, 3, 2, 2),
        id="mixed",
    ),
]


@pytest.mark.parametrize(("events", "expected"), SUMMARY_CASES)
def test_summary_table(events, expected):
    s = summarize(6, events)
    assert (
        s.steps_total,
        s.steps_passed_first_try,
        s.fixes_caught,
        s.warnings,
        s.questions,
    ) == expected


def test_summary_through_api(client, auth):
    sid = _session(client, auth)
    post_frame(client, auth, "check", big_jpeg(), session_id=sid)  # fake: fix
    post_frame(client, auth, "check", big_jpeg(), session_id=sid)  # fake: pass
    _event(client, auth, sid, "question", payload={"caption": "how much filling"})
    summary = client.get(f"/sessions/{sid}", headers=auth).json()["summary"]
    assert summary == {
        "steps_total": 6,
        "steps_passed_first_try": 0,
        "fixes_caught": 1,
        "warnings": 0,
        "questions": 1,
    }


# ------------------------------------------------------------------ review fixes


def test_monitor_404_right_after_recipe_delete(client, auth):
    sid = _session(client, auth)
    _monitor(client, auth, sid)  # cached
    assert client.delete(f"/recipes/{SEED_RECIPE_ID}", headers=auth).status_code == 204
    assert client.get(f"/sessions/{sid}/monitor", headers=auth).status_code == 404
    assert not any(k.startswith(SEED_RECIPE_ID) for k in live._config_cache)


def test_session_end_retry_after_failed_update_repairs(client, auth, monkeypatch):
    sid = _session(client, auth)
    store = get_store()
    real_update = store.update_session

    async def fail_once(*a, **kw):
        monkeypatch.setattr(store, "update_session", real_update)
        raise RuntimeError("storage blip")

    monkeypatch.setattr(store, "update_session", fail_once)
    r = client.post(f"/sessions/{sid}/events", headers=auth, json={"kind": "session_end"})
    assert r.status_code == 500
    second = _event(client, auth, sid, "session_end")
    detail = client.get(f"/sessions/{sid}", headers=auth).json()
    assert detail["finished_at"] is not None
    ends = [e for e in detail["events"] if e["kind"] == "session_end"]
    assert [e["id"] for e in ends] == [second]


def test_failed_mint_does_not_hold_guard(client, auth, monkeypatch):
    from app import ai

    g = ai.get()
    real_mint = g.mint_live_token

    async def boom(cfg):
        raise g.AITimeout("slow")

    sid = _session(client, auth)
    url = f"/live-token?recipe_id={SEED_RECIPE_ID}&session_id={sid}"
    monkeypatch.setattr(g, "mint_live_token", boom)
    assert client.get(url, headers=auth).status_code == 504
    monkeypatch.setattr(g, "mint_live_token", real_mint)
    assert client.get(url, headers=auth).status_code == 200
    assert client.get(url, headers=auth).status_code == 429


def test_monitor_load_racing_eviction_not_cached(client, auth, monkeypatch):
    from app.routers import sessions

    sid = _session(client, auth)
    store = get_store()
    real_steps = store.list_steps

    async def steps_then_end(*a, **kw):
        sessions.evict(sid)  # a session_end lands while the monitor is loading
        return await real_steps(*a, **kw)

    monkeypatch.setattr(store, "list_steps", steps_then_end)
    _monitor(client, auth, sid)
    assert sid not in sessions._monitor_cache
