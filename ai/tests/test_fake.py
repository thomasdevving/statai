from pathlib import Path

import pytest

import ghostchef_ai as gc
from ghostchef_ai import fake
from ghostchef_ai.schemas import CheckResult, LiveToken, RecipeDraft, WatchResult


async def test_check_sequence_fix_then_pass(recipe, big_frame):
    s3 = recipe.step(4)
    verdicts = [(await gc.check_frame(big_frame, s3, None)) for _ in range(4)]
    assert [r.verdict for r in verdicts] == ["fix", "pass", "fix", "pass"]
    first = verdicts[0]
    assert first.mistake_id == "filling_piled_center"
    assert first.headline == "Filling piled up"
    assert first.fix == "Spread it to the edges"
    assert first.confidence == 0.9 and first.model == "fake"
    assert verdicts[1].headline == "Looks right" and verdicts[1].fix == ""
    for r in verdicts:
        CheckResult.model_validate(r.model_dump())


async def test_check_counters_are_per_step(recipe, big_frame):
    assert (await gc.check_frame(big_frame, recipe.step(4), None)).verdict == "fix"
    assert (await gc.check_frame(big_frame, recipe.step(2), None)).verdict == "fix"
    assert (await gc.check_frame(big_frame, recipe.step(4), None)).verdict == "pass"


async def test_check_step_without_watch_fors_always_passes(recipe, big_frame):
    s2 = recipe.step(3)
    assert not s2.watch_fors
    assert {(await gc.check_frame(big_frame, s2, None)).verdict for _ in range(3)} == {"pass"}


async def test_check_small_frame_is_unsure(recipe):
    r = await gc.check_frame(b"\xff\xd8" + b"0" * 4000, recipe.step(4), None)
    assert r.verdict == "unsure"
    assert r.headline == "Can't tell" and r.fix == "Look straight down at board"
    assert r.confidence == 0.3
    # an unjudgeable frame does not advance the counter
    assert (await gc.check_frame(b"x" * 6000, recipe.step(4), None)).verdict == "fix"


async def test_watch_sequence(recipe, big_frame):
    s3 = recipe.step(4)
    statuses = [(await gc.watch_frame(big_frame, s3)) for _ in range(12)]
    assert [r.status for r in statuses] == ["ok"] * 3 + ["warn"] * 3 + ["ok"] * 3 + ["warn"] * 3
    warn = statuses[3]
    assert warn.mistake_id == "filling_piled_center" and warn.headline == "Filling piled up"
    assert statuses[0].mistake_id is None and statuses[0].headline == ""
    for r in statuses:
        WatchResult.model_validate(r.model_dump())


async def test_watch_step_without_watch_fors_always_ok(recipe, big_frame):
    assert {(await gc.watch_frame(big_frame, recipe.step(6))).status for _ in range(7)} == {"ok"}


async def test_reset_clears_counters(recipe, big_frame):
    await gc.check_frame(big_frame, recipe.step(4), None)
    fake.reset()
    assert (await gc.check_frame(big_frame, recipe.step(4), None)).verdict == "fix"


async def test_extract_recipe_returns_fixture(recipe):
    draft = await gc.extract_recipe(Path("ignored.mp4"), step_marks_s=[1.0, 2.0])
    assert draft == recipe
    titled = await gc.extract_recipe(Path("x.mp4"), title_hint="My roll")
    assert titled.title == "My roll"
    RecipeDraft.model_validate(titled.model_dump())


async def test_mint_live_token_fake(recipe):
    cfg = gc.build_live_config(recipe.title, None, recipe.transcript, recipe.steps)
    tok = await gc.mint_live_token(cfg)
    LiveToken.model_validate(tok.model_dump())
    assert tok.token == "fake-token" and tok.locked is False
    assert tok.new_session_expires_at < tok.expires_at


def test_build_live_config(recipe):
    cfg = gc.build_live_config(recipe.title, "Chef K", recipe.transcript, recipe.steps)
    assert cfg.model == "fake"
    assert cfg.response_modalities == ["AUDIO"] and cfg.voice is None and cfg.session_resumption
    for s in recipe.steps:
        assert s.title in cfg.system_instruction
    assert "every bite has flavour" in cfg.system_instruction
    assert "[CONTEXT]" in cfg.system_instruction
    names = [d["name"] for d in cfg.tools[0]["function_declarations"]]
    assert names == ["check_my_work", "next_step", "previous_step", "show_me",
                     "repeat_instruction"]


async def test_real_extract_reports_missing_video(monkeypatch):
    monkeypatch.setenv("GHOSTCHEF_AI_FAKE", "0")
    with pytest.raises(gc.AIUnavailable, match="video not found"):
        await gc.extract_recipe(Path("no-such-video.mp4"))


def test_public_surface_matches_contract():
    expected = {"WatchFor", "StepSpec", "RecipeDraft", "CheckResult", "WatchResult", "LiveConfig",
                "LiveToken", "AIError", "AITimeout", "AIQuotaError", "AIUnavailable",
                "AIInvalidOutput", "extract_recipe", "check_frame", "watch_frame",
                "build_live_config", "mint_live_token", "model_ids"}
    assert set(gc.__all__) == expected
    assert all(hasattr(gc, n) for n in expected)
    for sub in ("AITimeout", "AIQuotaError", "AIUnavailable", "AIInvalidOutput"):
        assert issubclass(getattr(gc, sub), gc.AIError)
