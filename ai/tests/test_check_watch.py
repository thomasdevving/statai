"""check.py and watch.py with a stubbed model call: every post-processing rule, errors, requests.

No network: client.image_json is replaced by a stub that returns canned JSON or raises.
"""

import asyncio
import json

import pytest

import ghostchef_ai as gc
from ghostchef_ai import check, client, prompts, watch
from ghostchef_ai.errors import AIInvalidOutput, AIQuotaError, AITimeout, AIUnavailable


class Stub:
    """Stands in for client.image_json. `answers` are dicts (returned) or exceptions (raised)."""

    def __init__(self, *answers, delay=0.0):
        self.answers, self.delay, self.calls = list(answers), delay, []

    async def __call__(self, **kw):
        self.calls.append(kw)
        if self.delay:
            await asyncio.sleep(self.delay)
        a = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if isinstance(a, BaseException):
            raise a
        return client.ImageJsonResult(a, kw["model"], 100, 20)


@pytest.fixture(autouse=True)
def _real_mode(monkeypatch):
    monkeypatch.setenv("GHOSTCHEF_AI_FAKE", "0")
    monkeypatch.setenv("GHOSTCHEF_PROVIDER", "gemini")


@pytest.fixture
def stub(monkeypatch):
    def install(*answers, delay=0.0):
        s = Stub(*answers, delay=delay)
        monkeypatch.setattr(client, "image_json", s)
        return s
    return install


def raw(verdict="pass", mistake_id=None, headline="", fix="", spoken="", confidence=0.9,
        evidence="filling on bread"):
    return {"evidence": evidence, "verdict": verdict, "mistake_id": mistake_id,
            "headline": headline, "fix": fix, "spoken": spoken, "confidence": confidence}


FRAME = b"\xff\xd8learner"
REF = b"\xff\xd8reference"


# ------------------------------------------------------------------ check: post-processing rules

async def test_check_rule1_unknown_mistake_id_becomes_none(stub, recipe):
    stub(raw("fix", "made_up_id", "Rice too wet", "Pat it dry with a towel", "Dry it."))
    r = await check.check_frame(FRAME, recipe.step(4), REF)
    assert r.verdict == "fix" and r.mistake_id is None
    assert (r.headline, r.fix, r.spoken) == ("Rice too wet", "Pat it dry with a towel", "Dry it.")


async def test_check_rule2_known_mistake_uses_recipe_strings(stub, recipe):
    stub(raw("fix", "filling_piled_center", "model words here", "model fix words", "model speech"))
    r = await check.check_frame(FRAME, recipe.step(4), REF)
    w = recipe.step(4).watch_for("filling_piled_center")
    assert r.mistake_id == "filling_piled_center"
    assert (r.headline, r.fix, r.spoken) == (w.headline, w.fix, w.spoken)


async def test_check_rule3_pass_clears_fix_and_mistake(stub, recipe):
    stub(raw("pass", "filling_piled_center", "", "Spread it out", "Nice work, that looks right."))
    r = await check.check_frame(FRAME, recipe.step(4), REF)
    assert r.verdict == "pass" and r.mistake_id is None and r.fix == ""
    assert r.headline == "Looks right"
    assert r.spoken == "Nice work, that looks right."


async def test_check_rule3_pass_keeps_model_headline_and_fills_empty_spoken(stub, recipe):
    stub(raw("pass", headline="Nice even layer", spoken=""))
    r = await check.check_frame(FRAME, recipe.step(4), REF)
    assert r.headline == "Nice even layer" and r.spoken == check.PASS_SPOKEN


async def test_check_rule4_clamps_words(stub, recipe):
    stub(raw("fix", None, "one two three four five six",
             "a b c d e f g h i j k", "Do the thing."))
    r = await check.check_frame(FRAME, recipe.step(4), REF)
    assert r.headline == "one two three four"
    assert r.fix == "a b c d e f g h"


@pytest.mark.parametrize("given,want", [(1.7, 1.0), (-0.2, 0.0), (0.66, 0.66)])
async def test_check_rule5_confidence_clamped(stub, recipe, given, want):
    stub(raw("unsure", None, "Can't see rice", "Look straight down", "Look down.", given))
    r = await check.check_frame(FRAME, recipe.step(4), REF)
    assert r.confidence == want and r.verdict == "unsure"
    assert r.headline == "Can't see rice"  # a confident-or-not unsure keeps its own words


@pytest.mark.parametrize("verdict,mid", [("pass", None), ("fix", "filling_piled_center")])
async def test_check_rule5_low_confidence_becomes_unsure(stub, recipe, verdict, mid):
    stub(raw(verdict, mid, "x", "y", "z", confidence=0.49))
    r = await check.check_frame(FRAME, recipe.step(4), REF)
    assert r.verdict == "unsure" and r.mistake_id is None
    assert (r.headline, r.fix, r.spoken) == (check.UNSURE_HEADLINE, check.UNSURE_FIX,
                                             check.UNSURE_SPOKEN)
    assert r.confidence == 0.49
    assert len(check.UNSURE_FIX.split()) <= 8


