"""Per-session latency ring buffers and the latest frame / result, for the monitor (§4).

In-process state: fine for one server process, which is how the backend runs.
"""

from __future__ import annotations

import statistics
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

RING = 500


@dataclass
class SessionMetrics:
    check_ms: deque[int] = field(default_factory=lambda: deque(maxlen=RING))
    watch_ms: deque[int] = field(default_factory=lambda: deque(maxlen=RING))
    last_frame_path: str | None = None  # bucket "frames"
    last_frame_at: datetime | None = None
    last_result: dict[str, Any] | None = None  # {source, at, body}


_sessions: dict[str, SessionMetrics] = {}


def for_session(session_id: str) -> SessionMetrics:
    return _sessions.setdefault(session_id, SessionMetrics())


def get(session_id: str) -> SessionMetrics | None:
    return _sessions.get(session_id)


def record(
    session_id: str,
    source: Literal["check", "watch"],
    latency_ms: int,
    body: dict[str, Any],
    at: datetime,
    frame_path: str | None,
) -> None:
    m = for_session(session_id)
    (m.check_ms if source == "check" else m.watch_ms).append(latency_ms)
    m.last_result = {"source": source, "at": at, "body": body}
    if frame_path:
        m.last_frame_path = frame_path
        m.last_frame_at = at


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
