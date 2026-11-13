import json
import os
import subprocess
import sys

from conftest import AI_DIR
from PIL import Image


def test_fixture_shape(recipe):
    assert recipe.title == "Maki roll"
    assert [s.idx for s in recipe.steps] == [1, 2, 3, 4, 5, 6]
    s3 = recipe.step(3)
    w = s3.watch_for("rice_too_thick")
    assert w is not None
    assert w.headline == "Too much rice"
    assert w.fix == "Spread thinner, 2cm nori free"
    assert w.spoken == ("There's a bit too much rice — spread it thinner and leave two "
                        "centimetres of nori at the top.")
    assert s3.watch_for("rice_covers_top_edge") is not None
    assert recipe.step(4).watch_for("too_much_filling") is not None
    assert not recipe.step(2).watch_fors and not recipe.step(6).watch_fors
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


def _cli(*args, fake="1"):
    env = {**os.environ, "GHOSTCHEF_AI_FAKE": fake, "GHOSTCHEF_AI_FAKE_DELAY": "0",
           "PYTHONIOENCODING": "utf-8"}
    return subprocess.run([sys.executable, "-m", "ghostchef_ai", *args], cwd=AI_DIR, env=env,
                          capture_output=True, text=True, encoding="utf-8")


def test_cli_check_and_watch():
    r = _cli("check", "--step", "3", "--frame", "fixtures/images/step-3.jpg")
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["verdict"] == "fix"
    r = _cli("watch", "--step", "3", "--frame", "fixtures/images/step-3.jpg")
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["status"] == "ok"


def test_cli_models_and_live_config():
    r = _cli("models")
    assert r.returncode == 0 and set(json.loads(r.stdout)) == {"video", "check", "watch", "live"}
    r = _cli("live-config")
    assert r.returncode == 0 and "[CONTEXT]" in json.loads(r.stdout)["system_instruction"]


def test_cli_real_mode_reports_not_implemented():
    r = _cli("check", "--step", "3", "--frame", "fixtures/images/step-3.jpg", fake="0")
    assert r.returncode != 0
    assert "not implemented yet" in r.stderr
    assert "Traceback" not in r.stderr