async def test_check_confidence_exactly_half_is_kept(stub, recipe):
    stub(raw("pass", confidence=0.5))
    assert (await check.check_frame(FRAME, recipe.step(4), REF)).verdict == "pass"


async def test_check_rule6_model_is_the_one_used(stub, recipe, monkeypatch):
    monkeypatch.setenv("GHOSTCHEF_MODEL_CHECK", "gemini-test-model")
    s = stub(raw("pass"))
    r = await check.check_frame(FRAME, recipe.step(4), REF)
    assert r.model == "gemini-test-model" == s.calls[0]["model"]


async def test_check_unsure_never_names_a_mistake_and_gets_defaults(stub, recipe):
    stub(raw("unsure", "filling_piled_center", "", "", "", 0.8))
    r = await check.check_frame(FRAME, recipe.step(4), REF)
    assert r.verdict == "unsure" and r.mistake_id is None
    assert (r.headline, r.fix, r.spoken) == (check.UNSURE_HEADLINE, check.UNSURE_FIX,
                                             check.UNSURE_SPOKEN)


async def test_check_fix_without_words_gets_defaults(stub, recipe):
    stub(raw("fix", None, "", "", ""))
    r = await check.check_frame(FRAME, recipe.step(4), REF)
    assert (r.headline, r.fix) == (check.FIX_HEADLINE, check.FIX_FIX)
    assert r.spoken == f"{check.FIX_HEADLINE}. {check.FIX_FIX}."


# ------------------------------------------------------------------ check: retry and errors

async def test_check_retries_once_on_invalid_output(stub, recipe):
    s = stub(AIInvalidOutput("cut off"), raw("pass"))
    out = await check.run_check(FRAME, recipe.step(4), REF)
    assert out.result.verdict == "pass" and out.attempts == 2 and len(s.calls) == 2


async def test_check_retries_on_schema_mismatch(stub, recipe):
    s = stub({"verdict": "maybe", "confidence": 0.9}, raw("fix", "filling_piled_center"))
    r = await check.check_frame(FRAME, recipe.step(4), REF)
    assert r.verdict == "fix" and len(s.calls) == 2


async def test_check_gives_up_after_second_invalid_output(stub, recipe):
    s = stub(AIInvalidOutput("bad"))
    with pytest.raises(AIInvalidOutput):
        await check.check_frame(FRAME, recipe.step(4), REF)
    assert len(s.calls) == 2


async def test_check_timeout(stub, recipe):
    stub(raw("pass"), delay=1.0)
    with pytest.raises(AITimeout):
        await check.check_frame(FRAME, recipe.step(4), REF, timeout_s=0.05)


class RateLimitError(Exception):
    status_code = 429


@pytest.mark.parametrize("exc", [AIQuotaError("quota"), RateLimitError("429")])
async def test_check_quota(stub, recipe, exc):
    s = stub(exc)
    with pytest.raises(AIQuotaError):
        await check.check_frame(FRAME, recipe.step(4), REF)
    assert len(s.calls) == 1  # no retry on quota


async def test_check_unavailable_is_not_retried(stub, recipe):
    s = stub(AIUnavailable("503 high demand"))
    with pytest.raises(AIUnavailable):
        await check.check_frame(FRAME, recipe.step(4), REF)
    assert len(s.calls) == 1


# ------------------------------------------------------------------ check: the request

async def test_check_request_with_reference(stub, recipe):
    s = stub(raw("pass"))
    await check.check_frame(FRAME, recipe.step(4), REF)
    kw = s.calls[0]
    assert kw["images"] == [(check.REF_LABEL, REF), (check.LEARNER_LABEL, FRAME)]
    assert check.REF_NOTE in kw["prompt"] and "{{" not in kw["prompt"]
    step, _ = json.JSONDecoder().raw_decode(kw["prompt"].split("as JSON:\n", 1)[1])
    assert step["title"] == "Add fillings"
    assert [w["id"] for w in step["watch_fors"]] == ["filling_piled_center"]
    assert kw["schema"]["properties"]["mistake_id"]["enum"] == ["filling_piled_center", None]
    assert kw["low_detail"] is check.LOW_DETAIL
    assert kw["max_output_tokens"] == check.MAX_OUTPUT_TOKENS


async def test_check_request_without_reference(stub, recipe):
    s = stub(raw("pass"))
    await check.check_frame(FRAME, recipe.step(4), None)
    kw = s.calls[0]
    assert kw["images"] == [(check.LEARNER_LABEL, FRAME)]
    assert check.NO_REF_NOTE in kw["prompt"]


async def test_check_step_without_watch_fors_schema(stub, recipe):
    s = stub(raw("fix", "anything", "Torn leaf", "Use a whole leaf", "Use one whole leaf."))
    r = await check.check_frame(FRAME, recipe.step(3), REF)
    assert s.calls[0]["schema"]["properties"]["mistake_id"] == {"type": "null"}
    assert r.mistake_id is None and r.verdict == "fix"


