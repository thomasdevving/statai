"""Validate the labelled evaluation set and print its counts (AI-03.4).

Usage (from ai/):

    python scripts/check_cases.py                       # validate eval/cases.csv, print counts
    python scripts/check_cases.py --require-minimum     # also fail if below the AI-03.4 minimum
    python scripts/check_cases.py --scaffold --step 3 --labeller AK --device "iPhone 15 (stand-in)"
        # append one unlabelled row per frame in eval/frames/{dev,heldout}/ not yet listed

Columns: case_id,file,step_idx,split,label,mistake_id,labeller,source_device,notes
- file is relative to ai/eval/, e.g. frames/dev/take1-0012.50.jpg, and must sit under
  frames/<split>/ so a frame can never be in both splits.
- label is pass | fix | unsure. mistake_id is set only for fix, and must be one of that
  step's watch_fors ids in fixtures/sushi_recipe.json (it may stay empty for a fix the
  recipe does not list).
Label by looking at the frame and the chef's criteria BEFORE running any model on it.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

AI_DIR = Path(__file__).resolve().parents[1]
EVAL_DIR = AI_DIR / "eval"
COLUMNS = ["case_id", "file", "step_idx", "split", "label", "mistake_id", "labeller",
           "source_device", "notes"]
SPLITS = ("dev", "heldout")
LABELS = ("pass", "fix", "unsure")
MINIMUM = {"pass": 3, "fix": 3, "unsure": 2}  # per split, AI-03.4
MAX_MB = 30


def load_watch_fors(recipe_path: Path) -> dict[int, set[str]]:
    recipe = json.loads(recipe_path.read_text(encoding="utf-8"))
    return {s["idx"]: {w["id"] for w in s["watch_fors"]} for s in recipe["steps"]}


def read_rows(csv_path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader.fieldnames or []), list(reader)


def validate(csv_path: Path, eval_dir: Path, watch_fors: dict[int, set[str]]):
    """Return (errors, warnings, counts Counter[(split, label)], unlabelled count, MB)."""
    errors: list[str] = []
    warnings: list[str] = []
    header, rows = read_rows(csv_path)
    if header != COLUMNS:
        errors.append(f"header must be exactly: {','.join(COLUMNS)} (got {','.join(header)})")
        return errors, warnings, Counter(), 0, 0.0
    counts: Counter[tuple[str, str]] = Counter()
    seen_ids: set[str] = set()
    seen_files: set[str] = set()
    unlabelled = 0
    total_bytes = 0
    for n, r in enumerate(rows, start=2):  # line 1 is the header
        where = f"line {n} ({r.get('case_id') or 'no case_id'})"
        cid = (r["case_id"] or "").strip()
        if not cid:
            errors.append(f"{where}: empty case_id")
        elif cid in seen_ids:
            errors.append(f"{where}: duplicate case_id")
        seen_ids.add(cid)

        file = (r["file"] or "").strip().replace("\\", "/")
        path = eval_dir / file
        if not file or not path.is_file():
            errors.append(f"{where}: file not found: {file!r}")
        else:
            total_bytes += path.stat().st_size
        if file in seen_files:
            errors.append(f"{where}: the same file is listed twice")
        seen_files.add(file)

        split = (r["split"] or "").strip()
        if split not in SPLITS:
            errors.append(f"{where}: split must be dev or heldout, got {split!r}")
        elif not file.startswith(f"frames/{split}/"):
            errors.append(f"{where}: a {split} case must live under frames/{split}/")

        try:
            step = int(r["step_idx"])
            if step not in watch_fors:
                errors.append(f"{where}: step_idx {step} is not in the fixture recipe")
        except (TypeError, ValueError):
            step = None
            errors.append(f"{where}: step_idx must be an integer, got {r['step_idx']!r}")

        label = (r["label"] or "").strip()
        mistake = (r["mistake_id"] or "").strip()
        if not label:
            unlabelled += 1
        elif label not in LABELS:
            errors.append(f"{where}: label must be pass, fix or unsure, got {label!r}")
        else:
            counts[(split, label)] += 1
            if not (r["labeller"] or "").strip():
                errors.append(f"{where}: labelled but no labeller initials")
        if mistake and label != "fix":
            errors.append(f"{where}: mistake_id is only allowed when label is fix")
        if label == "fix" and step in watch_fors:
            if not mistake:
                warnings.append(f"{where}: fix without mistake_id (a mistake the recipe "
                                "does not list)")
            elif mistake not in watch_fors[step]:
                errors.append(f"{where}: mistake_id {mistake!r} is not a watch_for of step "
                              f"{step} (known: {sorted(watch_fors[step]) or 'none'})")
        if not (r["source_device"] or "").strip():
            warnings.append(f"{where}: source_device is empty")
    if unlabelled:
        errors.append(f"{unlabelled} row(s) still have no label")
    mb = total_bytes / 1_000_000
    if mb > MAX_MB:
        warnings.append(f"listed frames total {mb:.1f} MB (> {MAX_MB} MB); downscale or prune")
    return errors, warnings, counts, unlabelled, mb


def meets_minimum(counts: Counter) -> dict[str, bool]:
    return {s: all(counts[(s, lab)] >= n for lab, n in MINIMUM.items()) for s in SPLITS}


def format_counts(counts: Counter, mb: float) -> str:
    lines = ["| split | pass | fix | unsure | total |", "|---|---|---|---|---|"]
    for s in SPLITS:
        row = [counts[(s, lab)] for lab in LABELS]
        lines.append(f"| {s} | {row[0]} | {row[1]} | {row[2]} | {sum(row)} |")
    ok = meets_minimum(counts)
    lines.append("")
    lines.append("minimum per split (pass ≥3, fix ≥3, unsure ≥2): "
                 + ", ".join(f"{s} {'met' if ok[s] else 'NOT met'}" for s in SPLITS))
    lines.append(f"frames listed: {mb:.1f} MB")
    return "\n".join(lines)


def scaffold(csv_path: Path, eval_dir: Path, step: int, labeller: str, device: str) -> int:
    if csv_path.exists():
        _, rows = read_rows(csv_path)
    else:
        rows = []
    listed = {r["file"].replace("\\", "/") for r in rows}
    next_id = 1 + max((int(r["case_id"][1:]) for r in rows
                       if r["case_id"][:1] == "c" and r["case_id"][1:].isdigit()), default=0)
    new = []
    for split in SPLITS:
        for img in sorted((eval_dir / "frames" / split).glob("*.jpg")):
            rel = img.relative_to(eval_dir).as_posix()
            if rel in listed:
                continue
            new.append({"case_id": f"c{next_id:04d}", "file": rel, "step_idx": str(step),
                        "split": split, "label": "", "mistake_id": "", "labeller": labeller,
                        "source_device": device, "notes": ""})
            next_id += 1
    write_header = not csv_path.exists() or csv_path.stat().st_size == 0
    with csv_path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        if write_header:
            w.writeheader()
        w.writerows(new)
    return len(new)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--cases", type=Path, default=EVAL_DIR / "cases.csv")
    p.add_argument("--eval-dir", type=Path, default=EVAL_DIR)
    p.add_argument("--recipe", type=Path, default=AI_DIR / "fixtures" / "sushi_recipe.json")
    p.add_argument("--require-minimum", action="store_true")
    p.add_argument("--scaffold", action="store_true")
    p.add_argument("--step", type=int, default=3)
    p.add_argument("--labeller", default="")
    p.add_argument("--device", default="")
    args = p.parse_args(argv)

    if args.scaffold:
        n = scaffold(args.cases, args.eval_dir, args.step, args.labeller, args.device)
        print(f"added {n} unlabelled row(s) to {args.cases}; fill in label (and mistake_id "
              "for fix), then run this script again without --scaffold")
        return 0
    if not args.cases.is_file():
        print(f"no cases file at {args.cases}", file=sys.stderr)
        return 1
    errors, warnings, counts, _, mb = validate(args.cases, args.eval_dir,
                                               load_watch_fors(args.recipe))
    print(format_counts(counts, mb))
    for w in warnings:
        print(f"warning: {w}")
    for e in errors:
        print(f"ERROR: {e}")
    if errors:
        return 1
    if args.require_minimum and not all(meets_minimum(counts).values()):
        print("ERROR: below the AI-03.4 minimum")
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
