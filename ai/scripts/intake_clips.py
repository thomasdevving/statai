"""Turn the filmed shot-list clips into footage files, frames and unlabelled label rows.

Usage (from ai/, ffmpeg on PATH), after downloading the shared drive folder:

    python scripts/intake_clips.py --src "C:/Users/me/Downloads/ghostchef-clips" \
        --labeller AK --device "Ray-Ban Meta Display (glasses)" --dry-run
    python scripts/intake_clips.py --src ... --labeller AK --device "..."

The Director keeps eval/clips.csv in sync with the shot list, one row per clip:

    clip_id,split,step_idx,intent,mistake_id,notes

- clip_id: the slate ID read out on camera, e.g. V14. The clip file's name must start with it
  (V14.mp4, V14-filling-piled.MOV, …); matching ignores case.
- split: expert (the chef take) | dev | heldout | other (demo, B-roll, anything not evaluated).
- step_idx, intent (pass/fix/unsure, what the clip is MEANT to show) and mistake_id: copied
  into the label rows as a hint only. Every frame is still labelled by a person, by eye,
  before any model sees it (AI-03.4); the label column stays empty.

What it does, per row:
- expert: copy to footage/<clip_id>.<ext> (gitignored). No frames: AI-03.5 picks the stills.
- dev / heldout: copy to footage/<clip_id>.<ext> or footage/heldout/<clip_id>.<ext>, extract a
  frame every --every s into eval/frames/<split>/<clip_id>-<s>.jpg, and append one unlabelled
  row per new frame to eval/cases.csv (existing rows are never touched).
- other: copy to footage/other/.
Raw clips never enter git (footage/ is gitignored); frames do, so keep them small.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

AI_DIR = Path(__file__).resolve().parents[1]
VIDEO_EXT = {".mp4", ".mov", ".m4v"}
SPLITS = ("expert", "dev", "heldout", "other")
MANIFEST_COLUMNS = ["clip_id", "split", "step_idx", "intent", "mistake_id", "notes"]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, AI_DIR / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@dataclass
class Clip:
    clip_id: str
    split: str
    step_idx: int | None
    intent: str
    mistake_id: str
    notes: str


def read_manifest(path: Path) -> tuple[list[Clip], list[str]]:
    clips, errors = [], []
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != MANIFEST_COLUMNS:
            return [], [f"header must be exactly: {','.join(MANIFEST_COLUMNS)}"]
        seen = set()
        for n, r in enumerate(reader, start=2):
            cid = (r["clip_id"] or "").strip()
            split = (r["split"] or "").strip()
            if not cid:
                errors.append(f"line {n}: empty clip_id")
                continue
            if cid.lower() in seen:
                errors.append(f"line {n}: duplicate clip_id {cid}")
            seen.add(cid.lower())
            if split not in SPLITS:
                errors.append(f"line {n} ({cid}): split must be one of {SPLITS}")
                continue
            step = (r["step_idx"] or "").strip()
            if split in ("dev", "heldout") and not step.isdigit():
                errors.append(f"line {n} ({cid}): dev/heldout clips need a step_idx")
                continue
            clips.append(Clip(cid, split, int(step) if step.isdigit() else None,
                              (r["intent"] or "").strip(), (r["mistake_id"] or "").strip(),
                              (r["notes"] or "").strip()))
    return clips, errors


def find_file(src: Path, clip_id: str) -> list[Path]:
    """Video files whose name starts with the clip ID, followed by a non-alphanumeric or end."""
    pat = re.compile(rf"^{re.escape(clip_id)}(?![A-Za-z0-9])", re.IGNORECASE)
    return sorted(p for p in src.rglob("*") if p.suffix.lower() in VIDEO_EXT
                  and pat.match(p.stem))


def destination(clip: Clip, src_file: Path, footage: Path) -> Path:
    folder = {"expert": footage, "dev": footage, "heldout": footage / "heldout",
              "other": footage / "other"}[clip.split]
    return folder / f"{clip.clip_id}{src_file.suffix.lower()}"


def append_rows(cases_csv: Path, eval_dir: Path, frames: list[Path], clip: Clip,
                labeller: str, device: str, columns: list[str]) -> int:
    rows = []
    existing: set[str] = set()
    next_id = 1
    if cases_csv.exists() and cases_csv.stat().st_size:
        with cases_csv.open(newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                existing.add(r["file"].replace("\\", "/"))
                if r["case_id"][:1] == "c" and r["case_id"][1:].isdigit():
                    next_id = max(next_id, int(r["case_id"][1:]) + 1)
    hint = f"intent: {clip.intent or '?'}{' ' + clip.mistake_id if clip.mistake_id else ''}"
    note = f"clip {clip.clip_id}; {hint}" + (f"; {clip.notes}" if clip.notes else "")
    for fr in frames:
        rel = fr.relative_to(eval_dir).as_posix()
        if rel in existing:
            continue
        rows.append({"case_id": f"c{next_id:04d}", "file": rel, "step_idx": str(clip.step_idx),
                     "split": clip.split, "label": "", "mistake_id": "", "labeller": labeller,
                     "source_device": device, "notes": note})
        next_id += 1
    new_file = not cases_csv.exists() or cases_csv.stat().st_size == 0
    with cases_csv.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columns)
        if new_file:
            w.writeheader()
        w.writerows(rows)
    return len(rows)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--src", type=Path, required=True, help="downloaded drive folder")
    p.add_argument("--manifest", type=Path, default=AI_DIR / "eval" / "clips.csv")
    p.add_argument("--footage", type=Path, default=AI_DIR / "footage")
    p.add_argument("--eval-dir", type=Path, default=AI_DIR / "eval")
    p.add_argument("--every", type=float, default=2.5)
    p.add_argument("--long-edge", type=int, default=1280)
    p.add_argument("--labeller", default="")
    p.add_argument("--device", default="")
    p.add_argument("--dry-run", action="store_true", help="report the plan, change nothing")
    args = p.parse_args(argv)

    if not args.src.is_dir():
        print(f"no such folder: {args.src}", file=sys.stderr)
        return 1
    clips, errors = read_manifest(args.manifest)
    for e in errors:
        print(f"manifest ERROR: {e}", file=sys.stderr)
    if errors:
        return 1
    ef = None if args.dry_run else _load("extract_frames")
    cc = _load("check_cases")
    matched: set[Path] = set()
    missing, ambiguous, total_rows = [], [], 0
    for clip in clips:
        files = find_file(args.src, clip.clip_id)
        if not files:
            missing.append(clip.clip_id)
            continue
        if len(files) > 1:
            ambiguous.append(f"{clip.clip_id}: {[f.name for f in files]}")
            continue
        src_file = files[0]
        matched.add(src_file)
        dest = destination(clip, src_file, args.footage)
        shown = dest.relative_to(AI_DIR) if dest.is_relative_to(AI_DIR) else dest
        plan = f"{clip.clip_id:>6} {clip.split:<8} {src_file.name} -> {shown}"
        if args.dry_run:
            print("would copy", plan)
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            shutil.copy2(src_file, dest)
        print("copied", plan)
        if clip.split in ("dev", "heldout"):
            out_dir = args.eval_dir / "frames" / clip.split
            ef.main([str(dest), str(out_dir), "--every", str(args.every),
                     "--long-edge", str(args.long_edge), "--prefix", clip.clip_id])
            frames = sorted(out_dir.glob(f"{clip.clip_id}-*.jpg"))
            n = append_rows(args.eval_dir / "cases.csv", args.eval_dir, frames, clip,
                            args.labeller, args.device, cc.COLUMNS)
            total_rows += n
            print(f"        {len(frames)} frames, {n} new unlabelled rows")
    unlisted = sorted(p.name for p in args.src.rglob("*")
                      if p.suffix.lower() in VIDEO_EXT and p not in matched)
    print()
    print(f"clips in manifest: {len(clips)}, matched: {len(matched)}, "
          f"new label rows: {total_rows}")
    for m in missing:
        print(f"MISSING file for {m}")
    for a in ambiguous:
        print(f"AMBIGUOUS {a} (rename so only one file starts with the ID)")
    for u in unlisted:
        print(f"not in manifest (ignored): {u}")
    if not args.dry_run and total_rows:
        print("\nnext: label the new rows in eval/cases.csv by eye, then "
              "`python scripts/check_cases.py --require-minimum`")
    return 1 if (missing or ambiguous) else 0


if __name__ == "__main__":
    sys.exit(main())
