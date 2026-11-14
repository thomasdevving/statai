"""AI-05: build_live_config (pure) and mint_live_token with a stubbed SDK client (no network)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

import ghostchef_ai as gc
from ghostchef_ai import client, live

FIVE = ["check_my_work", "next_step", "previous_step", "show_me", "repeat_instruction"]


def _cfg(recipe, chef="Chef K"):
    return gc.build_live_config(recipe.title, chef, recipe.transcript, recipe.steps)


def test_instruction_has_steps_transcript_context_and_rules(recipe):
    cfg = _cfg(recipe)
    si = cfg.system_instruction
    for s in recipe.steps:
        assert f"Step {s.idx}: {s.title} — {s.instruction}" in si
        for c in s.success_criteria:
            assert c in si
    assert recipe.transcript.strip() in si
    assert "[CONTEXT]" in si
    assert "Chef: Chef K" in si and f"Recipe: {recipe.title}" in si
    assert "The chef doesn't cover that in this lesson" in si
    assert "do not see the camera" in si
    assert "{{" not in si


def test_tools_declare_exactly_the_five_without_parameters(recipe):
    cfg = _cfg(recipe)
    assert len(cfg.tools) == 1
    decls = cfg.tools[0]["function_declarations"]
    assert [d["name"] for d in decls] == FIVE
    assert all(d["description"] and "parameters" not in d for d in decls)
    # The four app-handled commands are non-blocking so their tool response can be SILENT.
    behaviors = {d["name"]: d.get("behavior") for d in decls}
    assert behaviors == {"check_my_work": "NON_BLOCKING", "next_step": "NON_BLOCKING",
                         "previous_step": "NON_BLOCKING", "show_me": "NON_BLOCKING",
                         "repeat_instruction": None}
    assert set(live.SILENT_FUNCTIONS) == {n for n, b in behaviors.items() if b}


def test_config_fields(recipe):
    cfg = _cfg(recipe, chef=None)
    assert cfg.response_modalities == ["AUDIO"] and cfg.voice is None
    assert cfg.session_resumption is True
    assert "Chef:" not in cfg.system_instruction.split("LESSON MATERIAL")[1]


def test_model_comes_from_model_ids(monkeypatch, recipe):
    monkeypatch.setenv("GHOSTCHEF_AI_FAKE", "0")
    monkeypatch.setenv("GHOSTCHEF_MODEL_LIVE", "some-live-model")
    assert _cfg(recipe).model == "some-live-model"


def test_long_transcript_keeps_beginning_and_end(recipe):
    words = [f"w{i}" for i in range(9000)]
    cfg = gc.build_live_config(recipe.title, None, " ".join(words), recipe.steps)
    si = cfg.system_instruction
    assert "w0 " in si and "w8999" in si
    assert "w5000 " not in si
    assert "3000 words from the middle of the transcript omitted" in si


# --------------------------------------------------------------------------- token, stubbed


class _FakeTokens:
    """Stands in for client.aio.auth_tokens. reject_full: raise like the API rejecting a lock."""

    def __init__(self, reject_full: Exception | None = None):
        self.reject_full = reject_full
        self.requests: list[dict] = []

    async def create(self, *, config):
        self.requests.append(config)
        full = "system_instruction" in config["live_connect_constraints"]["config"]
        if self.reject_full is not None and full:
            raise self.reject_full
        return SimpleNamespace(name="auth_tokens/abc", expire_time=config["expire_time"],
                               new_session_expire_time=config["new_session_expire_time"],
                               uses=config["uses"])


@pytest.fixture
def stub(monkeypatch):
    def install(tokens: _FakeTokens):
        seen = {}

        def fake_client(api_version=None):
            seen["api_version"] = api_version
            return SimpleNamespace(aio=SimpleNamespace(auth_tokens=tokens))

        monkeypatch.setenv("GHOSTCHEF_AI_FAKE", "0")
        monkeypatch.setattr(live, "gemini_client", fake_client)
        client.reset_usage()
        return seen
    return install


class _ClientError(Exception):
    def __init__(self, code, msg):
        super().__init__(msg)
        self.code = code


async def test_fully_locked_path(stub, recipe):
    tokens = _FakeTokens()
    seen = stub(tokens)
    cfg = _cfg(recipe)
    before = datetime.now(tz=UTC)
    tok = await gc.mint_live_token(cfg)
    assert seen["api_version"] == "v1beta"
    assert tok.locked is True and tok.token.startswith("auth_tokens/")
    assert len(tokens.requests) == 1
    req = tokens.requests[0]
    assert req["uses"] == 1 and req["lock_additional_fields"] == []
    assert timedelta(minutes=29) < tok.expires_at - before <= timedelta(minutes=31)
    assert timedelta(minutes=1) < tok.new_session_expires_at - before <= timedelta(minutes=3)
    c = req["live_connect_constraints"]
    assert c["model"] == cfg.model
    lc = c["config"]
    assert lc["system_instruction"] == cfg.system_instruction
    assert lc["tools"] == cfg.tools and lc["response_modalities"] == ["AUDIO"]
    # Resumption stays with the client: a locked empty one would replace its handle.
    assert "session_resumption" not in lc
    assert "output_audio_transcription" in lc and "context_window_compression" in lc


async def test_partially_locked_path(stub, recipe):
    tokens = _FakeTokens(reject_full=_ClientError(400, "INVALID_ARGUMENT: tools cannot be set"))
    stub(tokens)
    cfg = _cfg(recipe)
    tok = await gc.mint_live_token(cfg)
    assert tok.locked is False and tok.token == "auth_tokens/abc"
    assert len(tokens.requests) == 2
    partial = tokens.requests[1]
    assert partial["lock_additional_fields"] == []
    assert partial["live_connect_constraints"] == {
        "model": cfg.model, "config": {"response_modalities": ["AUDIO"]}}


@pytest.mark.parametrize("exc, err", [
    (_ClientError(429, "RESOURCE_EXHAUSTED"), gc.AIQuotaError),
    (TimeoutError(), gc.AITimeout),
])
async def test_quota_and_timeout_are_not_downgraded(stub, recipe, exc, err):
    tokens = _FakeTokens(reject_full=exc)
    stub(tokens)
    with pytest.raises(err):
        await gc.mint_live_token(_cfg(recipe))
    assert len(tokens.requests) == 1


async def test_outage_on_locked_request_is_not_downgraded(stub, recipe):
    """A 503 "high demand" must not silently produce an unlocked token (code review)."""
    tokens = _FakeTokens(reject_full=_ClientError(503, "UNAVAILABLE: high demand"))
    stub(tokens)
    with pytest.raises(gc.AIUnavailable):
        await gc.mint_live_token(_cfg(recipe))
    assert len(tokens.requests) == 1


async def test_rejected_lock_then_outage_raises_unavailable(stub, recipe):
    class RejectThenFail(_FakeTokens):
        async def create(self, *, config):
            self.requests.append(config)
            if len(self.requests) == 1:
                raise _ClientError(400, "INVALID_ARGUMENT: tools cannot be set")
            raise _ClientError(503, "UNAVAILABLE")
    tokens = RejectThenFail()
    stub(tokens)
    with pytest.raises(gc.AIUnavailable):
        await gc.mint_live_token(_cfg(recipe))
    assert len(tokens.requests) == 2


async def test_bad_token_name_is_rejected(stub, recipe):
    tokens = _FakeTokens()

    async def create(*, config):
        return SimpleNamespace(name="secret-token-value", expire_time=None,
                               new_session_expire_time=None)
    tokens.create = create
    stub(tokens)
    with pytest.raises(gc.AIUnavailable, match="name format") as info:
        await gc.mint_live_token(_cfg(recipe))
    assert "secret-token-value" not in str(info.value)  # never echo a token


async def test_missing_key_is_unavailable(monkeypatch, recipe):
    monkeypatch.setenv("GHOSTCHEF_AI_FAKE", "0")
    client.reset_clients()
    with pytest.raises(gc.AIUnavailable, match="GEMINI_API_KEY"):
        await gc.mint_live_token(_cfg(recipe))
    client.reset_clients()


def test_voice_goes_into_speech_config(recipe):
    cfg = _cfg(recipe).model_copy(update={"voice": "Kore"})
    sc = live.locked_setup(cfg)["config"]["speech_config"]
    assert sc["voice_config"]["prebuilt_voice_config"]["voice_name"] == "Kore"
