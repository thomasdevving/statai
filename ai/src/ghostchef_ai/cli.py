"""Command line: python -m ghostchef_ai <models|check|watch|extract|live-config>."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import ghostchef_ai as gc
from ghostchef_ai.config import fixture_dir
from ghostchef_ai.schemas import RecipeDraft


def _recipe(path: str | None) -> RecipeDraft:
    p = Path(path) if path else fixture_dir() / "sushi_recipe.json"
    return RecipeDraft.model_validate(json.loads(p.read_text(encoding="utf-8")))


def _print(obj) -> None:
    data = obj.model_dump(mode="json") if hasattr(obj, "model_dump") else obj
    print(json.dumps(data, indent=2, ensure_ascii=False))


async def _run(args: argparse.Namespace) -> None:
    if args.cmd == "models":
        _print(gc.model_ids())
    elif args.cmd == "check":
        step = _recipe(args.recipe).step(args.step)
        ref = Path(args.ref) if args.ref else fixture_dir() / "images" / f"step-{args.step}.jpg"
        ref_bytes = ref.read_bytes() if ref.exists() else None
        _print(await gc.check_frame(Path(args.frame).read_bytes(), step, ref_bytes))
    elif args.cmd == "watch":
        step = _recipe(args.recipe).step(args.step)
        _print(await gc.watch_frame(Path(args.frame).read_bytes(), step))
    elif args.cmd == "extract":
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
        if name == "check":
            s.add_argument("--ref", help="reference JPEG (default: fixtures/images/step-N.jpg)")
    e = sub.add_parser("extract", help="run extract_recipe on an MP4")
    e.add_argument("video")
    e.add_argument("-o", "--output")
    e.add_argument("--title")
    e.add_argument("--marks", type=float, nargs="*", help="step marks in seconds")
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
