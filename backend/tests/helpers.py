from __future__ import annotations

import io
import uuid

from PIL import Image

from app.seed import SEED_RECIPE_ID, seed_step_id


def big_jpeg() -> bytes:
    """> 5 KB: the fake AI judges it."""
    from ghostchef_ai import config

    return (config.fixture_dir() / "images" / "step-3.jpg").read_bytes()


def tiny_jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (16, 16), (40, 40, 40)).save(buf, "JPEG")
    data = buf.getvalue()
    assert len(data) < 5000
    return data


def rid() -> str:
    return str(uuid.uuid4())


STEP3 = seed_step_id(SEED_RECIPE_ID, 3)
STEP2 = seed_step_id(SEED_RECIPE_ID, 2)


def post_frame(client, auth, endpoint, frame, step_id=STEP3, session_id=None, request_id=None):
    data = {"step_id": step_id, "request_id": request_id or rid()}
    if session_id:
        data["session_id"] = session_id
    return client.post(
        f"/{endpoint}",
        headers=auth,
        data=data,
        files={"frame": ("frame.jpg", frame, "image/jpeg")},
    )


def tiny_mp4() -> bytes:
    return b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + b"\x00" * 2048
