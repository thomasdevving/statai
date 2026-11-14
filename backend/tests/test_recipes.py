from __future__ import annotations

import time
import uuid

import pytest

from app.seed import SEED_RECIPE_ID

from .conftest import requires_ai
from .helpers import tiny_mp4

pytestmark = requires_ai

STEP_FIELDS = {
    "id": str,
    "recipe_id": str,
    "idx": int,
    "title": str,
    "key_line": str,
    "instruction": str,
    "chef_quote": (str, type(None)),
    "timestamp_s": (int, float),
    "clip_start_s": (int, float, type(None)),
    "clip_end_s": (int, float, type(None)),
    "success_criteria": list,
    "watch_fors": list,
    "ref_image_url": (str, type(None)),
    "clip_url": (str, type(None)),
    "timer_s": (int, type(None)),
}


def assert_step(step: dict) -> None:
    assert set(step) == set(STEP_FIELDS)
    for k, t in STEP_FIELDS.items():
        assert isinstance(step[k], t), (k, step[k])
    for w in step["watch_fors"]:
        assert set(w) == {"id", "mistake", "headline", "fix", "spoken"}


def test_list_recipes_shape(client, auth):
    r = client.get("/recipes", headers=auth)
    assert r.status_code == 200
    items = r.json()["recipes"]
    seeded = next(x for x in items if x["id"] == SEED_RECIPE_ID)
    assert set(seeded) == {"id", "title", "chef_name", "status", "step_count", "created_at"}
    assert seeded["status"] == "published"
    assert seeded["step_count"] == 6
    assert seeded["created_at"].endswith("Z")
    assert client.get("/recipes?status=published", headers=auth).json()["recipes"]
    assert client.get("/recipes?status=review", headers=auth).json()["recipes"] == []
    assert client.get("/recipes?status=bogus", headers=auth).status_code == 422


