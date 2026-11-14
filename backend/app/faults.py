"""Quota cool-down for /watch and fault injection for failure rehearsals (BE-07.2)."""

from __future__ import annotations

import time
from types import ModuleType

from fastapi import Request

from app.config import Settings

WATCH_COOLDOWN_S = 10.0
FAULT_HEADER = "x-fault"

# time.monotonic() until which /watch answers 429 without calling the model (per process).
_watch_cooldown_until = 0.0


def watch_cooldown_active() -> bool:
    return time.monotonic() < _watch_cooldown_until


def start_watch_cooldown() -> None:
    global _watch_cooldown_until
    _watch_cooldown_until = time.monotonic() + WATCH_COOLDOWN_S


def reset() -> None:
    """Tests only."""
    global _watch_cooldown_until
    _watch_cooldown_until = 0.0


def raise_if_injected(request: Request, settings: Settings, g: ModuleType) -> None:
    """Raises the configured ghostchef_ai error instead of calling the model.

    Needs FAULT_INJECT_ENABLED=1, a FAULT_INJECT value and the request header `X-Fault: 1`;
    otherwise it does nothing.
    """
    if not settings.fault_injection_on or not settings.fault_inject:
        return
    if request.headers.get(FAULT_HEADER, "").strip() != "1":
        return
    exc = {
        "timeout": g.AITimeout,
        "quota": g.AIQuotaError,
        "unavailable": g.AIUnavailable,
    }[settings.fault_inject]
    raise exc(f"injected fault: {settings.fault_inject}")
