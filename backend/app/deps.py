"""Process-wide dependencies: the store singleton and settings."""

from __future__ import annotations

from app.config import Settings, get_settings
from app.store.base import Store
from app.store.memory import MemoryStore

__all__ = ["get_settings", "get_store", "reset_store"]

_store: Store | None = None


def _build_store(settings: Settings) -> Store:
    if settings.storage == "memory":
        return MemoryStore(settings.data_path, settings.public_base_url)
    if not settings.supabase_url or settings.supabase_service_key is None:
        raise RuntimeError(
            "STORAGE=supabase needs SUPABASE_URL and SUPABASE_SERVICE_KEY (backend/.env); "
            "set them or use STORAGE=memory"
        )
    from app.store.supabase_store import SupabaseStore

    return SupabaseStore(settings.supabase_url, settings.supabase_service_key.get_secret_value())


def get_store() -> Store:
    global _store
    if _store is None:
        _store = _build_store(get_settings())
    return _store


def reset_store() -> None:
    """Tests only: drop the singleton so the next get_store() builds a fresh one."""
    global _store
    _store = None
    # In-process caches built from the old store's data.
    from app.jobs import ingest
    from app.media import videocache
    from app.routers import live, sessions

    ingest.reset()
    videocache.clear()
    live.reset()
    sessions.reset()
