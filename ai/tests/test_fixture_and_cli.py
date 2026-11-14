import json
import os
import subprocess
import sys

import pytest
from conftest import AI_DIR
from PIL import Image


def test_fixture_shape(recipe):
    # The sandwich lesson (docs/DECISIONS-AND-RISKS.md D-19); strings as in API-CONTRACT §2.
    assert recipe.title == "Ham and cheese sandwich"
    assert [s.title for s in recipe.steps] == [
        "Lay out bread", "Spread", "Add lettuce", "Add fillings", "Close", "Cut"]
    s4 = recipe.step(4)
    assert s4.key_line == "One even layer, edge to edge"
    w = s4.watch_for("filling_piled_center")
    assert w is not None
    assert w.headline == "Filling piled up"
    assert w.fix == "Spread it to the edges"
    assert w.spoken == ("The filling is all in the middle — spread it out so it reaches the "
                        "edges of the bread.")
    assert recipe.step(2).watch_for("spread_misses_edges") is not None
    assert not recipe.step(3).watch_fors and not recipe.step(6).watch_fors
    assert "spread it right to the edges so every bite has flavour" in recipe.transcript
    assert recipe.transcript.startswith("[PLACEHOLDER NARRATION")
    assert 150 <= len(recipe.transcript.split()) <= 300
    times = [s.timestamp_s for s in recipe.steps]
    assert times == sorted(times)


def test_placeholder_images():
    for idx in range(1, 7):
        p = AI_DIR / "fixtures" / "images" / f"step-{idx}.jpg"
        assert p.stat().st_size > 5000
        with Image.open(p) as im:
            assert im.format == "JPEG" and im.size == (720, 1280)


def _cli(*args, fake="1", **extra_env):
    env = {**os.environ, "GHOSTCHEF_AI_FAKE": fake, "GHOSTCHEF_AI_FAKE_DELAY": "0",
           "PYTHONIOENCODING": "utf-8", **extra_env}
    return subprocess.run([sys.executable, "-m", "ghostchef_ai", *args], cwd=AI_DIR, env=env,
                          capture_output=True, text=True, encoding="utf-8")


def test_cli_check_and_watch():
    r = _cli("check", "--step", "4", "--frame", "fixtures/images/step-4.jpg")
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["verdict"] == "fix"
    r = _cli("watch", "--step", "4", "--frame", "fixtures/images/step-4.jpg")
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["status"] == "ok"


def test_cli_models_and_live_config():
    r = _cli("models")
    assert r.returncode == 0 and set(json.loads(r.stdout)) == {"video", "check", "watch", "live"}
    r = _cli("live-config")
    assert r.returncode == 0 and "[CONTEXT]" in json.loads(r.stdout)["system_instruction"]


@pytest.mark.parametrize("cmd", ["check", "watch"])
def test_cli_real_mode_without_key_is_a_clear_error(cmd):
    # An empty GEMINI_API_KEY is not overridden by ai/.env, so this never reaches the network.
    r = _cli(cmd, "--step", "4", "--frame", "fixtures/images/step-4.jpg", fake="0",
             GEMINI_API_KEY="", GHOSTCHEF_PROVIDER="gemini")
    assert r.returncode == 2
    assert "GEMINI_API_KEY is not set" in r.stderr
    assert "Traceback" not in r.stderr


def test_cli_watch_step_without_watch_fors_needs_no_key():
    r = _cli("watch", "--step", "3", "--frame", "fixtures/images/step-3.jpg", fake="0",
             GEMINI_API_KEY="", GHOSTCHEF_PROVIDER="gemini")
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert out["status"] == "ok" and out["model"] == "none"
