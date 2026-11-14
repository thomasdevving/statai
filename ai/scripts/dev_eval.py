"""Dev-set runs for check_frame and watch_frame (AI-04.5; the beginnings of AI-07's eval.py).

Usage (from ai/, real mode, ai/.env with a key):

    # labelled dev rows of eval/cases.csv: label -> verdict counts and every disagreement
    python scripts/dev_eval.py cases
    # unlabelled frames (e.g. private dev material): what the model said, per frame size
    python scripts/dev_eval.py frames footage/mixkit/frames --rotate 180 --step 3 --no-ref

Both modes try two long-edge sizes for each call (check 1280 vs 768, watch 512 vs 384 by
default) and report median latency per size. `cases` mode reads ONLY `split == dev` rows and
refuses to touch held-out frames. Resized copies go to --work (default ai/footage/dev-variants,
gitignored). Calls run one at a time so latencies are not inflated by concurrency.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import io
import json
import os
import statistics
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

AI_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_DIR / "src"))

from ghostchef_ai import check, client, watch  # noqa: E402
from ghostchef_ai.config import fixture_dir, is_fake, load_env  # noqa: E402
from ghostchef_ai.errors import AIError  # noqa: E402
from ghostchef_ai.schemas import RecipeDraft  # noqa: E402

load_env()


@dataclass
class Case:
    name: str
    path: Path
    step_idx: int
    label: str = ""          # pass | fix | unsure, or "" when unlabelled
    mistake_id: str = ""


def resized_jpeg(src: Path, long_edge: int, rotate: int, work: Path) -> bytes:
    """Rotate, shrink so the long edge is at most long_edge, save a copy under work/, return it."""
    from PIL import Image

    out = work / f"{long_edge}-r{rotate}" / f"{src.stem}.jpg"
    if out.exists():
        return out.read_bytes()
    with Image.open(src) as im:
        im = im.convert("RGB")
        if rotate:
            im = im.rotate(rotate, expand=True)
        scale = long_edge / max(im.size)
        if scale < 1:
            im = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=85)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(buf.getvalue())
    return buf.getvalue()


def load_dev_cases(csv_path: Path) -> list[Case]:
    with csv_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    cases = []
    for r in rows:
        if r["split"] != "dev":
            continue  # never open held-out rows here (AI-04.5)
        cases.append(Case(r["case_id"], csv_path.parent / r["file"], int(r["step_idx"]),
                          r["label"], r["mistake_id"]))
    return cases


def frame_cases(folder: Path, step_idx: int) -> list[Case]:
    return [Case(p.stem, p, step_idx) for p in sorted(folder.glob("*.jpg"))]


async def run(cases: list[Case], recipe: RecipeDraft, args) -> dict:
    rows = []
    for size in args.check_sizes:
        for c in cases:
            step = recipe.step(c.step_idx)
            ref_path = fixture_dir() / "images" / f"step-{c.step_idx}.jpg"
            ref = None if args.no_ref else ref_path.read_bytes()
            frame = resized_jpeg(c.path, size, args.rotate, args.work)
            row = {"call": "check", "size": size, "case": c.name, "label": c.label,
                   "label_mistake": c.mistake_id, "bytes": len(frame)}
            try:
                out = await check.run_check(frame, step, ref, model=args.check_model,
                                             low_detail=args.check_low_detail)
                row |= {"verdict": out.result.verdict, "mistake_id": out.result.mistake_id,
                        "raw_verdict": out.raw.verdict, "confidence": out.result.confidence,
                        "headline": out.result.headline, "fix": out.result.fix,
                        "spoken": out.result.spoken, "evidence": out.raw.evidence,
                        "latency_ms": out.latency_ms, "attempts": out.attempts}
            except AIError as exc:
                row |= {"verdict": f"ERROR {type(exc).__name__}", "error": str(exc)[:200]}
            rows.append(row)
            _line(row)
    for size in args.watch_sizes:
        for c in cases:
            step = recipe.step(c.step_idx)
            frame = resized_jpeg(c.path, size, args.rotate, args.work)
            row = {"call": "watch", "size": size, "case": c.name, "label": c.label,
                   "label_mistake": c.mistake_id, "bytes": len(frame)}
            try:
                out = await watch.run_watch(frame, step)
                row |= {"verdict": out.result.status, "mistake_id": out.result.mistake_id,
                        "raw": out.raw.model_dump() if out.raw else None,
                        "confidence": out.result.confidence, "latency_ms": out.latency_ms}
            except AIError as exc:
                row |= {"verdict": f"ERROR {type(exc).__name__}", "error": str(exc)[:200]}
            rows.append(row)
            _line(row)
    return {"rows": rows, "usage": {"calls": client.usage.calls,
                                    "input_tokens": client.usage.input_tokens,
                                    "output_tokens": client.usage.output_tokens}}


def _line(row: dict) -> None:
    mid = row.get("mistake_id") or "-"
    extra = row.get("evidence") or row.get("raw") or row.get("error") or ""
    print(f"{row['call']:5} {row['size']:>4}px {row['case']:<22} {row['label'] or '?':6} -> "
          f"{row['verdict']:7} {mid:<22} conf {row.get('confidence', 0):.2f} "
          f"{row.get('latency_ms', 0):>5} ms  {extra}", flush=True)


def summarise(result: dict) -> None:
    rows = result["rows"]
    print("\n== median latency (ms) per call and size; errors excluded ==")
    for call in ("check", "watch"):
        for size in sorted({r["size"] for r in rows if r["call"] == call}, reverse=True):
            lat = [r["latency_ms"] for r in rows
                   if r["call"] == call and r["size"] == size and "latency_ms" in r]
            errs = sum(1 for r in rows if r["call"] == call and r["size"] == size
                       and r["verdict"].startswith("ERROR"))
            if lat:
                print(f"{call} {size}px: n={len(lat)} median {statistics.median(lat):.0f} "
                      f"max {max(lat)} errors {errs}")
            else:
                print(f"{call} {size}px: no successful calls, errors {errs}")
    print("\n== label -> answer counts (unlabelled rows show label '?') ==")
    for (call, size, label, verdict), n in sorted(Counter(
            (r["call"], r["size"], r["label"] or "?", r["verdict"]) for r in rows).items()):
        print(f"{call} {size}px  {label:6} -> {verdict:8} {n}")
    labelled = [r for r in rows if r["label"]]
    wrong = [r for r in labelled if not _agrees(r)]
    if labelled:
        print(f"\n== disagreements: {len(wrong)} of {len(labelled)} labelled answers ==")
        for r in wrong:
            print(f"{r['call']} {r['size']}px {r['case']}: label {r['label']} "
                  f"{r['label_mistake'] or ''} -> {r['verdict']} {r.get('mistake_id') or ''}  "
                  f"evidence: {r.get('evidence', '')}")
    u = result["usage"]
    print(f"\npaid calls {u['calls']}, input tokens {u['input_tokens']}, "
          f"output tokens {u['output_tokens']}")


def _agrees(r: dict) -> bool:
    if r["call"] == "check":
        return r["verdict"] == r["label"] and (
            r["label"] != "fix" or not r["label_mistake"] or r["mistake_id"] == r["label_mistake"])
    # watch: a labelled fix with a known mistake should warn with that id; everything else ok.
    if r["label"] == "fix" and r["label_mistake"]:
        return r["verdict"] == "warn" and r["mistake_id"] == r["label_mistake"]
    return r["verdict"] == "ok"


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("mode", choices=["cases", "frames"])
    p.add_argument("folder", nargs="?", help="frames mode: folder of JPEGs")
    p.add_argument("--cases-csv", type=Path, default=AI_DIR / "eval" / "cases.csv")
    p.add_argument("--step", type=int, default=4, help="frames mode: step index")
    p.add_argument("--rotate", type=int, default=0, help="degrees counter-clockwise, e.g. 180")
    p.add_argument("--no-ref", action="store_true", help="check without the reference image")
    p.add_argument("--check-sizes", type=int, nargs="*", default=[1280, 768])
    p.add_argument("--watch-sizes", type=int, nargs="*", default=[512, 384])
    p.add_argument("--check-model", help="override the check model for this run")
    p.add_argument("--check-low-detail", action="store_true", default=None,
                   help="check with LOW media resolution instead of the module default")
    p.add_argument("--work", type=Path, default=AI_DIR / "footage" / "dev-variants")
    p.add_argument("--save", type=Path, help="write all rows as JSON here (keep it out of git)")
    p.add_argument("--max-calls", type=int, default=80, help="cap on paid calls for this run")
    args = p.parse_args(argv)
    if is_fake():
        print("fake mode is on (GHOSTCHEF_AI_FAKE=1): this script needs real calls",
              file=sys.stderr)
        return 1
    os.environ["GHOSTCHEF_MAX_CALLS"] = str(args.max_calls)
    recipe = RecipeDraft.model_validate(
        json.loads((fixture_dir() / "sushi_recipe.json").read_text(encoding="utf-8")))
    if args.mode == "cases":
        cases = load_dev_cases(args.cases_csv)
        if not cases:
            print(f"no dev rows in {args.cases_csv}: nothing to evaluate (label frames first, "
                  "AI-03.4)")
            return 0
    else:
        if not args.folder:
            p.error("frames mode needs a folder")
        cases = frame_cases(Path(args.folder), args.step)
    result = asyncio.run(run(cases, recipe, args))
    summarise(result)
    if args.save:
        args.save.parent.mkdir(parents=True, exist_ok=True)
        args.save.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"rows saved to {args.save}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
