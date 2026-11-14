"""GET /sessions/{id}/latest-frame.jpg?t=<token> (BE-03.5).

The monitor shows this in an <img>, which cannot send X-Demo-Key, so the route is open in the
guard and authorised by the per-session random token returned only inside the monitor response.
"""

from __future__ import annotations

import hmac
import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response

from app import metrics
from app.errors import not_found
from app.request_ctx import request_base_url

router = APIRouter(tags=["sessions"])


def latest_frame_url(session_id: str, public_base_url: str | None) -> str | None:
    m = metrics.get(session_id)
    if m is None or m.latest_frame is None:
        return None
    base = (public_base_url or request_base_url.get() or "http://localhost:8000").rstrip("/")
    return f"{base}/sessions/{session_id}/latest-frame.jpg?t={m.frame_token}"


@router.get("/sessions/{session_id}/latest-frame.jpg")
async def latest_frame(session_id: str, t: Annotated[str, Query()] = "") -> Response:
    try:
        sid = str(uuid.UUID(session_id))
    except ValueError:
        raise not_found("frame") from None
    m = metrics.get(sid)
    # One answer for "no such session", "no frame yet" and "wrong token": nothing to probe.
    if (
        m is None
        or m.latest_frame is None
        or not t
        or not hmac.compare_digest(t.encode(), m.frame_token.encode())
    ):
        raise not_found("frame")
    return Response(
        content=m.latest_frame.data,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store"},
    )
