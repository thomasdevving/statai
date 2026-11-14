"""AI-03 helper scripts: extract_frames (pure parts + ffmpeg if installed), check_cases,
side_by_side."""

import csv
import importlib.util
import shutil
import subprocess
import sys

import pytest
from conftest import AI_DIR
from PIL import Image


def _load(name):
    spec = importlib.util.spec_from_file_location(name, AI_DIR / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ef = _load("extract_frames")
cc = _load("check_cases")
sbs = _load("side_by_side")
WATCH = cc.load_watch_fors(AI_DIR / "fixtures" / "sushi_recipe.json")
HAS_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


# ------------------------------------------------------------------ extract_frames

def test_timestamps():
    assert ef.timestamps(10.0, 2.5) == [0.0, 2.5, 5.0, 7.5]
    assert ef.timestamps(10.04, 2.5) == [0.0, 2.5, 5.0, 7.5]
    assert ef.timestamps(1.0, 2.5) == [0.0]
    with pytest.raises(ValueError):
        ef.timestamps(10, 0)


def test_frame_name_and_cmd(tmp_path):
    assert ef.frame_name("take1", 74.5) == "take1-0074.50.jpg"
    cmd = ef.ffmpeg_cmd("ffmpeg", tmp_path / "v.mp4", 74.5, tmp_path / "o.jpg", 1280, 3)
    assert cmd[cmd.index("-ss") + 1] == "74.500"
    assert cmd.index("-ss") < cmd.index("-i")  # fast seek
    assert cmd[cmd.index("-frames:v") + 1] == "1"
    assert "min(1280,iw)" in cmd[cmd.index("-vf") + 1]


def test_missing_ffmpeg_gives_install_hint(monkeypatch):
    monkeypatch.setattr(ef.shutil, "which", lambda _: None)
    with pytest.raises(SystemExit) as info:
        ef.find_tools()
    assert "winget install ffmpeg" in str(info.value)


@pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg not installed")
def test_extract_real_video(tmp_path):
    video = tmp_path / "clip.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i",
                    "testsrc=size=1080x1920:rate=10:duration=6", "-pix_fmt", "yuv420p",
                    str(video)], check=True)
    out = tmp_path / "frames"
    assert ef.main([str(video), str(out), "--every", "2.5", "--prefix", "t"]) == 0
    frames = sorted(out.glob("*.jpg"))
    assert [f.name for f in frames] == ["t-0000.00.jpg", "t-0002.50.jpg", "t-0005.00.jpg"]
    with Image.open(frames[0]) as im:
        assert im.size == (720, 1280)
    assert ef.main([str(video), str(out), "--at", "3.0", "--name", "step-3"]) == 0
    assert (out / "step-3.jpg").is_file()


# ------------------------------------------------------------------ check_cases

def _make_eval(tmp_path, rows, frames=()):
    for split, name in frames:
        d = tmp_path / "frames" / split
        d.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (8, 8)).save(d / name, "JPEG")
    path = tmp_path / "cases.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cc.COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cc.COLUMNS})
    return path


def _row(cid, split, name, label, mistake="", step="3"):
    return {"case_id": cid, "file": f"frames/{split}/{name}", "step_idx": step, "split": split,
            "label": label, "mistake_id": mistake, "labeller": "AK", "source_device": "phone"}


def test_valid_set_and_counts(tmp_path):
    frames = [("dev", f"{i}.jpg") for i in range(8)] + [("heldout", f"h{i}.jpg")
                                                         for i in range(8)]
    labels = ["pass"] * 3 + ["fix"] * 3 + ["unsure"] * 2
    rows = [_row(f"c{i}", "dev", f"{i}.jpg", lab, "rice_too_thick" if lab == "fix" else "")
            for i, lab in enumerate(labels)]
    rows += [_row(f"h{i}", "heldout", f"h{i}.jpg", lab,
                  "rice_covers_top_edge" if lab == "fix" else "")
             for i, lab in enumerate(labels)]
    path = _make_eval(tmp_path, rows, frames)
    errors, warnings, counts, unlabelled, _ = cc.validate(path, tmp_path, WATCH)
    assert errors == [] and unlabelled == 0
    assert counts[("dev", "pass")] == 3 and counts[("heldout", "unsure")] == 2
    assert cc.meets_minimum(counts) == {"dev": True, "heldout": True}
    assert "| dev | 3 | 3 | 2 | 8 |" in cc.format_counts(counts, 0.1)


