import json
from pathlib import Path

import pytest

from ghostchef_ai import fake
from ghostchef_ai.schemas import RecipeDraft

AI_DIR = Path(__file__).resolve().parents[1]
FIXTURE = AI_DIR / "fixtures" / "sushi_recipe.json"


@pytest.fixture(autouse=True)
def _fake_env(monkeypatch):
    monkeypatch.setenv("GHOSTCHEF_AI_FAKE", "1")
    monkeypatch.setenv("GHOSTCHEF_AI_FAKE_DELAY", "0")
    for k in ("GHOSTCHEF_MODEL_VIDEO", "GHOSTCHEF_MODEL_CHECK", "GHOSTCHEF_MODEL_WATCH",
              "GHOSTCHEF_MODEL_LIVE", "GHOSTCHEF_FIXTURE_DIR",
              # ai/.env may hold a real key: unit tests must never reach a paid API.
              "GEMINI_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    fake.reset()
    yield
    fake.reset()


@pytest.fixture
def recipe() -> RecipeDraft:
    return RecipeDraft.model_validate(json.loads(FIXTURE.read_text(encoding="utf-8")))


@pytest.fixture
def big_frame() -> bytes:
    return (AI_DIR / "fixtures" / "images" / "step-3.jpg").read_bytes()
