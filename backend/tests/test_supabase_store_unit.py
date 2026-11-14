"""Offline checks for the Supabase wiring (no network)."""

from __future__ import annotations

import pytest

from app.config import get_settings
from app.deps import get_store, reset_store
from app.store.supabase_store import resumable_endpoint_for


def test_resumable_endpoint_uses_direct_storage_host():
    assert (
        resumable_endpoint_for("https://abcdef.supabase.co")
        == "https://abcdef.storage.supabase.co/storage/v1/upload/resumable/sign"
    )
    assert (
        resumable_endpoint_for("http://localhost:54321/")
        == "http://localhost:54321/storage/v1/upload/resumable/sign"
    )


def test_supabase_mode_without_credentials_fails_clearly(monkeypatch):
    monkeypatch.setenv("STORAGE", "supabase")
    monkeypatch.setenv("SUPABASE_URL", "")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "")
    get_settings.cache_clear()
    reset_store()
    with pytest.raises(RuntimeError, match="SUPABASE_URL and SUPABASE_SERVICE_KEY"):
        get_store()


def test_supabase_failure_maps_to_internal_without_key(monkeypatch, caplog):
    import asyncio

    from postgrest.exceptions import APIError

    from app.errors import ApiError
    from app.store.supabase_store import SupabaseStore

    class Boom:
        def table(self, name):
            raise APIError({"message": "boom token=SECRET123", "code": "XX000"})

    store = SupabaseStore("https://abcdef.supabase.co", "sb_secret_dontlog", client=Boom())
    with pytest.raises(ApiError) as exc:
        asyncio.run(store.list_recipes())
    assert exc.value.status == 500 and exc.value.code == "internal"
    assert "sb_secret_dontlog" not in caplog.text and "SECRET123" not in caplog.text


class _Query:
    """Records the PostgREST builder calls a store method makes."""

    def __init__(self, rows):
        self.calls, self.rows = [], rows

    def __getattr__(self, name):
        if name == "not_":
            return self

        def call(*a, **kw):
            self.calls.append((name, a))
            return self

        return call

    def execute(self):
        class R:
            data = self.rows

        return R()


class _Client:
    def __init__(self, rows):
        self.q = _Query(rows)

    def table(self, name):
        self.q.calls.append(("table", (name,)))
        return self.q


def test_list_sessions_started_before_uses_utc_z_cutoff():
    import asyncio
    from datetime import UTC, datetime

    from app.store.supabase_store import SupabaseStore

    client = _Client([])
    store = SupabaseStore("https://abcdef.supabase.co", "k", client=client)
    cutoff = datetime(2026, 11, 14, 10, 0, tzinfo=UTC)
    asyncio.run(store.list_sessions(started_before=cutoff, limit=5))
    assert ("lt", ("started_at", "2026-11-14T10:00:00Z")) in client.q.calls


def test_delete_session_filters_by_id_and_reports_result():
    import asyncio
    import uuid

    from app.store.supabase_store import SupabaseStore

    sid = str(uuid.uuid4())
    client = _Client([{"id": sid}])
    store = SupabaseStore("https://abcdef.supabase.co", "k", client=client)
    assert asyncio.run(store.delete_session(sid)) is True
    assert ("table", ("sessions",)) in client.q.calls and ("eq", ("id", sid)) in client.q.calls
    assert asyncio.run(store.delete_session("not-a-uuid")) is False
