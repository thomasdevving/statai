from __future__ import annotations

import uuid

from app.seed import SEED_RECIPE_ID

from .conftest import requires_ai
from .helpers import STEP2, STEP3, big_jpeg, post_frame, rid, tiny_jpeg

pytestmark = requires_ai

CHECK_FIELDS = {
    "request_id",
    "step_id",
    "verdict",
    "mistake_id",
    "headline",
    "fix",
    "spoken",
    "confidence",
    "latency_ms",
    "model",
}
WATCH_FIELDS = (CHECK_FIELDS - {"verdict"}) | {"status"}


def _session(client, auth) -> str:
    r = client.post(
        "/sessions",
        headers=auth,
        json={"recipe_id": SEED_RECIPE_ID, "client": "ios", "device_label": "test"},
    )
    assert r.status_code == 201
    assert set(r.json()) == {"session_id", "started_at"}
    return r.json()["session_id"]


def test_check_sequence_fix_then_pass(client, auth):
    req = rid()
    r = post_frame(client, auth, "check", big_jpeg(), request_id=req)
    assert r.status_code == 200
    body = r.json()
    assert set(body) == CHECK_FIELDS
    assert body["request_id"] == req and body["step_id"] == STEP3
    assert body["verdict"] == "fix"
    assert body["mistake_id"] == "rice_too_thick"
    assert body["headline"] == "Too much rice"
    assert isinstance(body["latency_ms"], int) and body["latency_ms"] >= 0
    assert body["model"] == "fake"
    r = post_frame(client, auth, "check", big_jpeg())
    assert r.json()["verdict"] == "pass"
    assert r.json()["fix"] == ""


def test_check_tiny_frame_unsure(client, auth):
    r = post_frame(client, auth, "check", tiny_jpeg())
    assert r.status_code == 200
    assert r.json()["verdict"] == "unsure"


def test_watch_sequence(client, auth):
    statuses = []
    for _ in range(6):
        r = post_frame(client, auth, "watch", big_jpeg())
        assert r.status_code == 200
        assert set(r.json()) == WATCH_FIELDS
        statuses.append(r.json()["status"])
    assert statuses == ["ok", "ok", "ok", "warn", "warn", "warn"]
    assert r.json()["mistake_id"] == "rice_too_thick"


def test_check_errors(client, auth):
    assert post_frame(client, {}, "check", big_jpeg()).status_code == 401
    r = post_frame(client, auth, "check", big_jpeg(), step_id=str(uuid.uuid4()))
    assert r.status_code == 404
    r = post_frame(client, auth, "check", big_jpeg(), session_id=str(uuid.uuid4()))
    assert r.status_code == 404
    r = post_frame(client, auth, "check", big_jpeg(), request_id="nope")
    assert r.status_code == 422
    r = client.post("/check", headers=auth, data={"step_id": STEP3, "request_id": rid()})
    assert r.status_code == 422


def test_ai_errors_map_to_envelope(client, auth, monkeypatch):
    import ghostchef_ai

    async def boom(*a, **k):
        raise ghostchef_ai.AITimeout("Gemini did not answer within 8 s")

    async def quota(*a, **k):
        raise ghostchef_ai.AIQuotaError("quota")

    monkeypatch.setattr(ghostchef_ai, "check_frame", boom)
    monkeypatch.setattr(ghostchef_ai, "watch_frame", quota)
    req = rid()
    r = post_frame(client, auth, "check", big_jpeg(), request_id=req)
    assert r.status_code == 504
    assert r.json()["error"] == {
        "code": "model_timeout",
        "retryable": True,
        "request_id": req,
        "message": "Gemini did not answer within 8 s",
    }
    r = post_frame(client, auth, "watch", big_jpeg())
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "quota_exhausted"


def test_session_events_and_summary(client, auth):
    sid = _session(client, auth)
    # step 3: fix, then pass -> not first try; one fix caught
    assert post_frame(client, auth, "check", big_jpeg(), session_id=sid).json()["verdict"] == "fix"
    assert post_frame(client, auth, "check", big_jpeg(), session_id=sid).json()["verdict"] == "pass"
    # step 2 (no watch_fors): unsure first (ignored), then pass -> first try
    assert (
        post_frame(client, auth, "check", tiny_jpeg(), step_id=STEP2, session_id=sid).json()[
            "verdict"
        ]
        == "unsure"
    )
    assert (
        post_frame(client, auth, "check", big_jpeg(), step_id=STEP2, session_id=sid).json()[
            "verdict"
        ]
        == "pass"
    )
    for _ in range(4):  # 4th is the first warn
        post_frame(client, auth, "watch", big_jpeg(), session_id=sid)
    r = client.post(
        f"/sessions/{sid}/events",
        headers=auth,
        json={"kind": "question", "payload": {"caption": "why wet hands"}},
    )
    assert r.status_code == 201 and set(r.json()) == {"event_id"}
    r = client.post(
        f"/sessions/{sid}/events",
        headers=auth,
        json={
            "kind": "step_change",
            "step_id": STEP3,
            "payload": {"from_idx": 2, "to_idx": 3, "via": "pinch"},
        },
    )
    assert r.status_code == 201

    body = client.get(f"/sessions/{sid}", headers=auth).json()
    assert set(body) == {
        "id",
        "recipe_id",
        "client",
        "device_label",
        "started_at",
        "finished_at",
        "events",
        "summary",
    }
    kinds = [e["kind"] for e in body["events"]]
    assert kinds == [
        "check_fix",
        "check_pass",
        "check_unsure",
        "check_pass",
        "watch_warn",
        "question",
        "step_change",
    ]
    ev = body["events"][0]
    assert set(ev) == {"id", "kind", "step_id", "request_id", "payload", "created_at"}
    assert ev["payload"]["verdict"] == "fix"
    assert ev["payload"]["frame_path"].startswith(f"{sid}/")
    assert body["summary"] == {
        "steps_total": 6,
        "steps_passed_first_try": 1,
        "fixes_caught": 1,
        "warnings": 1,
        "questions": 1,
    }
    assert body["finished_at"] is None

    assert (
        client.post(
            f"/sessions/{sid}/events", headers=auth, json={"kind": "session_end"}
        ).status_code
        == 201
    )
    assert client.get(f"/sessions/{sid}", headers=auth).json()["finished_at"] is not None


