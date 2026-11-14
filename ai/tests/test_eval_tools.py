"""AI-07 tooling without network: eval runner (fake mode), debounce replay, clip intake."""

import csv
import importlib.util
import json
import shutil
import subprocess
import sys

import pytest
from conftest import AI_DIR

from ghostchef_ai import eval as ev

HAS_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
COLUMNS = ["case_id", "file", "step_idx", "split", "label", "mistake_id", "labeller",
           "source_device", "notes"]


def _load(name):
    spec = importlib.util.spec_from_file_location(name, AI_DIR / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod  # dataclasses need the module registered
    spec.loader.exec_module(mod)
    return mod


def _eval_dir(tmp_path, rows):
    """A tiny eval set: real fixture images as frames (big enough for the fake's rules)."""
    for split in ("dev", "heldout"):
        (tmp_path / "frames" / split).mkdir(parents=True)
    img = (AI_DIR / "fixtures" / "images" / "step-4.jpg").read_bytes()
    with (tmp_path / "cases.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        for i, (split, label, mid, size) in enumerate(rows):
            name = f"f{i}.jpg"
            (tmp_path / "frames" / split / name).write_bytes(img if size == "big" else b"x" * 100)
            w.writerow({"case_id": f"c{i}", "file": f"frames/{split}/{name}", "step_idx": "4",
                        "split": split, "label": label, "mistake_id": mid, "labeller": "AK",
                        "source_device": "test", "notes": ""})
    return tmp_path / "cases.csv"


# ------------------------------------------------------------------ eval runner


def test_load_cases_filters_split_and_unlabelled(tmp_path):
    cases_csv = _eval_dir(tmp_path, [("dev", "pass", "", "big"), ("dev", "", "", "big"),
                                     ("heldout", "fix", "filling_piled_center", "big")])
    dev = ev.load_cases(cases_csv, "dev")
    assert [c.case_id for c in dev] == ["c0"]
    assert ev.load_cases(cases_csv, "heldout")[0].mistake_id == "filling_piled_center"


def test_check_metrics_counts():
    R = ev.Row
    rows = [R("a", "f", 4, "fix", "filling_piled_center", "pass", latency_ms=100),
            R("b", "f", 4, "fix", "filling_piled_center", "fix", "filling_piled_center",
              latency_ms=300),
            R("c", "f", 4, "pass", "", "fix", latency_ms=200),
            R("d", "f", 4, "unsure", "", "unsure", latency_ms=50),
            R("e", "f", 4, "pass", "", "unsure", latency_ms=60),
            R("x", "f", 4, "pass", "", error="AITimeout: slow")]
    m = ev.check_metrics(rows)
    assert (m["false_approvals"], m["n_fix"]) == (1, 2)
    assert (m["false_rejections"], m["n_pass"]) == (1, 2)
    assert (m["appropriate_unsure"], m["n_unsure"]) == (1, 1)
    assert m["wrong_unsure"] == 1 and m["right_mistake_id"] == 1 and m["errors"] == 1
    assert (m["latency_p50_ms"], m["latency_max_ms"]) == (100, 300)


def test_watch_metrics_threshold():
    R = ev.Row
    rows = [R("a", "f", 4, "fix", "filling_piled_center", "warn", "filling_piled_center", 0.9),
            R("b", "f", 4, "fix", "filling_piled_center", "warn", "filling_piled_center", 0.6),
            R("c", "f", 4, "pass", "", "warn", "filling_piled_center", 0.95),
            R("d", "f", 4, "pass", "", "ok", "", 0.9)]
    m = ev.watch_metrics(rows, 0.7)
    assert (m["detected"], m["n_fix"], m["false_warnings"], m["n_not_fix"]) == (1, 2, 1, 2)


@pytest.mark.parametrize("config", ["full", "no-ref", "generic"])
def test_runner_end_to_end_in_fake_mode(tmp_path, config):
    cases_csv = _eval_dir(tmp_path, [("dev", "fix", "filling_piled_center", "big"),
                                     ("dev", "pass", "", "big"),
                                     ("dev", "unsure", "", "small")])
    out = tmp_path / "results"
    assert ev.main(["--split", "dev", "--config", config, "--cases", str(cases_csv),
                    "--out", str(out), "--concurrency", "1"]) == 0
    js = next(out.glob("*.json"))
    assert js.name.endswith(f"-dev-{config}-check-FAKE.json")
    data = json.loads(js.read_text(encoding="utf-8"))
    assert data["meta"]["fake"] is True and data["metrics"]["n"] == 3
    assert data["metrics"]["appropriate_unsure"] == 1  # the tiny frame -> fake unsure
    md = js.with_suffix(".md").read_text(encoding="utf-8")
    assert "FAKE MODE, not an evaluation result" in md and "False approvals" in md


def test_runner_watch_mode_and_guards(tmp_path):
    cases_csv = _eval_dir(tmp_path, [("dev", "fix", "filling_piled_center", "big"),
                                     ("heldout", "pass", "", "big")])
    out = tmp_path / "results"
    assert ev.main(["--split", "dev", "--mode", "watch", "--cases", str(cases_csv),
                    "--out", str(out)]) == 0
    assert ev.main(["--split", "heldout", "--cases", str(cases_csv), "--out", str(out)]) == 2
    assert ev.main(["--split", "dev", "--mode", "watch", "--config", "generic",
                    "--cases", str(cases_csv), "--out", str(out)]) == 2
    empty = _eval_dir(tmp_path / "e", [("dev", "", "", "big")])
    assert ev.main(["--split", "dev", "--cases", str(empty), "--out", str(out)]) == 1


def test_generic_prompt_has_only_the_step_title():
    text = ev.prompts.render("generic_check", STEP_TITLE="Add fillings")
    assert "Add fillings" in text and "{{" not in text


# ------------------------------------------------------------------ debounce replay


def test_debounce_two_in_a_row_same_id():
    r = [(0, "warn", "a", 0.9), (2.5, "warn", "a", 0.9), (5, "warn", "a", 0.9)]
    assert ev.debounce_alerts(r, 0.7) == [(2.5, "a")]


def test_debounce_breaks_on_ok_other_id_or_low_confidence():
    r = [(0, "warn", "a", 0.9), (2.5, "ok", None, 0.9), (5, "warn", "a", 0.9),
         (7.5, "warn", "b", 0.9), (10, "warn", "b", 0.5), (12.5, "warn", "b", 0.9)]
    assert ev.debounce_alerts(r, 0.7) == []


def test_debounce_mutes_after_alert():
    r = [(t, "warn", "a", 0.9) for t in (0, 2.5, 5, 7.5, 20, 22.5, 25)]
    # The streak keeps counting while muted, so the next alert comes as soon as the mute
    # ends (22.5 = 2.5 + 20), not two frames later.
    assert ev.debounce_alerts(r, 0.7, mute_s=20) == [(2.5, "a"), (22.5, "a")]


def test_watch_clip_score():
    wc = _load("watch_clip")
    assert wc.score([], "none", None, None, 60) == {
        "alerts": 0, "false_alerts": 0, "false_alerts_per_min": 0.0}
    s = wc.score([(1.0, "x"), (7.5, "filling_piled_center"), (30, "filling_piled_center")],
                 "filling_piled_center", 5.0, 18.0, 40)
    assert s["detected"] and s["detection_delay_s"] == 2.5
    assert s["false_alerts"] == 2 and s["alerts_after_fix"] == 1


# ------------------------------------------------------------------ clip intake


def _manifest(path, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["clip_id", "split", "step_idx", "intent", "mistake_id", "notes"])
        w.writerows(rows)


def test_manifest_validation(tmp_path):
    ic = _load("intake_clips")
    m = tmp_path / "clips.csv"
    _manifest(m, [["V1", "dev", "4", "fix", "filling_piled_center", ""],
                  ["v1", "dev", "4", "pass", "", ""], ["V2", "nope", "", "", "", ""],
                  ["V3", "heldout", "", "pass", "", ""], ["C1", "expert", "", "", "", ""]])
    clips, errors = ic.read_manifest(m)
    assert any("duplicate" in e for e in errors)
    assert any("split must be" in e for e in errors)
    assert any("need a step_idx" in e for e in errors)
    assert [c.clip_id for c in clips] == ["V1", "v1", "C1"]


def test_find_file_matches_id_prefix_only(tmp_path):
    ic = _load("intake_clips")
    for n in ("V1.mp4", "v1-filling.MOV", "V10.mp4", "V1.txt"):
        (tmp_path / n).write_bytes(b"x")
    assert {p.name for p in ic.find_file(tmp_path, "V1")} == {"V1.mp4", "v1-filling.MOV"}
    assert [p.name for p in ic.find_file(tmp_path, "V10")] == ["V10.mp4"]


def test_committed_manifest_has_the_right_header():
    ic = _load("intake_clips")
    with (AI_DIR / "eval" / "clips.csv").open(newline="", encoding="utf-8") as f:
        assert next(csv.reader(f)) == ic.MANIFEST_COLUMNS


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg not installed")
def test_intake_end_to_end(tmp_path):
    ic = _load("intake_clips")
    src = tmp_path / "drive"
    src.mkdir()
    for name in ("V1-filling.mp4", "C1.mp4", "B1.mp4", "stray.mp4"):
        subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i",
                        "testsrc=size=720x1280:rate=10:duration=6", "-pix_fmt", "yuv420p",
                        str(src / name)], check=True)
    m = tmp_path / "clips.csv"
    _manifest(m, [["V1", "dev", "4", "fix", "filling_piled_center", "obvious"],
                  ["C1", "expert", "", "", "", "chef take"], ["B1", "other", "", "", "", ""],
                  ["V9", "heldout", "4", "pass", "", ""]])
    footage, eval_dir = tmp_path / "footage", tmp_path / "eval"
    args = ["--src", str(src), "--manifest", str(m), "--footage", str(footage),
            "--eval-dir", str(eval_dir), "--labeller", "AK", "--device", "test"]
    assert ic.main([*args, "--dry-run"]) == 1  # V9 is missing
    assert not footage.exists()
    assert ic.main(args) == 1
    assert (footage / "V1.mp4").is_file() and (footage / "C1.mp4").is_file()
    assert (footage / "other" / "B1.mp4").is_file()
    frames = sorted((eval_dir / "frames" / "dev").glob("V1-*.jpg"))
    assert len(frames) == 3
    with (eval_dir / "cases.csv").open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 3 and all(r["label"] == "" for r in rows)
    assert rows[0]["step_idx"] == "4" and "intent: fix filling_piled_center" in rows[0]["notes"]
    assert ic.main(args) == 1  # rerun adds no duplicate rows
    with (eval_dir / "cases.csv").open(newline="", encoding="utf-8") as f:
        assert len(list(csv.DictReader(f))) == 3
