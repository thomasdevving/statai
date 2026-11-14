"""Per-session latency ring buffers, error counts, and the latest frame / result for the
monitor (§4, BE-03.5).

In-process state: fine for one server process, which is how the backend runs.
"""

from __future__ import annotations

import secrets
import statistics
from collections import Counter, deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

RING = 500

Source = Literal["check", "watch"]


@dataclass
class LatestFrame:
    data: bytes
    at: datetime
    source: Source


@dataclass
class SessionMetrics:
    check_ms: deque[int] = field(default_factory=lambda: deque(maxlen=RING))
    watch_ms: deque[int] = field(default_factory=lambda: deque(maxlen=RING))
    errors: Counter[str] = field(default_factory=Counter)  # error code -> count
    latest_frame: LatestFrame | None = None
    # Authorises GET /sessions/{id}/latest-frame.jpg; only ever returned inside the monitor.
    frame_token: str = field(default_factory=lambda: secrets.token_urlsafe(24))
    last_result: dict[str, Any] | None = None  # {source, at, body}


_sessions: dict[str, SessionMetrics] = {}
# Process-wide error counts by code for /check and /watch, with or without a session.
errors_total: Counter[str] = Counter()


def for_session(session_id: str) -> SessionMetrics:
    return _sessions.setdefault(session_id, SessionMetrics())


def get(session_id: str) -> SessionMetrics | None:
    return _sessions.get(session_id)


def set_latest_frame(session_id: str, data: bytes, at: datetime, source: Source) -> None:
    for_session(session_id).latest_frame = LatestFrame(data=data, at=at, source=source)


def record(
    session_id: str,
    source: Source,
    latency_ms: int,
    body: dict[str, Any],
    at: datetime,
) -> None:
    m = for_session(session_id)
    (m.check_ms if source == "check" else m.watch_ms).append(latency_ms)
    m.last_result = {"source": source, "at": at, "body": body}


def record_error(session_id: str | None, code: str) -> None:
    errors_total[code] += 1
    if session_id:
        for_session(session_id).errors[code] += 1


def latency(session_id: str) -> dict[str, int | None]:
    m = _sessions.get(session_id) or SessionMetrics()

    def p50(xs: deque[int]) -> int | None:
        return int(statistics.median(xs)) if xs else None

    return {
        "check_p50_ms": p50(m.check_ms),
        "check_max_ms": max(m.check_ms) if m.check_ms else None,
        "watch_p50_ms": p50(m.watch_ms),
        "watch_max_ms": max(m.watch_ms) if m.watch_ms else None,
        "n_check": len(m.check_ms),
        "n_watch": len(m.watch_ms),
    }


def drop(session_id: str) -> None:
    _sessions.pop(session_id, None)


def reset() -> None:
    _sessions.clear()
    errors_total.clear()
