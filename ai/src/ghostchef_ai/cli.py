"""Command line: python -m ghostchef_ai <models|check|watch|extract|live-config>."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import ghostchef_ai as gc
from ghostchef_ai import check, ingest, watch
from ghostchef_ai.config import fixture_dir, is_fake, load_env
from ghostchef_ai.schemas import RecipeDraft


def _recipe(path: str | None) -> RecipeDraft:
    p = Path(path) if path else fixture_dir() / "sushi_recipe.json"
    return RecipeDraft.model_validate(json.loads(p.read_text(encoding="utf-8")))


def _details(latency_ms: int, **extra) -> None:
    """--verbose: what the contract result leaves out, on stderr (stdout stays pure JSON)."""
    print(json.dumps({"latency_ms": latency_ms, **extra}, ensure_ascii=False), file=sys.stderr)


def _print(obj) -> None:
    data = obj.model_dump(mode="json") if hasattr(obj, "model_dump") else obj
    print(json.dumps(data, indent=2, ensure_ascii=False))


async def _run(args: argparse.Namespace) -> None:
    if args.cmd == "models":
        _print(gc.model_ids())
    elif args.cmd == "check":
        step = _recipe(args.recipe).step(args.step)
        ref = Path(args.ref) if args.ref else fixture_dir() / "images" / f"step-{args.step}.jpg"
        ref_bytes = None if args.no_ref or not ref.exists() else ref.read_bytes()
        frame = Path(args.frame).read_bytes()
        if args.verbose and not is_fake():
            out = await check.run_check(frame, step, ref_bytes)
            _details(out.latency_ms, attempts=out.attempts, evidence=out.raw.evidence,
                     raw_verdict=out.raw.verdict, ref="yes" if ref_bytes else "none")
            _print(out.result)
        else:
            _print(await gc.check_frame(frame, step, ref_bytes))
    elif args.cmd == "watch":
        step = _recipe(args.recipe).step(args.step)
        frame = Path(args.frame).read_bytes()
        if args.verbose and not is_fake():
            out = await watch.run_watch(frame, step)
            _details(out.latency_ms, raw=out.raw.model_dump() if out.raw else None)
            _print(out.result)
        else:
            _print(await gc.watch_frame(frame, step))
    elif args.cmd == "extract":
        if args.verbose and not is_fake():
            out = await ingest.run_extract(Path(args.video), title_hint=args.title,
                                           step_marks_s=args.marks or None)
            print(json.dumps({"model": out.model, "upload_s": round(out.upload_s, 1),
                              "generate_s": round(out.generate_s, 1),
                              "attempts": out.attempts, "steps": len(out.draft.steps)}),
                  file=sys.stderr)
            draft = out.draft
        else:
            draft = await gc.extract_recipe(
                Path(args.video), title_hint=args.title, step_marks_s=args.marks or None
            )
        text = json.dumps(draft.model_dump(mode="json"), indent=2, ensure_ascii=False)
        if args.output:
            Path(args.output).write_text(text + "\n", encoding="utf-8")
            print(f"wrote {args.output}", file=sys.stderr)
        else:
            print(text)
    elif args.cmd == "live-config":
        r = _recipe(args.recipe)
        _print(gc.build_live_config(r.title, args.chef, r.transcript, r.steps))


def main(argv: list[str] | None = None) -> int:
    load_env()  # ai/.env, for command-line use only
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(prog="python -m ghostchef_ai")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("models", help="print the model id used for each job")
    for name in ("check", "watch"):
        s = sub.add_parser(name, help=f"run {name}_frame on one JPEG")
        s.add_argument("--step", type=int, required=True)
        s.add_argument("--frame", required=True)
        s.add_argument("--recipe", help="RecipeDraft JSON (default: fixtures/sushi_recipe.json)")
        s.add_argument("-v", "--verbose", action="store_true",
                       help="real mode: also print latency and the raw model answer to stderr")
        if name == "check":
            s.add_argument("--ref", help="reference JPEG (default: fixtures/images/step-N.jpg)")
            s.add_argument("--no-ref", action="store_true",
                           help="send no reference image (criteria only)")
    e = sub.add_parser("extract", help="run extract_recipe on an MP4")
    e.add_argument("video")
    e.add_argument("-o", "--output")
    e.add_argument("--title")
    e.add_argument("--marks", type=float, nargs="*", help="step marks in seconds")
    e.add_argument("-v", "--verbose", action="store_true",
                   help="real mode: also print model, timings and attempts to stderr")
    lc = sub.add_parser("live-config", help="print the Gemini Live config for a recipe")
    lc.add_argument("--recipe")
    lc.add_argument("--chef")
    args = p.parse_args(argv)
    try:
        asyncio.run(_run(args))
    except gc.AIError as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    except (OSError, KeyError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0
