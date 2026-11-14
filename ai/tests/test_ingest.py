"""ingest.py (AI-06) without network: prompt, repair rules, retry, upload lifecycle."""

import json
from types import SimpleNamespace

import pytest

from ghostchef_ai import client, ingest
from ghostchef_ai.errors import AIInvalidOutput, AIUnavailable
from ghostchef_ai.schemas import RecipeDraft


def raw_step(**over):
    s = {
        "title": "Spread the rice",
        "key_line": "Thin layer, leave 2cm top",
        "instruction": "Spread the rice thinly.",
        "chef_quote": "Most people use far too much.",
        "timestamp_s": 74.5,
        "clip_start_s": 72.0,
        "clip_end_s": 76.0,
        "success_criteria": ["Nori visible through the rice"],
        "watch_fors": [{"id": "rice_too_thick", "mistake": "Thick rice", "headline": "Too much",
                        "fix": "Spread thinner", "spoken": "Spread it thinner."}],
        "timer_s": None,
    }
    s.update(over)
    return s


def raw(*steps, **over):
    d = {"title": "Maki", "transcript": "Talk.", "steps": list(steps) or [raw_step()]}
    d.update(over)
    return d


# ------------------------------------------------------------------ prompt


def test_prompt_is_recipe_agnostic_and_mentions_hints():
    text = ingest.prompts.template("extract").lower()
    for word in ("sushi", "rice", "nori", "maki"):
        assert word not in text
    p = ingest.build_prompt("Maki roll", [12.4, 58.0])
    assert '"Maki roll"' in p and "12.4, 58" in p and "hints" in p
    assert "No step marks were given." in ingest.build_prompt(None, None)
    assert "No title hint" in ingest.build_prompt(None, [])


# ------------------------------------------------------------------ repair rules


def test_clamps_display_text():
    r = ingest.repair(raw(raw_step(
        title="Spread the cooked rice evenly now",
        key_line="one two three four five six seven eight nine ten",
        watch_fors=[{"id": "x", "mistake": "m", "headline": "a b c d e f",
                     "fix": "1 2 3 4 5 6 7 8 9 10", "spoken": "s"}])))
    s = r["steps"][0]
    assert s["title"] == "Spread the cooked rice"
    assert len(s["key_line"].split()) == 8
    assert s["watch_fors"][0]["headline"] == "a b c d"
    assert len(s["watch_fors"][0]["fix"].split()) == 8
    RecipeDraft.model_validate(r)


def _wf(i):
    return {"id": i, "mistake": "m", "headline": "h", "fix": "f", "spoken": "s"}


def test_slugifies_and_deduplicates_ids():
    r = ingest.repair(raw(raw_step(watch_fors=[_wf("Rice Too-Thick!"), _wf("rice too thick"),
                                               _wf("rice_too_thick"), _wf("9 lives")])))
    ids = [w["id"] for w in r["steps"][0]["watch_fors"]]
    assert ids == ["rice_too_thick", "rice_too_thick_2", "rice_too_thick_3", "m_9_lives"]
    RecipeDraft.model_validate(r)


def test_missing_id_falls_back_to_mistake_text():
    r = ingest.repair(raw(raw_step(watch_fors=[
        {"id": "", "mistake": "Filling piled high", "headline": "h", "fix": "f",
         "spoken": "s"}])))
    assert r["steps"][0]["watch_fors"][0]["id"] == "filling_piled_high"


def test_drops_incomplete_watch_fors():
    r = ingest.repair(raw(raw_step(watch_fors=[
        {"id": "a", "mistake": "m", "headline": "h", "fix": "", "spoken": "s"},
        {"id": "b", "mistake": "m", "headline": "h", "fix": "f"},
        "not a dict",
        _wf("c")])))
    assert [w["id"] for w in r["steps"][0]["watch_fors"]] == ["c"]


def test_sorts_by_timestamp_and_renumbers():
    r = ingest.repair(raw(raw_step(title="Third", timestamp_s=90),
                          raw_step(title="First", timestamp_s=5),
                          raw_step(title="Second", timestamp_s=40)))
    assert [(s["idx"], s["title"]) for s in r["steps"]] == [
        (1, "First"), (2, "Second"), (3, "Third")]
    RecipeDraft.model_validate(r)


def test_negative_and_bad_timestamps():
    r = ingest.repair(raw(raw_step(timestamp_s=-3, clip_start_s=-1, clip_end_s=2),
                          raw_step(timestamp_s="soon", clip_start_s=float("nan"))))
    a, b = r["steps"]
    assert a["timestamp_s"] == 0.0 and b["timestamp_s"] == 0.0
    assert (a["clip_start_s"], a["clip_end_s"]) == (0.0, 2.0)
    assert b["clip_start_s"] is None and b["clip_end_s"] is None


@pytest.mark.parametrize("start,end", [(10, 10), (10, 5), (None, 5), (5, None)])
def test_invalid_clip_window_becomes_null(start, end):
    s = ingest.repair(raw(raw_step(clip_start_s=start, clip_end_s=end)))["steps"][0]
    assert s["clip_start_s"] is None and s["clip_end_s"] is None


def test_unusable_steps_dropped_and_capped_at_ten():
    steps = [raw_step(title="", instruction="i"), raw_step(instruction="  ")]
    steps += [raw_step(title=f"Step {i}", timestamp_s=i) for i in range(12)]
    r = ingest.repair(raw(*steps))
    assert len(r["steps"]) == 10 and r["steps"][0]["title"] == "Step 0"


