"""Per-request context the store needs to build absolute local URLs in memory mode."""

from __future__ import annotations

from contextvars import ContextVar

# Set by a middleware in app.main from the incoming request ("http://host:port").
request_base_url: ContextVar[str | None] = ContextVar("request_base_url", default=None)
