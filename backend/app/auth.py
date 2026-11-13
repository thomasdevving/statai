"""X-Demo-Key dependency (API-CONTRACT §1)."""

from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import Depends, Header

from app.config import Settings, get_settings
from app.errors import ApiError


async def require_demo_key(
    settings: Annotated[Settings, Depends(get_settings)],
    x_demo_key: Annotated[str | None, Header()] = None,
) -> None:
    expected = settings.demo_api_key.get_secret_value().encode()
    given = (x_demo_key or "").encode()
    if not x_demo_key or not hmac.compare_digest(given, expected):
        raise ApiError(401, "unauthorized", "missing or wrong X-Demo-Key")