def test_get_recipe_shape_and_image(client, auth):
    r = client.get(f"/recipes/{SEED_RECIPE_ID}", headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {
        "id",
        "title",
        "chef_name",
        "status",
        "error",
        "video_url",
        "step_marks_s",
        "transcript",
        "created_at",
        "steps",
    }
    assert body["video_url"] is None
    assert isinstance(body["step_marks_s"], list)
    assert [s["idx"] for s in body["steps"]] == [1, 2, 3, 4, 5, 6]
    for s in body["steps"]:
        assert_step(s)
    from .helpers import CHECKED_IDX, FIRST_MISTAKE_ID

    checked = body["steps"][CHECKED_IDX - 1]
    assert checked["watch_fors"][0]["id"] == FIRST_MISTAKE_ID
    url = checked["ref_image_url"]
    img = client.get(url)  # signed URL, no key
    assert img.status_code == 200
    assert img.headers["content-type"] == "image/jpeg"
    assert img.content[:2] == b"\xff\xd8"


def test_recipe_auth_and_404(client, auth):
    assert client.get("/recipes").status_code == 401
    r = client.get(f"/recipes/{uuid.uuid4()}", headers=auth)
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"
    assert client.get("/recipes/not-a-uuid", headers=auth).status_code == 422


def _create(client, auth, **over):
    body = {
        "title": "Ham and cheese sandwich",
        "chef_name": "Aki",
        "step_marks_s": [1.5, 3.0],
        "consent": True,
    }
    body.update(over)
    return client.post("/recipes", headers=auth, json=body)


def test_create_recipe_shape(client, auth):
    r = _create(client, auth)
    assert r.status_code == 201
    body = r.json()
    assert set(body) == {
        "recipe_id",
        "status",
        "upload_url",
        "upload_token",
        "bucket",
        "object_path",
        "resumable_endpoint",
        "upload_expires_at",
    }
    assert body["status"] == "uploading"
    assert body["bucket"] == "videos"
    assert body["object_path"] == f"{body['recipe_id']}/source.mp4"
    assert body["resumable_endpoint"] is None
    assert body["upload_token"] in body["upload_url"]
    detail = client.get(f"/recipes/{body['recipe_id']}", headers=auth).json()
    assert detail["status"] == "uploading"
    assert detail["step_marks_s"] == [1.5, 3.0]
    assert detail["steps"] == []


@pytest.mark.parametrize(
    "over",
    [
        {"title": "x" * 81},
        {"title": ""},
        {"consent": False},
        {"consent": None},
        {"step_marks_s": [3.0, 1.0]},
        {"step_marks_s": [-1.0]},
    ],
)
def test_create_recipe_validation(client, auth, over):
    r = _create(client, auth, **over)
    assert r.status_code == 422, over
    assert r.json()["error"]["code"] == "validation_error"


def test_create_recipe_missing_consent(client, auth):
    r = client.post("/recipes", headers=auth, json={"title": "Sandwich"})
    assert r.status_code == 422


def test_upload_process_review_publish_flow(client, auth):
    created = _create(client, auth).json()
    rid = created["recipe_id"]

    r = client.post(f"/recipes/{rid}/process", headers=auth)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "upload_missing"

    bad = created["upload_url"].split("?token=")[0] + "?token=wrong"
    assert client.put(bad, content=tiny_mp4()).status_code == 403

    up = client.put(
        created["upload_url"], content=tiny_mp4(), headers={"Content-Type": "video/mp4"}
    )
    assert up.status_code == 200

    r = client.post(f"/recipes/{rid}/process", headers=auth)
    assert r.status_code == 202
    assert r.json() == {"recipe_id": rid, "status": "processing"}

    r = client.post(f"/recipes/{rid}/process", headers=auth)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "recipe_not_ready"

    deadline = time.monotonic() + 5
    status = None
    while time.monotonic() < deadline:
        body = client.get(f"/recipes/{rid}", headers=auth).json()
        status = body["status"]
        if status in ("review", "failed"):
            break
        time.sleep(0.05)
    assert status == "review", body
    assert body["title"] == "Ham and cheese sandwich"  # the title given to POST /recipes
    assert len(body["steps"]) == 6
    assert body["video_url"] and "/local-files/videos/" in body["video_url"]
    assert all(s["ref_image_url"] for s in body["steps"])

    r = client.post(f"/recipes/{rid}/publish", headers=auth)
    assert r.status_code == 200
    assert r.json()["status"] == "published"
    assert r.json()["video_url"] is None


def test_publish_while_processing_409(client, auth):
    import asyncio

    from app.deps import get_store

    created = _create(client, auth).json()
    rid = created["recipe_id"]
    asyncio.run(get_store().update_recipe(rid, status="processing"))
    r = client.post(f"/recipes/{rid}/publish", headers=auth)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "recipe_not_ready"


def test_publish_needs_ref_images(client, auth):
    import asyncio

    from app.deps import get_store

    store = get_store()
    steps = asyncio.run(store.list_steps(SEED_RECIPE_ID))
    asyncio.run(store.update_recipe(SEED_RECIPE_ID, status="review"))
    asyncio.run(store.update_step(steps[0].id, ref_image_path=None))
    r = client.post(f"/recipes/{SEED_RECIPE_ID}/publish", headers=auth)
    assert r.status_code == 409


def test_patch_recipe(client, auth):
    r = client.patch(f"/recipes/{SEED_RECIPE_ID}", headers=auth, json={"title": "Better sandwich"})
    assert r.status_code == 200
    assert r.json()["title"] == "Better sandwich"
    assert len(r.json()["steps"]) == 6
    r = client.patch(f"/recipes/{SEED_RECIPE_ID}", headers=auth, json={"title": "x" * 81})
    assert r.status_code == 422
    r = client.patch(f"/recipes/{SEED_RECIPE_ID}", headers=auth, json={"title": None})
    assert r.status_code == 422
    assert client.patch(f"/recipes/{uuid.uuid4()}", headers=auth, json={}).status_code == 404


def test_patch_step(client, auth):
    from .helpers import CHECKED_STEP

    r = client.patch(
        f"/steps/{CHECKED_STEP}",
        headers=auth,
        json={"title": "Spread to the edges", "timestamp_s": 80.5, "timer_s": 30},
    )
    assert r.status_code == 200
    body = r.json()
    assert_step(body)
    assert (body["title"], body["timestamp_s"], body["timer_s"]) == (
        "Spread to the edges",
        80.5,
        30,
    )
    for bad in (
        {"title": "one two three four five"},
        {"key_line": "one two three four five six seven eight nine"},
        {
            "watch_fors": [
                {"id": "x", "mistake": "m", "headline": "a b c d e", "fix": "f", "spoken": "s"}
            ]
        },
        {
            "watch_fors": [
                {
                    "id": "x",
                    "mistake": "m",
                    "headline": "h",
                    "fix": "1 2 3 4 5 6 7 8 9",
                    "spoken": "s",
                }
            ]
        },
        {
            "watch_fors": [
                {"id": "Bad-Id", "mistake": "m", "headline": "h", "fix": "f", "spoken": "s"}
            ]
        },
        {"title": None},
        {"timestamp_s": -1},
    ):
        r = client.patch(f"/steps/{CHECKED_STEP}", headers=auth, json=bad)
        assert r.status_code == 422, bad
        assert r.json()["error"]["code"] == "validation_error"
    assert client.patch(f"/steps/{uuid.uuid4()}", headers=auth, json={}).status_code == 404


def test_delete_recipe_cascades(client, auth):
    from .helpers import big_jpeg, post_frame

    sess = client.post(
        "/sessions", headers=auth, json={"recipe_id": SEED_RECIPE_ID, "client": "web-sim"}
    ).json()
    assert (
        post_frame(client, auth, "check", big_jpeg(), session_id=sess["session_id"]).status_code
        == 200
    )
    body = client.get(f"/recipes/{SEED_RECIPE_ID}", headers=auth).json()
    img_url = body["steps"][0]["ref_image_url"]
    monitor = client.get(f"/sessions/{sess['session_id']}/monitor", headers=auth).json()
    frame_url = monitor["last_frame_url"]
    assert client.get(frame_url).status_code == 200

    r = client.delete(f"/recipes/{SEED_RECIPE_ID}", headers=auth)
    assert r.status_code == 204
    assert client.get(f"/recipes/{SEED_RECIPE_ID}", headers=auth).status_code == 404
    assert client.get(f"/sessions/{sess['session_id']}", headers=auth).status_code == 404
    assert client.get(img_url).status_code == 404
    assert client.get(frame_url).status_code == 404
    assert client.delete(f"/recipes/{SEED_RECIPE_ID}", headers=auth).status_code == 404


def test_stale_upload_becomes_failed(client, auth):
    import asyncio
    from datetime import timedelta

    from app.deps import get_store
    from app.store.base import utcnow

    rid = _create(client, auth).json()["recipe_id"]
    asyncio.run(get_store().update_recipe(rid, created_at=utcnow() - timedelta(hours=3)))
    body = client.get(f"/recipes/{rid}", headers=auth).json()
    assert body["status"] == "failed"
    assert body["error"] == "upload never completed"
