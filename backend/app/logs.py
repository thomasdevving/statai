"""Structured logging (BE-03.6): one JSON line per /check and /watch call.

Never logs frame bytes, keys, or tokens. The uvicorn access log has the `t` / `token` query
values redacted, because the latest-frame URL carries its token in the query string.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

CALL_LOGGER = "ghostchef.calls"
_call_log = logging.getLogger(CALL_LOGGER)

_SECRET_QUERY = re.compile(r"([?&](?:t|token)=)[^&\s]*")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        line: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            line.update(fields)
        if record.exc_info:
            line["exc"] = self.formatException(record.exc_info)
        return json.dumps(line, default=str)


class RedactQueryFilter(logging.Filter):
    """Masks `t=` and `token=` query values in uvicorn access log lines."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and args:
            record.args = tuple(
                _SECRET_QUERY.sub(r"\1***", a) if isinstance(a, str) else a for a in args
            )
        return True


def setup_logging() -> None:
    """Gives the `ghostchef` loggers a JSON handler at INFO, once per process."""
    root = logging.getLogger("ghostchef")
    if not any(getattr(h, "_ghostchef", False) for h in root.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        handler._ghostchef = True  # type: ignore[attr-defined]
        root.addHandler(handler)
    root.setLevel(logging.INFO)
    access = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, RedactQueryFilter) for f in access.filters):
        access.addFilter(RedactQueryFilter())


def log_call(fields: dict[str, Any]) -> None:
    _call_log.info("call", extra={"fields": fields})
