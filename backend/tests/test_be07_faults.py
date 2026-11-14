"""BE-07.2: /watch quota cool-down and header-gated fault injection."""

from __future__ import annotations

import ghostchef_ai
import pytest

from app import faults
from app.config import get_settings

from .conftest import requires_ai
from .helpers import PLAIN_STEP, big_jpeg, rid

pytestmark = requires_ai


@pytest.fixture
def model_calls(monkeypatch):
    """Counts real model calls; watch_frame raises AIQuotaError while calls["quota"] is set."""
    calls = {"watch": 0, "check": 0, "quota": True}
    real_watch, real_check = ghostchef_ai.watch_frame, ghostchef_ai.check_frame

    async def watch(*a, **kw):
        calls["watch"] += 1
        if calls["quota"]:
            raise ghostchef_ai.AIQuotaError("429 from the model")
        return await real_watch(*a, **kw)

    async def check(*a, **kw):
        calls["check"] += 1
        return await real_check(*a, **kw)

    monkeypatch.setattr(ghostchef_ai, "watch_frame", watch)
    monkeypatch.setattr(ghostchef_ai, "check_frame", check)
    return calls


def _inject(monkeypatch, fault: str | None, enabled: str | None = "1") -> None:
    if fault is not None:
        monkeypatch.setenv("FAULT_INJECT", fault)
    if enabled is not None:
        monkeypatch.setenv("FAULT_INJECT_ENABLED", enabled)
    get_settings.cache_clear()


def _post(client, auth, endpoint, headers=None, request_id=None):
    frame = big_jpeg()
    r = client.post(
        f"/{endpoint}",
        headers={**auth, **(headers or {})},
        data={"step_id": PLAIN_STEP, "request_id": request_id or rid()},
        files={"frame": ("f.jpg", frame, "image/jpeg")},
    )
    return r


# ----------------------------------------------------------------------------- cool-down


def test_quota_on_watch_starts_cooldown_and_skips_the_model(client, auth, model_calls):
    first = _post(client, auth, "watch")
    assert first.status_code == 429 and first.json()["error"]["code"] == "quota_exhausted"
    assert model_calls["watch"] == 1

    my_rid = rid()
    second = _post(client, auth, "watch", request_id=my_rid)
    err = second.json()["error"]
    assert second.status_code == 429
    assert err["code"] == "quota_exhausted" and err["retryable"] is True
    assert err["request_id"] == my_rid
    assert model_calls["watch"] == 1  # the model was not called again


def test_check_is_served_during_cooldown(client, auth, model_calls):
    assert _post(client, auth, "watch").status_code == 429
    r = _post(client, auth, "check")
    assert r.status_code == 200
    assert model_calls["check"] == 1


def test_quota_on_check_does_not_start_watch_cooldown(client, auth, model_calls, monkeypatch):
    model_calls["quota"] = False

    async def check_quota(*a, **kw):
        raise ghostchef_ai.AIQuotaError("429")

    monkeypatch.setattr(ghostchef_ai, "check_frame", check_quota)
    assert _post(client, auth, "check").status_code == 429
    assert not faults.watch_cooldown_active()
    assert _post(client, auth, "watch").status_code == 200


def test_cooldown_expires(client, auth, model_calls, monkeypatch):
    clock = {"t": 1000.0}
    monkeypatch.setattr(faults.time, "monotonic", lambda: clock["t"])
    assert _post(client, auth, "watch").status_code == 429
    assert model_calls["watch"] == 1
    clock["t"] += faults.WATCH_COOLDOWN_S - 0.1
    assert _post(client, auth, "watch").status_code == 429
    assert model_calls["watch"] == 1
    clock["t"] += 0.2
    model_calls["quota"] = False
    assert _post(client, auth, "watch").status_code == 200
    assert model_calls["watch"] == 2


def test_cooldown_releases_the_inflight_claim_and_logs(client, auth, model_calls, caplog):
    from app.routers import frames

    session = client.post(
        "/sessions", headers=auth, json={"recipe_id": _seed(), "client": "web-sim"}
    ).json()["session_id"]
    frame = big_jpeg()

    def watch():
        return client.post(
            "/watch",
            headers=auth,
            data={"step_id": PLAIN_STEP, "request_id": rid(), "session_id": session},
            files={"frame": ("f.jpg", frame, "image/jpeg")},
        )

    with caplog.at_level("INFO", logger="ghostchef.calls"):
        assert watch().status_code == 429  # model quota
        assert watch().status_code == 429  # cool-down
    assert frames._watch_inflight == set()
    cooled = [r.fields for r in caplog.records if getattr(r, "fields", {}).get("cooldown")]
    assert len(cooled) == 1
    assert cooled[0]["http_status"] == 429 and cooled[0]["error"] == "quota_exhausted"


