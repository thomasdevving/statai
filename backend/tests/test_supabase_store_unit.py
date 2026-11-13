"""Offline checks for the Supabase wiring (no network)."""

from __future__ import annotations

import pytest

from app.config import get_settings
from app.deps import get_store, reset_store
from app.store.supabase_store import resumable_endpoint_for


def test_resumable_endpoint_uses_direct_storage_host():
    assert (
        resumable_endpoint_for("https://abcdef.supabase.co")
        == "https://abcdef.storage.supabase.co/storage/v1/upload/resumable"
    )
    assert (
        resumable_endpoint_for("http://localhost:54321/")
        == "http://localhost:54321/storage/v1/upload/resumable"
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
