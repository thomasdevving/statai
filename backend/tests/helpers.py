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


def _fixture_facts() -> tuple[str, int, int, str, str]:
    """Facts the tests need, read from the AI track's fixture so they follow its content
    (sushi before D-19, the sandwich after) instead of hard-coding one recipe.

    Returns (title, checked_idx, plain_idx, first_mistake_id, first_mistake_headline).
    checked_idx is the first step with watch_fors (the fake AI answers fix / warn there);
    plain_idx is the first step without any (the fake AI always passes it).
    Without ghostchef_ai installed the AI tests are skipped, so placeholders are fine.
    """
    try:
        from ghostchef_ai import fake
    except ImportError:
        return ("", 1, 2, "", "")
    draft = fake.load_fixture()
    checked = next(s for s in draft.steps if s.watch_fors)
    plain = next(s for s in draft.steps if not s.watch_fors)
    w = checked.watch_fors[0]
    return (draft.title, checked.idx, plain.idx, w.id, w.headline)


RECIPE_TITLE, CHECKED_IDX, PLAIN_IDX, FIRST_MISTAKE_ID, FIRST_MISTAKE_HEADLINE = _fixture_facts()
CHECKED_STEP = seed_step_id(SEED_RECIPE_ID, CHECKED_IDX)
PLAIN_STEP = seed_step_id(SEED_RECIPE_ID, PLAIN_IDX)


def post_frame(
    client, auth, endpoint, frame, step_id=CHECKED_STEP, session_id=None, request_id=None
):
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
