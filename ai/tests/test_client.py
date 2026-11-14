"""client.py without network: error mapping, timeout, call budget, provider switch, OpenAI path."""

import asyncio
import json
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from ghostchef_ai import client, config
from ghostchef_ai.errors import AIInvalidOutput, AIQuotaError, AITimeout, AIUnavailable


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.setenv("GHOSTCHEF_AI_FAKE", "0")
    monkeypatch.delenv("GHOSTCHEF_PROVIDER", raising=False)
    monkeypatch.delenv("GHOSTCHEF_MAX_CALLS", raising=False)
    client.reset_usage()
    client.reset_clients()
    client._openai_unsupported.clear()
    yield
    # Clients are reset at the start of the next test: here a test's monkeypatched stub
    # may still be in place (monkeypatch is undone after this fixture's teardown).
    client.reset_usage()


# ---------------------------------------------------------------- error mapping

class RateLimitError(Exception):
    status_code = 429


class ClientError(Exception):  # google-genai style: .code
    def __init__(self, code, msg):
        super().__init__(msg)
        self.code = code


class APITimeoutError(Exception):
    pass


class InternalServerError(Exception):
    status_code = 500


@pytest.mark.parametrize("exc,expected", [
    (RateLimitError("slow down"), AIQuotaError),
    (ClientError(429, "RESOURCE_EXHAUSTED"), AIQuotaError),
    (ClientError(400, "bad request"), AIUnavailable),
    (InternalServerError("boom"), AIUnavailable),
    (APITimeoutError("t"), AITimeout),
    (TimeoutError(), AITimeout),
    (json.JSONDecodeError("x", "doc", 0), AIInvalidOutput),
])
def test_map_error(exc, expected):
    assert isinstance(client.map_error(exc), expected)


def test_map_error_validation_error():
    class M(BaseModel):
        a: int
    with pytest.raises(Exception) as info:
        M.model_validate({"a": "nope"})
    assert isinstance(client.map_error(info.value), AIInvalidOutput)


def test_map_error_passes_ai_errors_through():
    e = AITimeout("x")
    assert client.map_error(e) is e


# ---------------------------------------------------------------- budget and timeout

async def test_timeout_maps_to_ai_timeout():
    with pytest.raises(AITimeout):
        await client.call_with_budget(asyncio.sleep(1), timeout_s=0.01)


async def test_provider_error_is_mapped():
    async def boom():
        raise RateLimitError("429")
    with pytest.raises(AIQuotaError):
        await client.call_with_budget(boom(), timeout_s=1)


async def test_call_cap(monkeypatch):
    monkeypatch.setenv("GHOSTCHEF_MAX_CALLS", "2")

    async def ok():
        return 1
    assert await client.call_with_budget(ok(), 1) == 1
    assert await client.call_with_budget(ok(), 1) == 1
    with pytest.raises(AIQuotaError, match="budget exhausted"):
        await client.call_with_budget(ok(), 1)
    assert client.usage.calls == 2


def test_provider_switch_and_defaults(monkeypatch):
    assert config.provider() == "gemini"
    assert config.max_calls() == 0
    monkeypatch.setenv("GHOSTCHEF_PROVIDER", "openai")
    assert config.provider() == "openai"
    assert config.max_calls() == 300
    assert config.model_ids()["live"] == "unsupported-on-openai"
    monkeypatch.setenv("GHOSTCHEF_PROVIDER", "anthropic")
    with pytest.raises(AIUnavailable):
        config.provider()


def test_missing_keys_are_clear_errors(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(AIUnavailable, match="OPENAI_API_KEY"):
        client.openai_client()
    with pytest.raises(AIUnavailable, match="GEMINI_API_KEY"):
        client.gemini_client()


# ---------------------------------------------------------------- OpenAI path, stubbed

class BadRequestError(Exception):
    status_code = 400


class StubCompletions:
    def __init__(self, reject=(), text='{"has_text": true}', finish="stop"):
        self.reject, self.text, self.finish, self.calls = set(reject), text, finish, []

    async def create(self, **params):
        self.calls.append(params)
        for p in self.reject:
            if p in params:
                raise BadRequestError(f"Unsupported parameter: '{p}' is not supported")
        return SimpleNamespace(
            model=params["model"] + "-2026",
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.text),
                                     finish_reason=self.finish)],
            usage=SimpleNamespace(prompt_tokens=100, completion_tokens=7),
        )


def _stub(monkeypatch, comp):
    monkeypatch.setenv("GHOSTCHEF_PROVIDER", "openai")
    stub = SimpleNamespace(chat=SimpleNamespace(completions=comp))
    monkeypatch.setattr(client, "openai_client", lambda: stub)


SCHEMA = {"type": "object", "properties": {"has_text": {"type": "boolean"}},
          "required": ["has_text"], "additionalProperties": False}


async def _call():
    return await client.image_json(model="m", prompt="p", images=[("IMG", b"\xff\xd8jpeg")],
                                   schema=SCHEMA, schema_name="t", timeout_s=2)


