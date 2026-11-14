"""Regression tests for the BE-01 security review findings."""

from __future__ import annotations

import asyncio
import uuid

import httpx
import pytest

from app.seed import SEED_RECIPE_ID

from .conftest import KEY, requires_ai
from .helpers import tiny_mp4


def test_unauthenticated_body_is_not_parsed(client):
    # malformed multipart / JSON without a key: 401, not 400/422
    r = client.post(
        "/check", content=b"garbage", headers={"Content-Type": "multipart/form-data; boundary=x"}
    )
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"
    r = client.post("/recipes", content=b"{bad json", headers={"Content-Type": "application/json"})
    assert r.status_code == 401


def test_docs_and_openapi_not_served(client, auth):
    for path in ("/docs", "/openapi.json", "/redoc"):
        assert client.get(path).status_code == 401
        assert client.get(path, headers=auth).status_code == 404


def test_json_body_cap(client, auth):
    sid = str(uuid.uuid4())
    big = {"kind": "question", "payload": {"x": "a" * (70 * 1024)}}
    r = client.post(f"/sessions/{sid}/events", headers=auth, json=big)
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "payload_too_large"

    def chunks():  # no Content-Length: counted while streaming
        for _ in range(10):
            yield b"a" * 10_000

    r = client.post(
        f"/sessions/{sid}/events",
        content=chunks(),
        headers={**auth, "Content-Type": "application/json"},
    )
    assert r.status_code == 413


@requires_ai
@pytest.mark.parametrize("marks", ["[NaN]", "[Infinity]", "[1.0, Infinity]"])
def test_step_marks_reject_non_finite(client, auth, marks):
    body = '{"title": "Sandwich", "consent": true, "step_marks_s": ' + marks + "}"
    r = client.post("/recipes", content=body, headers={**auth, "Content-Type": "application/json"})
    assert r.status_code == 422


@requires_ai
def test_patch_step_rejects_non_finite_timestamp(client, auth):
    from .helpers import CHECKED_STEP

    r = client.patch(
        f"/steps/{CHECKED_STEP}",
        content='{"timestamp_s": NaN}',
        headers={**auth, "Content-Type": "application/json"},
    )
    assert r.status_code == 422


@requires_ai
async def test_concurrent_process_starts_one_job(app):
    from app.jobs import ingest

    transport = httpx.ASGITransport(app=app)
    h = {"X-Demo-Key": KEY}
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            created = (
                await c.post("/recipes", headers=h, json={"title": "Sandwich", "consent": True})
            ).json()
            up = await c.put(created["upload_url"].replace("http://t", ""), content=tiny_mp4())
            assert up.status_code == 200
            rid = created["recipe_id"]
            results = await asyncio.gather(
                *(c.post(f"/recipes/{rid}/process", headers=h) for _ in range(5))
            )
            codes = sorted(r.status_code for r in results)
            assert codes == [202, 409, 409, 409, 409]
            await ingest.wait_all()
            body = (await c.get(f"/recipes/{rid}", headers=h)).json()
            assert body["status"] == "review"


@requires_ai
def test_delete_revokes_upload_token(client, auth):
    created = client.post(
        "/recipes", headers=auth, json={"title": "Sandwich", "consent": True}
    ).json()
    assert client.delete(f"/recipes/{created['recipe_id']}", headers=auth).status_code == 204
    assert client.put(created["upload_url"], content=tiny_mp4()).status_code == 403


def test_seed_recipe_constant():
    assert uuid.UUID(SEED_RECIPE_ID).version == 4