def test_title_falls_back_to_hint_then_default():
    assert ingest.repair(raw(title=""), title_hint="My roll")["title"] == "My roll"
    assert ingest.repair(raw(title=None))["title"] == "Untitled recipe"


def test_timer_and_quote_cleanup():
    s = ingest.repair(raw(raw_step(timer_s=0, chef_quote="  ")))["steps"][0]
    assert s["timer_s"] is None and s["chef_quote"] is None
    assert ingest.repair(raw(raw_step(timer_s=90.0)))["steps"][0]["timer_s"] == 90


def test_validate_rejects_empty_and_non_objects():
    with pytest.raises(AIInvalidOutput, match="no usable steps"):
        ingest.validate({"title": "t", "transcript": "", "steps": []})
    with pytest.raises(AIInvalidOutput):
        ingest.validate(["not", "an", "object"])


def test_fixture_survives_repair_unchanged(recipe):
    data = recipe.model_dump(mode="json")
    for s in data["steps"]:
        s.pop("idx")
    assert ingest.validate(data) == recipe


# ------------------------------------------------------------------ run_extract, stubbed


class ClientError(Exception):
    def __init__(self, code, msg):
        super().__init__(msg)
        self.code = code


def _resp(data, finish="STOP"):
    text = data if isinstance(data, str) else json.dumps(data)
    return SimpleNamespace(
        text=text,
        candidates=[SimpleNamespace(finish_reason=SimpleNamespace(name=finish))],
        usage_metadata=SimpleNamespace(prompt_token_count=1000, candidates_token_count=100,
                                       thoughts_token_count=10))


class StubFiles:
    def __init__(self, states=("PROCESSING", "ACTIVE")):
        self.states = list(states)
        self.deleted = []

    def _file(self):
        return SimpleNamespace(name="files/abc", state=SimpleNamespace(name=self.states.pop(0)))

    async def upload(self, *, file):
        self.uploaded = file
        return self._file()

    async def get(self, *, name):
        return self._file()

    async def delete(self, *, name):
        self.deleted.append(name)


class StubModels:
    def __init__(self, responses):
        self.responses = list(responses)
        self.configs = []

    async def generate_content(self, *, model, contents, config):
        self.configs.append(config)
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


@pytest.fixture
def video(tmp_path):
    p = tmp_path / "chef.mp4"
    p.write_bytes(b"\x00" * 64)
    return p


def _stub(monkeypatch, files, models):
    monkeypatch.setenv("GHOSTCHEF_AI_FAKE", "0")
    monkeypatch.delenv("GHOSTCHEF_PROVIDER", raising=False)
    monkeypatch.setattr(ingest, "POLL_INTERVAL_S", 0)
    client.reset_usage()
    stub = SimpleNamespace(aio=SimpleNamespace(files=files, models=models))
    monkeypatch.setattr(client, "gemini_client", lambda *a, **k: stub)


async def test_happy_path_waits_for_active_and_deletes(monkeypatch, video):
    files, models = StubFiles(), StubModels([_resp(raw())])
    _stub(monkeypatch, files, models)
    out = await ingest.run_extract(video, title_hint="Hint", step_marks_s=[3.0])
    assert out.draft.steps[0].watch_fors[0].id == "rice_too_thick"
    assert out.attempts == 1 and out.model == "gemini-3.5-flash"
    assert files.deleted == ["files/abc"]
    assert models.configs[0].thinking_config.thinking_level.name == "MINIMAL"
    assert client.usage.calls == 1


async def test_retries_once_on_invalid_output(monkeypatch, video):
    files, models = StubFiles(), StubModels([_resp("not json"), _resp(raw())])
    _stub(monkeypatch, files, models)
    out = await ingest.run_extract(video)
    assert out.attempts == 2 and files.deleted == ["files/abc"]


async def test_gives_up_after_second_invalid_output(monkeypatch, video):
    files = StubFiles()
    _stub(monkeypatch, files, StubModels([_resp("{}", "MAX_TOKENS"), _resp(raw(steps=[]))]))
    with pytest.raises(AIInvalidOutput):
        await ingest.run_extract(video)
    assert files.deleted == ["files/abc"]


async def test_steps_down_thinking_level_unbilled(monkeypatch, video):
    reject = ClientError(400, "Thinking level MINIMAL is not supported for this model.")
    models = StubModels([reject, _resp(raw())])
    _stub(monkeypatch, StubFiles(), models)
    await ingest.run_extract(video)
    assert models.configs[-1].thinking_config.thinking_level.name == "LOW"
    assert client.usage.calls == 1


async def test_processing_failure_still_deletes(monkeypatch, video):
    files = StubFiles(states=("PROCESSING", "FAILED"))
    _stub(monkeypatch, files, StubModels([]))
    with pytest.raises(AIUnavailable, match="processing failed"):
        await ingest.run_extract(video)
    assert files.deleted == ["files/abc"]


async def test_quota_error_is_mapped_and_deletes(monkeypatch, video):
    files = StubFiles()
    _stub(monkeypatch, files, StubModels([ClientError(429, "RESOURCE_EXHAUSTED")]))
    with pytest.raises(ingest.AIError) as info:
        await ingest.run_extract(video)
    assert type(info.value).__name__ == "AIQuotaError"
    assert files.deleted == ["files/abc"]


async def test_openai_provider_is_refused(monkeypatch, video):
    monkeypatch.setenv("GHOSTCHEF_PROVIDER", "openai")
    with pytest.raises(AIUnavailable, match="needs Gemini"):
        await ingest.run_extract(video)
