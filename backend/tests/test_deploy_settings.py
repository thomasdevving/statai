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


@pytest.mark.parametrize("key", ["dev-key", " dev-key ", "", "   "])
def test_railway_default_or_empty_key_refused(monkeypatch, settings_key, key):
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    settings_key(key)
    with pytest.raises(RuntimeError, match="DEMO_API_KEY"):
        main.check_deploy_settings()


def test_railway_real_key_allowed(monkeypatch, settings_key):
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    settings_key("a-long-random-production-key")
    main.check_deploy_settings()


@pytest.fixture
def off_railway(monkeypatch):
    for v in ("RAILWAY_ENVIRONMENT", "RAILWAY_ENVIRONMENT_NAME", "RAILWAY_ENVIRONMENT_ID"):
        monkeypatch.delenv(v, raising=False)


@pytest.mark.parametrize("key", ["dev-key", " dev-key ", "", "   "])
@pytest.mark.parametrize("fake", ["0", "false", "no"])
def test_supabase_real_ai_default_key_refused(monkeypatch, off_railway, settings_key, key, fake):
    monkeypatch.setattr(get_settings(), "storage", "supabase")
    monkeypatch.setenv("GHOSTCHEF_AI_FAKE", fake)
    settings_key(key)
    with pytest.raises(RuntimeError, match="DEMO_API_KEY"):
        main.check_deploy_settings()


def test_supabase_real_ai_real_key_allowed(monkeypatch, off_railway, settings_key):
    monkeypatch.setattr(get_settings(), "storage", "supabase")
    monkeypatch.setenv("GHOSTCHEF_AI_FAKE", "0")
    settings_key("a-long-random-production-key")
    main.check_deploy_settings()


@pytest.mark.parametrize(("storage", "fake"), [("supabase", "1"), ("memory", "0"), ("memory", "1")])
def test_default_key_allowed_unless_supabase_and_real_ai(
    monkeypatch, off_railway, settings_key, storage, fake
):
    monkeypatch.setattr(get_settings(), "storage", storage)
    monkeypatch.setenv("GHOSTCHEF_AI_FAKE", fake)
    settings_key("dev-key")
    main.check_deploy_settings()
