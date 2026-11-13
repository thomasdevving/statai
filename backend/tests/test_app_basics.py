from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth import require_demo_key
from app.errors import ApiError

from .conftest import KEY


def _envelope_ok(body: dict, code: str) -> None:
    assert set(body) == {"error"}
    err = body["error"]
    assert set(err) == {"code", "message", "retryable", "request_id"}
    assert err["code"] == code
    assert isinstance(err["message"], str) and err["message"]
    assert isinstance(err["retryable"], bool)


def test_health_body(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["contract_version"] == "2.0"
    assert body["storage"] == "memory"
    assert body["ai_mode"] in ("fake", "gemini", "unavailable")


def test_health_needs_no_key(client):
    assert client.get("/health", headers={"X-Demo-Key": "wrong"}).status_code == 200


def _protected_app(app):
    router = APIRouter(dependencies=[Depends(require_demo_key)])

    @router.get("/_protected")
    async def _p() -> dict:
        return {"ok": True}

    @router.get("/_boom")
    async def _boom() -> dict:
        raise RuntimeError("secret internal detail")

    @router.get("/_api_error")
    async def _api_error() -> dict:
        raise ApiError(409, "recipe_not_ready", "not ready", request_id="abc")

    app.include_router(router)
    return app


def test_401_missing_and_wrong_key(app):
    from fastapi.testclient import TestClient

    with TestClient(_protected_app(app), raise_server_exceptions=False) as c:
        r = c.get("/_protected")
        assert r.status_code == 401
        _envelope_ok(r.json(), "unauthorized")
        r = c.get("/_protected", headers={"X-Demo-Key": "nope"})
        assert r.status_code == 401
        _envelope_ok(r.json(), "unauthorized")
        assert c.get("/_protected", headers={"X-Demo-Key": KEY}).status_code == 200


def test_api_error_and_500_envelopes(app):
    from fastapi.testclient import TestClient

    with TestClient(_protected_app(app), raise_server_exceptions=False) as c:
        r = c.get("/_api_error", headers={"X-Demo-Key": KEY})
        assert r.status_code == 409
        _envelope_ok(r.json(), "recipe_not_ready")
        assert r.json()["error"]["request_id"] == "abc"
        r = c.get("/_boom", headers={"X-Demo-Key": KEY})
        assert r.status_code == 500
        _envelope_ok(r.json(), "internal")
        assert "secret" not in r.text


def test_404_envelope(client, auth):
    r = client.get("/no-such-route", headers=auth)
    assert r.status_code == 404
    _envelope_ok(r.json(), "not_found")


def test_422_envelope(client):
    # token query parameter is required
    r = client.put("/local-upload/videos/x/source.mp4", content=b"abc")
    assert r.status_code == 422
    _envelope_ok(r.json(), "validation_error")


def test_cors_allows_demo_key_header(client):
    r = client.options(
        "/health",
        headers={
            "Origin": "http://example.test",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "X-Demo-Key",
        },
    )
    assert r.status_code == 200
    assert "x-demo-key" in r.headers["access-control-allow-headers"].lower()
