"""AI-07.2: replay the proactive watcher on one clip, exactly as the phone would.

Usage (from ai/, real mode, ai/.env with a key; ffmpeg on PATH):

    # a mistake clip: the mistake becomes visible at 6 s and is fixed at 18 s
    python scripts/watch_clip.py footage/V14.mp4 --step 4 --expect filling_piled_center \
        --mistake-at 6 --fixed-at 18
    # a correct clip: any alert is a false alert
    python scripts/watch_clip.py footage/V03.mp4 --step 4 --expect none

One frame every --every seconds (2.5 = the watcher interval) goes through watch_frame once; the
client debounce (2 in a row, same id, confidence ≥ threshold, 20 s mute after an alert) is then
replayed for every --thresholds value, so a threshold sweep costs no extra model calls.
Writes <UTC>-clip-<name>.json and .md to eval/results/.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

AI_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_DIR / "src"))

import ghostchef_ai as gc  # noqa: E402
from ghostchef_ai.config import is_fake, load_env, model_ids  # noqa: E402
from ghostchef_ai.errors import AIError  # noqa: E402
from ghostchef_ai.eval import debounce_alerts, load_recipe  # noqa: E402

load_env()


def _extract_frames_module():
    spec = importlib.util.spec_from_file_location("extract_frames",
                                                  AI_DIR / "scripts" / "extract_frames.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def score(alerts: list[tuple[float, str]], expect: str, mistake_at: float | None,
          fixed_at: float | None, duration_s: float) -> dict:
    """Detection delay, false alerts, alerts after the fix, for one threshold."""
    minutes = max(duration_s, 1e-9) / 60
    if expect == "none":
        return {"alerts": len(alerts), "false_alerts": len(alerts),
                "false_alerts_per_min": round(len(alerts) / minutes, 2)}
    start = mistake_at or 0.0
    end = fixed_at if fixed_at is not None else float("inf")
    hits = [t for t, mid in alerts if mid == expect and start <= t <= end + 2.5]
    false = [t for t, mid in alerts if not (mid == expect and start <= t <= end + 2.5)]
    after_fix = [t for t, _ in alerts if fixed_at is not None and t > fixed_at + 2.5]
    return {"alerts": len(alerts), "detected": bool(hits),
            "detection_delay_s": round(hits[0] - start, 1) if hits else None,
            "false_alerts": len(false), "alerts_after_fix": len(after_fix)}


async def run(frames: list[tuple[float, Path]], step, timeout_s: float) -> list[dict]:
    out = []
    for t, path in frames:  # one at a time, like the phone (never two calls in flight)
        try:
            r = await gc.watch_frame(path.read_bytes(), step, timeout_s=timeout_s)
            out.append({"t": t, "status": r.status, "mistake_id": r.mistake_id,
                        "confidence": r.confidence, "model": r.model, "error": ""})
        except AIError as exc:
            out.append({"t": t, "status": "error", "mistake_id": None, "confidence": 0.0,
                        "model": "", "error": f"{type(exc).__name__}: {exc}"[:200]})
    return out


def markdown(meta: dict, results: list[dict], sweep: dict) -> str:
    fake = " — **FAKE MODE, not an evaluation result**" if meta["fake"] else ""
    first = next(iter(sweep.values()))
    lines = [f"# Watcher replay: {meta['clip']}{fake}", "",
             f"- Step {meta['step']}, expect `{meta['expect']}`, mistake at "
             f"{meta['mistake_at']} s, fixed at {meta['fixed_at']} s",
             f"- {len(results)} frames every {meta['every']} s over {meta['duration_s']:.1f} s; "
             f"model `{meta['model']}`; {meta['when']}", "",
             "| threshold | " + " | ".join(first.keys()) + " |",
             "|---|" + "---|" * len(first)]
    for th, s in sweep.items():
        lines.append(f"| {th} | " + " | ".join(str(v) for v in s.values()) + " |")
    lines += ["", "| t (s) | status | id | conf | error |", "|---|---|---|---|---|"]
    lines += [f"| {r['t']} | {r['status']} | {r['mistake_id'] or ''} | {r['confidence']} | "
              f"{r['error'][:60]} |" for r in results]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("clip", type=Path)
    p.add_argument("--step", type=int, default=4)
    p.add_argument("--expect", required=True, help="the clip's mistake_id, or 'none'")
    p.add_argument("--mistake-at", type=float, help="second the mistake becomes visible")
    p.add_argument("--fixed-at", type=float, help="second the mistake is fixed (fix clips)")
    p.add_argument("--every", type=float, default=2.5)
    p.add_argument("--long-edge", type=int, default=512)
    p.add_argument("--thresholds", type=float, nargs="+", default=[0.5, 0.6, 0.7, 0.8, 0.9])
    p.add_argument("--timeout", type=float, default=3.5)
    p.add_argument("--out", type=Path, default=AI_DIR / "eval" / "results")
    args = p.parse_args(argv)
    if not args.clip.is_file():
        print(f"no such clip: {args.clip}", file=sys.stderr)
        return 1
    ef = _extract_frames_module()
    ffmpeg, ffprobe = ef.find_tools()
    duration = ef.probe_duration(ffprobe, args.clip)
    step = load_recipe().step(args.step)
    with tempfile.TemporaryDirectory() as d:
        frames = []
        for t in ef.timestamps(duration, args.every):
            out = Path(d) / ef.frame_name("f", t)
            ef.subprocess.run(ef.ffmpeg_cmd(ffmpeg, args.clip, t, out, args.long_edge, 5),
                              capture_output=True, check=False)
            if out.exists():
                frames.append((t, out))
        results = asyncio.run(run(frames, step, args.timeout))
    triples = [(r["t"], r["status"], r["mistake_id"], r["confidence"]) for r in results]
    sweep = {th: score(debounce_alerts(triples, th), args.expect, args.mistake_at,
                       args.fixed_at, duration) for th in args.thresholds}
    when = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    meta = {"when": when, "clip": args.clip.name, "step": args.step, "expect": args.expect,
            "mistake_at": args.mistake_at, "fixed_at": args.fixed_at, "every": args.every,
            "duration_s": duration, "fake": is_fake(), "model": model_ids()["watch"]}
    args.out.mkdir(parents=True, exist_ok=True)
    stem = f"{when}-clip-{args.clip.stem}" + ("-FAKE" if meta["fake"] else "")
    (args.out / f"{stem}.json").write_text(json.dumps(
        {"meta": meta, "frames": results, "sweep": {str(k): v for k, v in sweep.items()}},
        indent=2) + "\n", encoding="utf-8")
    md = markdown(meta, results, sweep)
    (args.out / f"{stem}.md").write_text(md, encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