async def test_openai_request_shape(monkeypatch):
    comp = StubCompletions()
    _stub(monkeypatch, comp)
    res = await _call()
    assert res.data == {"has_text": True} and res.model == "m-2026"
    sent = comp.calls[0]
    assert sent["response_format"]["json_schema"]["strict"] is True
    img = sent["messages"][0]["content"][1]["image_url"]
    assert img["detail"] == "low" and img["url"].startswith("data:image/jpeg;base64,")
    assert client.usage.calls == 1 and client.usage.by_model["m"] == [1, 100, 7]


async def test_openai_drops_rejected_params_without_counting(monkeypatch):
    comp = StubCompletions(reject={"temperature", "reasoning_effort"})
    _stub(monkeypatch, comp)
    res = await _call()
    assert res.data == {"has_text": True}
    assert "temperature" not in comp.calls[-1] and "reasoning_effort" not in comp.calls[-1]
    assert client.usage.calls == 1  # rejected 400s are not counted
    await _call()  # learned: goes straight through
    assert len(comp.calls) == 4


async def test_openai_truncated_output_is_invalid(monkeypatch):
    _stub(monkeypatch, StubCompletions(text='{"has_', finish="length"))
    with pytest.raises(AIInvalidOutput):
        await _call()


async def test_openai_non_json_is_invalid(monkeypatch):
    _stub(monkeypatch, StubCompletions(text="not json"))
    with pytest.raises(AIInvalidOutput):
        await _call()


# ---------------------------------------------------------------- Gemini path, stubbed

class StubGemini:
    def __init__(self, text='{"has_text": true}', finish="STOP", reject_levels=()):
        self.text, self.finish, self.reject_levels, self.configs = text, finish, \
            set(reject_levels), []

    async def generate_content(self, *, model, contents, config):
        self.configs.append(config)
        tc = config.thinking_config
        if tc is not None and tc.thinking_level.name in self.reject_levels:
            raise ClientError(400, f"Thinking level {tc.thinking_level.name} is not supported "
                                   "for this model. Please retry with other thinking level.")
        return SimpleNamespace(
            text=self.text,
            candidates=[SimpleNamespace(finish_reason=SimpleNamespace(name=self.finish))],
            usage_metadata=SimpleNamespace(prompt_token_count=50, candidates_token_count=5,
                                           thoughts_token_count=2),
        )


def _stub_gemini(monkeypatch, stub):
    monkeypatch.setenv("GHOSTCHEF_PROVIDER", "gemini")
    client._gemini_no_thinking_cfg.clear()
    client._gemini_thinking_level.clear()
    fake = SimpleNamespace(aio=SimpleNamespace(models=stub))
    monkeypatch.setattr(client, "gemini_client", lambda *a, **k: fake)


async def test_gemini_requests_minimal_thinking(monkeypatch):
    stub = StubGemini()
    _stub_gemini(monkeypatch, stub)
    res = await _call()
    assert res.data == {"has_text": True}
    cfg = stub.configs[0]
    assert cfg.thinking_config.thinking_level.name == "MINIMAL"
    assert cfg.response_json_schema == SCHEMA
    assert client.usage.by_model["m"] == [1, 50, 7]  # thinking tokens count as output


async def test_gemini_steps_down_to_low_thinking(monkeypatch):
    stub = StubGemini(reject_levels={"MINIMAL"})
    _stub_gemini(monkeypatch, stub)
    assert (await _call()).data == {"has_text": True}
    assert stub.configs[-1].thinking_config.thinking_level.name == "LOW"
    assert client.usage.calls == 1  # the rejected request is not counted
    await _call()  # learned: goes straight to LOW
    assert len(stub.configs) == 3
    assert stub.configs[-1].thinking_config.thinking_level.name == "LOW"


async def test_gemini_drops_thinking_when_no_level_accepted(monkeypatch):
    stub = StubGemini(reject_levels={"MINIMAL", "LOW"})
    _stub_gemini(monkeypatch, stub)
    assert (await _call()).data == {"has_text": True}
    assert stub.configs[-1].thinking_config is None
    assert client.usage.calls == 1
    await _call()  # learned: no thinking config at all
    assert len(stub.configs) == 4


@pytest.mark.parametrize("text,finish,needle", [
    ('{"has_', "MAX_TOKENS", "cut off"),
    ("", "STOP", "empty answer"),
    ("not json", "STOP", "did not match"),
])
async def test_gemini_bad_outputs_are_invalid(monkeypatch, text, finish, needle):
    _stub_gemini(monkeypatch, StubGemini(text=text, finish=finish))
    with pytest.raises(AIInvalidOutput, match=needle):
        await _call()


def test_server_side_504_is_a_timeout():
    assert isinstance(client.map_error(ClientError(504, "DEADLINE_EXCEEDED")), AITimeout)


def test_bad_max_calls_is_an_ai_error(monkeypatch):
    monkeypatch.setenv("GHOSTCHEF_MAX_CALLS", "lots")
    with pytest.raises(AIUnavailable, match="whole number"):
        config.max_calls()