# ------------------------------------------------------------------ watch

def wraw(status="ok", mistake_id=None, confidence=0.9):
    return {"status": status, "mistake_id": mistake_id, "confidence": confidence}


async def test_watch_no_watch_fors_returns_ok_without_a_call(stub, recipe):
    s = stub(AssertionError("must not be called"))
    r = await watch.watch_frame(FRAME, recipe.step(3))
    assert r.status == "ok" and r.model == watch.NO_CALL_MODEL and not s.calls


async def test_watch_warn_copies_recipe_strings(stub, recipe):
    stub(wraw("warn", "spread_misses_edges", 0.83))
    r = await watch.watch_frame(FRAME, recipe.step(2))
    w = recipe.step(2).watch_for("spread_misses_edges")
    assert r.status == "warn" and r.mistake_id == w.id and r.confidence == 0.83
    assert (r.headline, r.fix, r.spoken) == (w.headline, w.fix, w.spoken)


@pytest.mark.parametrize("mid", [None, "not_in_step"])
async def test_watch_warn_with_null_or_unknown_id_is_ok(stub, recipe, mid):
    stub(wraw("warn", mid, 0.95))
    r = await watch.watch_frame(FRAME, recipe.step(4))
    assert r.status == "ok" and r.mistake_id is None
    assert (r.headline, r.fix, r.spoken) == ("", "", "")
    assert r.confidence == 0.0


async def test_watch_ok_has_empty_strings_and_clamped_confidence(stub, recipe):
    stub(wraw("ok", "filling_piled_center", 3.0))
    r = await watch.watch_frame(FRAME, recipe.step(4))
    assert r.status == "ok" and r.mistake_id is None
    assert (r.headline, r.fix, r.spoken) == ("", "", "") and r.confidence == 1.0


async def test_watch_request(stub, recipe, monkeypatch):
    monkeypatch.setenv("GHOSTCHEF_MODEL_WATCH", "gemini-watch-test")
    s = stub(wraw())
    r = await watch.watch_frame(FRAME, recipe.step(4))
    kw = s.calls[0]
    assert r.model == kw["model"] == "gemini-watch-test"
    assert kw["images"] == [(watch.FRAME_LABEL, FRAME)]
    assert kw["low_detail"] is True
    assert "- filling_piled_center: Filling is piled in the middle" in kw["prompt"]
    assert "Add fillings" in kw["prompt"] and "{{" not in kw["prompt"]
    assert set(kw["schema"]["properties"]) == {"status", "mistake_id", "confidence"}


async def test_watch_timeout(stub, recipe):
    stub(wraw(), delay=1.0)
    with pytest.raises(AITimeout):
        await watch.watch_frame(FRAME, recipe.step(4), timeout_s=0.05)


@pytest.mark.parametrize("exc", [AIQuotaError("quota"), RateLimitError("429")])
async def test_watch_quota(stub, recipe, exc):
    stub(exc)
    with pytest.raises(AIQuotaError):
        await watch.watch_frame(FRAME, recipe.step(4))


@pytest.mark.parametrize("answer", [AIInvalidOutput("cut"), {"status": "alarm"}])
async def test_watch_invalid_output_is_not_retried(stub, recipe, answer):
    s = stub(answer)
    with pytest.raises(AIInvalidOutput):
        await watch.watch_frame(FRAME, recipe.step(4))
    assert len(s.calls) == 1


# ------------------------------------------------------------------ prompts and public surface

@pytest.mark.parametrize("name", ["check", "watch"])
def test_prompts_are_recipe_agnostic(name):
    text = prompts.template(name).lower()
    for word in ("sushi", "maki", "nori", "rice", "sandwich", "bread", "ham", "lettuce"):
        assert word not in text, f"{name}.md mentions {word!r}"


def test_render_rejects_missing_or_unknown_placeholders():
    with pytest.raises(KeyError):
        prompts.render("watch", STEP_TITLE="x")
    with pytest.raises(KeyError):
        prompts.render("watch", STEP_TITLE="x", MISTAKES="y", EXTRA="z")


async def test_public_surface_dispatches_to_real_functions(stub, recipe):
    s = stub(raw("fix", "filling_piled_center"))
    r = await gc.check_frame(FRAME, recipe.step(4), REF)
    assert r.mistake_id == "filling_piled_center" and r.model != "fake" and len(s.calls) == 1
    stub(wraw("warn", "filling_piled_center"))
    w = await gc.watch_frame(FRAME, recipe.step(4))
    assert w.status == "warn" and w.model != "fake"


async def test_fake_mode_unchanged(stub, recipe, monkeypatch, big_frame):
    monkeypatch.setenv("GHOSTCHEF_AI_FAKE", "1")
    s = stub(AssertionError("fake mode must not call the model"))
    assert (await gc.check_frame(big_frame, recipe.step(4), None)).model == "fake"
    assert (await gc.watch_frame(big_frame, recipe.step(4))).model == "fake"
    assert not s.calls