def test_cooldown_does_not_hide_a_bad_request_id(client, auth, model_calls):
    assert _post(client, auth, "watch").status_code == 429
    r = client.post(
        "/watch",
        headers=auth,
        data={"step_id": PLAIN_STEP, "request_id": "nope"},
        files={"frame": ("f.jpg", big_jpeg(), "image/jpeg")},
    )
    assert r.status_code == 422


def _seed() -> str:
    from app.seed import SEED_RECIPE_ID

    return SEED_RECIPE_ID


# ----------------------------------------------------------------------------- fault injection


@pytest.mark.parametrize(
    ("fault", "status", "code"),
    [
        ("timeout", 504, "model_timeout"),
        ("quota", 429, "quota_exhausted"),
        ("unavailable", 503, "model_unavailable"),
    ],
)
@pytest.mark.parametrize("endpoint", ["check", "watch"])
def test_injected_fault_with_header(
    client, auth, monkeypatch, model_calls, fault, status, code, endpoint
):
    model_calls["quota"] = False
    _inject(monkeypatch, fault)
    my_rid = rid()
    r = _post(client, auth, endpoint, headers={"X-Fault": "1"}, request_id=my_rid)
    assert r.status_code == status
    err = r.json()["error"]
    assert err["code"] == code and err["retryable"] is True and err["request_id"] == my_rid
    assert model_calls["watch"] == 0 and model_calls["check"] == 0


def test_injected_quota_on_watch_starts_cooldown_but_not_on_check(
    client, auth, monkeypatch, model_calls
):
    model_calls["quota"] = False
    _inject(monkeypatch, "quota")
    assert _post(client, auth, "check", headers={"X-Fault": "1"}).status_code == 429
    assert not faults.watch_cooldown_active()
    assert _post(client, auth, "watch", headers={"X-Fault": "1"}).status_code == 429
    assert faults.watch_cooldown_active()
    # the next watch, even without the header, is held by the cool-down
    assert _post(client, auth, "watch").status_code == 429
    assert model_calls["watch"] == 0


def test_enabled_without_header_is_normal(client, auth, monkeypatch, model_calls):
    model_calls["quota"] = False
    _inject(monkeypatch, "timeout")
    assert _post(client, auth, "check").status_code == 200
    assert _post(client, auth, "check", headers={"X-Fault": "0"}).status_code == 200
    assert _post(client, auth, "watch").status_code == 200


@pytest.mark.parametrize("enabled", [None, "", "0", "true", "yes"])
def test_header_without_enabled_is_ignored(client, auth, monkeypatch, model_calls, enabled):
    model_calls["quota"] = False
    _inject(monkeypatch, "timeout", enabled)
    assert _post(client, auth, "check", headers={"X-Fault": "1"}).status_code == 200
    assert _post(client, auth, "watch", headers={"X-Fault": "1"}).status_code == 200


def test_enabled_without_a_fault_value_is_a_no_op(client, auth, monkeypatch, model_calls):
    model_calls["quota"] = False
    _inject(monkeypatch, None)
    assert _post(client, auth, "check", headers={"X-Fault": "1"}).status_code == 200


def test_invalid_fault_value_is_rejected_by_settings(monkeypatch):
    from pydantic import ValidationError

    monkeypatch.setenv("FAULT_INJECT", "explode")
    get_settings.cache_clear()
    with pytest.raises(ValidationError):
        get_settings()


def test_live_token_fault(client, auth, monkeypatch):
    import asyncio

    from app.deps import get_store

    asyncio.run(get_store().update_recipe(_seed(), status="published"))
    _inject(monkeypatch, "unavailable")
    r = client.get(f"/live-token?recipe_id={_seed()}", headers={**auth, "X-Fault": "1"})
    assert r.status_code == 503 and r.json()["error"]["code"] == "model_unavailable"
    r = client.get(f"/live-token?recipe_id={_seed()}", headers=auth)
    assert r.status_code == 200


def test_startup_warns_when_enabled(monkeypatch, caplog, app):
    from fastapi.testclient import TestClient

    _inject(monkeypatch, "timeout")
    with caplog.at_level("WARNING", logger="ghostchef"):
        with TestClient(app):
            pass
    assert any("FAULT INJECTION IS ENABLED" in r.getMessage() for r in caplog.records)


def test_cors_allows_x_fault_header(client):
    r = client.options(
        "/check",
        headers={
            "Origin": "http://example.test",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-fault, x-demo-key",
        },
    )
    assert r.status_code == 200
    assert "x-fault" in r.headers["access-control-allow-headers"].lower()
