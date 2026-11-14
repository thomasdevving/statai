from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path

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


HAVE_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
requires_ffmpeg = pytest.mark.skipif(
    not HAVE_FFMPEG, reason="ffmpeg/ffprobe not installed (needed from BE-06 on)"
)


def _ffmpeg(*args: str) -> None:
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", "-y", *args],
        check=True,
        capture_output=True,
        timeout=120,
    )


def _make_testsrc(path: Path, seconds: int, size: str, rate: int) -> Path:
    _ffmpeg(
        "-f", "lavfi", "-i", f"testsrc=duration={seconds}:size={size}:rate={rate}",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(path),
    )  # fmt: skip
    return path


@pytest.fixture(scope="session")
def testsrc_mp4(tmp_path_factory) -> Path:
    """5 s, 1920x1080, 10 fps."""
    if not HAVE_FFMPEG:
        pytest.skip("ffmpeg not installed")
    return _make_testsrc(tmp_path_factory.mktemp("media") / "testsrc.mp4", 5, "1920x1080", 10)


@pytest.fixture(scope="session")
def testsrc_rotated_mp4(testsrc_mp4, tmp_path_factory) -> Path:
    """Same video with a 90 degree display-matrix rotation (a phone held upright)."""
    out = tmp_path_factory.mktemp("media") / "rotated.mp4"
    try:
        _ffmpeg("-display_rotation", "90", "-i", str(testsrc_mp4), "-c", "copy", str(out))
    except subprocess.CalledProcessError:
        pytest.skip("this ffmpeg does not support -display_rotation")
    return out


@pytest.fixture(scope="session")
def testsrc_long_mp4(tmp_path_factory) -> Path:
    """8 s, 320x240."""
    if not HAVE_FFMPEG:
        pytest.skip("ffmpeg not installed")
    return _make_testsrc(tmp_path_factory.mktemp("media") / "long.mp4", 8, "320x240", 10)


@pytest.fixture(scope="session")
def testsrc_bytes(testsrc_mp4) -> bytes:
    return testsrc_mp4.read_bytes()


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
