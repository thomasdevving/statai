"""Settings: the one place every environment variable is read (see backend/README.md)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    demo_api_key: SecretStr = SecretStr("dev-key")
    storage: Literal["memory", "supabase"] = "memory"
    data_dir: Path = Path(".data")

    supabase_url: str | None = None
    supabase_service_key: SecretStr | None = None

    # Read by ghostchef_ai itself; mirrored here only so the configuration is listed in one place.
    ghostchef_ai_fake: str = "1"
    gemini_api_key: SecretStr | None = None

    check_budget_s: float = Field(default=8.0, gt=0)
    watch_budget_s: float = Field(default=3.5, gt=0)
    signed_url_ttl_s: int = Field(default=7200, gt=0)
    max_video_mb: int = Field(default=500, gt=0)
    cors_origins: str = "*"
    # Failure rehearsal (BE-07.2): active only with FAULT_INJECT_ENABLED=1 and a request header.
    fault_inject: Literal["", "timeout", "quota", "unavailable"] = ""
    fault_inject_enabled: str = ""
    web_dir: Path = Path("../web")
    public_base_url: str | None = None

    @field_validator("supabase_url", "public_base_url", mode="before")
    @classmethod
    def _empty_to_none(cls, v: object) -> object:
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @field_validator("fault_inject", mode="before")
    @classmethod
    def _fault_normalised(cls, v: object) -> object:
        return v.strip() if isinstance(v, str) else v

    @field_validator("supabase_service_key", "gemini_api_key", mode="before")
    @classmethod
    def _empty_secret_to_none(cls, v: object) -> object:
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @property
    def fault_injection_on(self) -> bool:
        return self.fault_inject_enabled.strip() == "1"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def max_video_bytes(self) -> int:
        return self.max_video_mb * 1024 * 1024

    def resolve(self, p: Path) -> Path:
        """Relative paths are taken relative to backend/, not the process cwd."""
        return p if p.is_absolute() else (BACKEND_DIR / p).resolve()

    @property
    def data_path(self) -> Path:
        return self.resolve(self.data_dir)

    @property
    def web_path(self) -> Path:
        return self.resolve(self.web_dir)


@lru_cache
def get_settings() -> Settings:
    return Settings()