def test_event_validation(client, auth):
    sid = _session(client, auth)
    for kind in ("check_pass", "check_fix", "check_unsure", "watch_warn", "made_up"):
        r = client.post(f"/sessions/{sid}/events", headers=auth, json={"kind": kind})
        assert r.status_code == 422, kind
    r = client.post(f"/sessions/{uuid.uuid4()}/events", headers=auth, json={"kind": "show_me"})
    assert r.status_code == 404
    r = client.post(
        "/sessions", headers=auth, json={"recipe_id": str(uuid.uuid4()), "client": "ios"}
    )
    assert r.status_code == 404
    r = client.post("/sessions", headers=auth, json={"recipe_id": SEED_RECIPE_ID, "client": "tv"})
    assert r.status_code == 422


def test_list_sessions(client, auth):
    a = _session(client, auth)
    b = _session(client, auth)
    client.post(f"/sessions/{a}/events", headers=auth, json={"kind": "session_end"})
    body = client.get("/sessions?active=true&limit=5", headers=auth).json()
    ids = [s["id"] for s in body["sessions"]]
    assert ids == [b]
    s = body["sessions"][0]
    assert set(s) == {
        "id",
        "recipe_id",
        "recipe_title",
        "client",
        "device_label",
        "started_at",
        "finished_at",
    }
    assert s["recipe_title"] == "Maki roll"
    assert len(client.get("/sessions?limit=1", headers=auth).json()["sessions"]) == 1
    assert client.get("/sessions?limit=0", headers=auth).status_code == 422


def test_monitor(client, auth):
    sid = _session(client, auth)
    m = client.get(f"/sessions/{sid}/monitor", headers=auth).json()
    assert m["current_step"]["idx"] == 1
    assert m["last_frame_url"] is None and m["last_result"] is None
    assert m["latency"]["n_check"] == 0

    client.post(
        f"/sessions/{sid}/events",
        headers=auth,
        json={"kind": "step_change", "payload": {"from_idx": 1, "to_idx": 3, "via": "tap"}},
    )
    post_frame(client, auth, "check", big_jpeg(), session_id=sid)
    post_frame(client, auth, "watch", big_jpeg(), session_id=sid)
    m = client.get(f"/sessions/{sid}/monitor", headers=auth).json()
    assert set(m) == {
        "session",
        "recipe_title",
        "current_step",
        "last_frame_url",
        "last_frame_at",
        "last_result",
        "events",
        "latency",
    }
    assert set(m["session"]) == {"id", "client", "device_label", "started_at", "finished_at"}
    assert m["recipe_title"] == "Maki roll"
    assert m["current_step"]["idx"] == 3
    assert m["last_result"]["source"] == "watch"
    assert m["last_result"]["body"]["status"] == "ok"
    assert client.get(m["last_frame_url"]).status_code == 200
    assert [e["kind"] for e in m["events"]] == ["check_fix", "step_change"]  # newest first
    lat = m["latency"]
    assert set(lat) == {
        "check_p50_ms",
        "check_max_ms",
        "watch_p50_ms",
        "watch_max_ms",
        "n_check",
        "n_watch",
    }
    assert (lat["n_check"], lat["n_watch"]) == (1, 1)
    assert client.get(f"/sessions/{uuid.uuid4()}/monitor", headers=auth).status_code == 404


def test_live_token(client, auth):
    sid = _session(client, auth)
    r = client.get(f"/live-token?recipe_id={SEED_RECIPE_ID}&session_id={sid}", headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {
        "token",
        "expires_at",
        "new_session_expires_at",
        "model",
        "api_version",
        "locked",
        "config",
    }
    assert body["api_version"] == "v1beta"
    assert isinstance(body["locked"], bool)
    assert set(body["config"]) == {
        "system_instruction",
        "response_modalities",
        "voice",
        "tools",
        "session_resumption",
    }
    assert "Maki roll" in body["config"]["system_instruction"]
    names = {f["name"] for t in body["config"]["tools"] for f in t["function_declarations"]}
    assert {"check_my_work", "next_step", "previous_step", "show_me", "repeat_instruction"} <= names
    assert client.get(f"/live-token?recipe_id={uuid.uuid4()}", headers=auth).status_code == 404
    assert client.get("/live-token", headers=auth).status_code == 422
    assert client.get(f"/live-token?recipe_id={SEED_RECIPE_ID}").status_code == 401
