from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

# Defaults for every test: memory store, fake AI, no delays. Set before app modules import.
os.environ.setdefault("GHOSTCHEF_AI_FAKE", "1")
os.environ.setdefault("GHOSTCHEF_AI_FAKE_DELAY", "0")

from app import ai, metrics  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.deps import reset_store  # noqa: E402

KEY = "test-key"

requires_ai = pytest.mark.skipif(
    not ai.available(), reason="ghostchef_ai not installed (needs AI-01 on main)"
)


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch) -> Iterator[None]:
    monkeypatch.setenv("DEMO_API_KEY", KEY)
    monkeypatch.setenv("STORAGE", "memory")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("WEB_DIR", str(tmp_path / "no-web"))
    monkeypatch.setenv("PUBLIC_BASE_URL", "")
    monkeypatch.setenv("CORS_ORIGINS", "*")
    get_settings.cache_clear()
    reset_store()
    metrics.reset()
    if ai.available():
        from ghostchef_ai import fake

        fake.reset()
    yield
    get_settings.cache_clear()
    reset_store()


@pytest.fixture
def app():
    from app.main import create_app

    return create_app()


@pytest.fixture
def client(app) -> Iterator[TestClient]:
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def auth() -> dict[str, str]:
    return {"X-Demo-Key": KEY}
