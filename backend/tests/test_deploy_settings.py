"""BE-04: a Railway deployment must not start with the public default demo key."""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from app import main
from app.config import get_settings


@pytest.fixture
def settings_key(monkeypatch):
    def set_key(value: str) -> None:
        monkeypatch.setattr(get_settings(), "demo_api_key", SecretStr(value))

    return set_key


def test_local_default_key_allowed(monkeypatch, settings_key):
    for v in ("RAILWAY_ENVIRONMENT", "RAILWAY_ENVIRONMENT_NAME", "RAILWAY_ENVIRONMENT_ID"):
        monkeypatch.delenv(v, raising=False)
    settings_key("dev-key")
    main.check_deploy_settings()


@pytest.mark.parametrize("key", ["dev-key", "", "   "])
def test_railway_default_or_empty_key_refused(monkeypatch, settings_key, key):
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    settings_key(key)
    with pytest.raises(RuntimeError, match="DEMO_API_KEY"):
        main.check_deploy_settings()


def test_railway_real_key_allowed(monkeypatch, settings_key):
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    settings_key("a-long-random-production-key")
    main.check_deploy_settings()