@pytest.mark.parametrize("row,frames,needle", [
    (_row("c1", "dev", "x.jpg", "pass"), [], "file not found"),
    (_row("c1", "dev", "x.jpg", "maybe"), [("dev", "x.jpg")], "label must be"),
    (_row("c1", "dev", "x.jpg", "pass", "rice_too_thick"), [("dev", "x.jpg")],
     "only allowed when label is fix"),
    (_row("c1", "dev", "x.jpg", "fix", "burnt_rice"), [("dev", "x.jpg")], "not a watch_for"),
    (_row("c1", "dev", "x.jpg", "pass", step="9"), [("dev", "x.jpg")], "not in the fixture"),
    (_row("c1", "dev", "x.jpg", ""), [("dev", "x.jpg")], "no label"),
    ({**_row("c1", "dev", "x.jpg", "pass"), "split": "heldout"}, [("dev", "x.jpg")],
     "must live under frames/heldout/"),
])
def test_validation_errors(tmp_path, row, frames, needle):
    path = _make_eval(tmp_path, [row], frames)
    errors, *_ = cc.validate(path, tmp_path, WATCH)
    assert any(needle in e for e in errors), errors


def test_duplicate_ids_and_files(tmp_path):
    rows = [_row("c1", "dev", "x.jpg", "pass"), _row("c1", "dev", "x.jpg", "pass")]
    errors, *_ = cc.validate(_make_eval(tmp_path, rows, [("dev", "x.jpg")]), tmp_path, WATCH)
    assert any("duplicate case_id" in e for e in errors)
    assert any("listed twice" in e for e in errors)


def test_bad_header(tmp_path):
    path = tmp_path / "cases.csv"
    path.write_text("id,file\n", encoding="utf-8")
    errors, *_ = cc.validate(path, tmp_path, WATCH)
    assert "header must be exactly" in errors[0]


def test_scaffold_adds_only_new_frames(tmp_path):
    path = _make_eval(tmp_path, [_row("c0001", "dev", "a.jpg", "pass")],
                      [("dev", "a.jpg"), ("dev", "b.jpg"), ("heldout", "h.jpg")])
    assert cc.scaffold(path, tmp_path, 3, "AK", "phone") == 2
    _, rows = cc.read_rows(path)
    assert [r["case_id"] for r in rows] == ["c0001", "c0002", "c0003"]
    assert rows[2]["split"] == "heldout" and rows[2]["label"] == ""
    assert cc.scaffold(path, tmp_path, 3, "AK", "phone") == 0


def test_committed_cases_file_has_the_right_header():
    header, _ = cc.read_rows(AI_DIR / "eval" / "cases.csv")
    assert header == cc.COLUMNS


def test_check_cases_cli_runs():
    r = subprocess.run([sys.executable, str(AI_DIR / "scripts" / "check_cases.py")],
                       capture_output=True, text=True, encoding="utf-8")
    assert "| split | pass | fix | unsure | total |" in r.stdout


# ------------------------------------------------------------------ side_by_side

def test_side_by_side(tmp_path):
    imgs = [AI_DIR / "fixtures" / "images" / f"step-{i}.jpg" for i in (3, 4)]
    out = tmp_path / "s.jpg"
    assert sbs.main([*map(str, imgs), "--labels", "ref", "mine", "-o", str(out)]) == 0
    with Image.open(out) as im:
        assert im.height == sbs.HEIGHT + sbs.LABEL_H + 2 * sbs.GAP
