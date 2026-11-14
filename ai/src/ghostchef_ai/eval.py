"""AI-07 evaluation runner: python -m ghostchef_ai.eval (ai/tasks/07, docs/EVALUATION.md §4).

Runs check_frame or watch_frame over the labelled rows of eval/cases.csv and writes one JSON
file (every case) and one Markdown summary (the EVALUATION.md metrics) per run to eval/results/.

    python -m ghostchef_ai.eval --split dev --config full                 # tuning
    python -m ghostchef_ai.eval --split dev --mode watch --threshold 0.7
    python -m ghostchef_ai.eval --split heldout --config full --confirm-heldout   # once, frozen

Configs (the ablation): full = reference photo + criteria + mistakes (what ships);
no-ref = criteria + mistakes, no reference photo; generic = a plain "is this step done
correctly?" prompt with no criteria and no reference. Watch mode always uses the shipped prompt.

Rules: tune on dev only; the held-out split needs --confirm-heldout and is run once, after the
prompts are frozen. Every result file records the date, model, prompt hashes, git commit and set
size. Works in fake mode (GHOSTCHEF_AI_FAKE=1), which is how the runner itself is tested; fake
results are labelled as such and are never evaluation results.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import statistics
import subprocess
import sys
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import ghostchef_ai as gc
from ghostchef_ai import check, client, prompts
from ghostchef_ai.config import AI_DIR, fixture_dir, is_fake, load_env, model_ids
from ghostchef_ai.errors import AIError, AIInvalidOutput
from ghostchef_ai.schemas import CheckResult, RecipeDraft, StepSpec

CONFIGS = ("full", "no-ref", "generic")
MODES = ("check", "watch")
DEFAULT_THRESHOLD = 0.7  # API-CONTRACT §3.3 default until AI-07.3 tunes it


@dataclass
class Case:
    case_id: str
    file: Path
    step_idx: int
    split: str
    label: str
    mistake_id: str = ""


@dataclass
class Row:
    case_id: str
    file: str
    step_idx: int
    label: str
    mistake_id: str
    prediction: str = ""          # check: pass/fix/unsure; watch: ok/warn
    predicted_mistake: str = ""
    confidence: float | None = None
    latency_ms: int | None = None
    model: str = ""
    error: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------- loading


def load_cases(csv_path: Path, split: str) -> list[Case]:
    """Labelled rows of one split. Unlabelled rows are skipped (check_cases.py validates)."""
    eval_dir = csv_path.parent
    out: list[Case] = []
    with csv_path.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if (r.get("split") or "").strip() != split or not (r.get("label") or "").strip():
                continue
            out.append(Case(case_id=r["case_id"].strip(),
                            file=eval_dir / r["file"].strip().replace("\\", "/"),
                            step_idx=int(r["step_idx"]), split=split,
                            label=r["label"].strip(),
                            mistake_id=(r.get("mistake_id") or "").strip()))
    return out


def load_recipe(path: Path | None = None) -> RecipeDraft:
    p = path or fixture_dir() / "sushi_recipe.json"
    return RecipeDraft.model_validate(json.loads(p.read_text(encoding="utf-8")))


def reference_image(step_idx: int, images_dir: Path | None = None) -> bytes | None:
    p = (images_dir or fixture_dir() / "images") / f"step-{step_idx}.jpg"
    return p.read_bytes() if p.is_file() else None


# --------------------------------------------------------------------------- one case


def generic_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "verdict": {"type": "string", "enum": ["pass", "fix", "unsure"]},
            "headline": {"type": "string"},
            "fix": {"type": "string"},
            "spoken": {"type": "string"},
            "confidence": {"type": "number"},
        },
        "required": ["verdict", "headline", "fix", "spoken", "confidence"],
        "additionalProperties": False,
    }


async def generic_check(frame: bytes, step: StepSpec, timeout_s: float) -> CheckResult:
    """The ablation's plain prompt: no criteria, no mistakes, no reference photo."""
    if is_fake():
        return await gc.check_frame(frame, step, None, timeout_s=timeout_s)
    model = model_ids()["check"]
    res = await client.image_json(
        model=model, prompt=prompts.render("generic_check", STEP_TITLE=step.title),
        images=[(check.LEARNER_LABEL, frame)], schema=generic_schema(),
        schema_name="generic_check", timeout_s=timeout_s,
        max_output_tokens=check.MAX_OUTPUT_TOKENS, low_detail=check.LOW_DETAIL)
    try:
        raw = check.RawCheck.model_validate({**res.data, "mistake_id": None})
    except Exception as exc:  # noqa: BLE001
        raise AIInvalidOutput(f"generic check output did not match: {exc}"[:300]) from exc
    return check.postprocess(raw, step, res.model, has_ref=False)


async def run_case(case: Case, recipe: RecipeDraft, mode: str, config: str,
                   timeout_s: float) -> Row:
    row = Row(case.case_id, case.file.as_posix(), case.step_idx, case.label, case.mistake_id)
    try:
        step = recipe.step(case.step_idx)
        frame = case.file.read_bytes()
    except (KeyError, OSError) as exc:
        row.error = f"setup: {exc}"
        return row
    t0 = time.perf_counter()
    try:
        if mode == "watch":
            w = await gc.watch_frame(frame, step, timeout_s=timeout_s)
            row.prediction, row.predicted_mistake = w.status, w.mistake_id or ""
            row.confidence, row.model = w.confidence, w.model
        else:
            if config == "generic":
                c = await generic_check(frame, step, timeout_s)
            else:
                ref = reference_image(step.idx) if config == "full" else None
                c = await gc.check_frame(frame, step, ref, timeout_s=timeout_s)
            row.prediction, row.predicted_mistake = c.verdict, c.mistake_id or ""
            row.confidence, row.model = c.confidence, c.model
    except AIError as exc:
        row.error = f"{type(exc).__name__}: {exc}"[:300]
    row.latency_ms = round((time.perf_counter() - t0) * 1000)
    return row


# --------------------------------------------------------------------------- metrics


def _p50_max(values: list[int]) -> tuple[int | None, int | None]:
    return (round(statistics.median(values)), max(values)) if values else (None, None)


def check_metrics(rows: list[Row]) -> dict[str, Any]:
    ok = [r for r in rows if not r.error]
    confusion = Counter((r.label, r.prediction) for r in ok)
    by_label = Counter(r.label for r in ok)
    p50, mx = _p50_max([r.latency_ms for r in ok if r.latency_ms is not None])
    return {
        "n": len(rows), "errors": len(rows) - len(ok),
        "confusion": {f"{lab}->{pred}": n for (lab, pred), n in sorted(confusion.items())},
        "false_approvals": confusion[("fix", "pass")], "n_fix": by_label["fix"],
        "false_rejections": confusion[("pass", "fix")], "n_pass": by_label["pass"],
        "appropriate_unsure": confusion[("unsure", "unsure")], "n_unsure": by_label["unsure"],
        "wrong_unsure": confusion[("pass", "unsure")] + confusion[("fix", "unsure")],
        "right_mistake_id": sum(1 for r in ok if r.label == "fix" and r.prediction == "fix"
                                and r.mistake_id and r.predicted_mistake == r.mistake_id),
        "latency_p50_ms": p50, "latency_max_ms": mx,
    }


def watch_metrics(rows: list[Row], threshold: float) -> dict[str, Any]:
    ok = [r for r in rows if not r.error]

    def warns(r: Row) -> bool:
        return r.prediction == "warn" and (r.confidence or 0) >= threshold

    fixes = [r for r in ok if r.label == "fix"]
    others = [r for r in ok if r.label in ("pass", "unsure")]
    p50, mx = _p50_max([r.latency_ms for r in ok if r.latency_ms is not None])
    return {
        "n": len(rows), "errors": len(rows) - len(ok), "threshold": threshold,
        "detected": sum(1 for r in fixes if warns(r)
                        and (not r.mistake_id or r.predicted_mistake == r.mistake_id)),
        "n_fix": len(fixes),
        "false_warnings": sum(1 for r in others if warns(r)), "n_not_fix": len(others),
        "single_frame_note": "per frame, before the client's 2-in-a-row debounce",
        "latency_p50_ms": p50, "latency_max_ms": mx,
    }


# --------------------------------------------------------------------------- watcher debounce


def debounce_alerts(results: list[tuple[float, str, str | None, float]], threshold: float, *,
                    required: int = 2, mute_s: float = 20.0) -> list[tuple[float, str]]:
    """Replay API-CONTRACT §3.3 on (time_s, status, mistake_id, confidence) watch results.

    An alert fires on the `required`-th consecutive warn with the same mistake id and
    confidence ≥ threshold. After an alert the streak resets and that id is muted for mute_s
    (as if the wearer dismissed it). Returns [(time_s, mistake_id)] of raised alerts.
    """
    alerts: list[tuple[float, str]] = []
    muted_until: dict[str, float] = {}
    streak_id, streak = None, 0
    for t, status, mid, conf in results:
        if status != "warn" or not mid or conf < threshold:
            streak_id, streak = None, 0
            continue
        streak = streak + 1 if mid == streak_id else 1
        streak_id = mid
        if streak >= required and t >= muted_until.get(mid, float("-inf")):
            alerts.append((t, mid))
            muted_until[mid] = t + mute_s
            streak_id, streak = None, 0
    return alerts


# --------------------------------------------------------------------------- run metadata


def _git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=AI_DIR,
                              capture_output=True, text=True, timeout=5).stdout.strip() or "?"
    except (OSError, subprocess.SubprocessError):
        return "?"


def prompt_hashes() -> dict[str, str]:
    names = ("check", "watch", "generic_check")
    return {n: hashlib.sha256(prompts.template(n).encode()).hexdigest()[:12] for n in names}


def summary_markdown(meta: dict, metrics: dict, rows: list[Row]) -> str:
    fake = " — **FAKE MODE, not an evaluation result**" if meta["fake"] else ""
    lines = [f"# Eval {meta['split']} / {meta['config']} / {meta['mode']}{fake}", "",
             f"- When (UTC): {meta['when']}  ·  commit `{meta['commit']}`",
             f"- Model: `{meta['model']}`  ·  prompt hashes: {meta['prompt_hashes']}",
             f"- Cases: {metrics['n']} ({meta['cases_file']}), errors: {metrics['errors']}", ""]
    if meta["mode"] == "check":
        lines += [
            "| Metric | Count |", "|---|---|",
            f"| False approvals (fix → pass) | {metrics['false_approvals']} of "
            f"{metrics['n_fix']} |",
            f"| False rejections (pass → fix) | {metrics['false_rejections']} of "
            f"{metrics['n_pass']} |",
            f"| Appropriate unsure | {metrics['appropriate_unsure']} of {metrics['n_unsure']} |",
            f"| Wrong unsure (pass/fix → unsure) | {metrics['wrong_unsure']} |",
            f"| Fix with the right mistake id | {metrics['right_mistake_id']} of "
            f"{metrics['n_fix']} |",
            f"| Latency p50 / max (ms) | {metrics['latency_p50_ms']} / "
            f"{metrics['latency_max_ms']} |", "",
            "Confusion (label→verdict): "
            + ", ".join(f"{k} {v}" for k, v in metrics["confusion"].items())]
    else:
        lines += [
            "| Metric | Count |", "|---|---|",
            f"| Mistakes detected (warn, right id, conf ≥ {metrics['threshold']}) | "
            f"{metrics['detected']} of {metrics['n_fix']} |",
            f"| False warnings on pass/unsure frames | {metrics['false_warnings']} of "
            f"{metrics['n_not_fix']} |",
            f"| Latency p50 / max (ms) | {metrics['latency_p50_ms']} / "
            f"{metrics['latency_max_ms']} |", "", f"_{metrics['single_frame_note']}_"]
    wrong = [r for r in rows if r.error or (meta["mode"] == "check" and r.label != r.prediction)]
    if wrong:
        lines += ["", "## Disagreements and errors", "",
                  "| case | label | got | conf | error |", "|---|---|---|---|---|"]
        lines += [f"| {r.case_id} | {r.label} {r.mistake_id} | {r.prediction} "
                  f"{r.predicted_mistake} | {r.confidence} | {r.error[:80]} |" for r in wrong]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- main


async def evaluate(cases: list[Case], recipe: RecipeDraft, mode: str, config: str,
                   concurrency: int, timeout_s: float) -> list[Row]:
    sem = asyncio.Semaphore(max(1, concurrency))

    async def one(c: Case) -> Row:
        async with sem:
            return await run_case(c, recipe, mode, config, timeout_s)
    return list(await asyncio.gather(*(one(c) for c in cases)))


def main(argv: list[str] | None = None) -> int:
    load_env()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(prog="python -m ghostchef_ai.eval",
                                description=__doc__.splitlines()[0])
    p.add_argument("--split", choices=("dev", "heldout"), required=True)
    p.add_argument("--config", choices=CONFIGS, default="full")
    p.add_argument("--mode", choices=MODES, default="check")
    p.add_argument("--cases", type=Path, default=AI_DIR / "eval" / "cases.csv")
    p.add_argument("--out", type=Path, default=AI_DIR / "eval" / "results")
    p.add_argument("--concurrency", type=int, default=2)
    p.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    p.add_argument("--timeout", type=float, default=None,
                   help="per-case model budget (default: check 8 s, watch 3.5 s)")
    p.add_argument("--confirm-heldout", action="store_true",
                   help="required for --split heldout: run it once, after freezing prompts")
    args = p.parse_args(argv)
    if args.split == "heldout" and not args.confirm_heldout:
        print("refusing to run the held-out split without --confirm-heldout "
              "(run it once, after the prompts and threshold are frozen)", file=sys.stderr)
        return 2
    if args.mode == "watch" and args.config != "full":
        print("watch mode has no ablation configs; use --config full", file=sys.stderr)
        return 2
    cases = load_cases(args.cases, args.split)
    if not cases:
        print(f"no labelled {args.split} rows in {args.cases}", file=sys.stderr)
        return 1
    timeout_s = args.timeout or (8.0 if args.mode == "check" else 3.5)
    rows = asyncio.run(evaluate(cases, load_recipe(), args.mode, args.config,
                                args.concurrency, timeout_s))
    metrics = (check_metrics(rows) if args.mode == "check"
               else watch_metrics(rows, args.threshold))
    when = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    meta = {"when": when, "split": args.split, "config": args.config, "mode": args.mode,
            "fake": is_fake(), "model": model_ids()["check" if args.mode == "check" else "watch"],
            "prompt_hashes": prompt_hashes(), "commit": _git_commit(),
            "cases_file": args.cases.as_posix(), "concurrency": args.concurrency,
            "timeout_s": timeout_s, "paid_calls": client.usage.calls}
    args.out.mkdir(parents=True, exist_ok=True)
    stem = f"{when}-{args.split}-{args.config}-{args.mode}" + ("-FAKE" if meta["fake"] else "")
    (args.out / f"{stem}.json").write_text(
        json.dumps({"meta": meta, "metrics": metrics, "rows": [asdict(r) for r in rows]},
                   indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md = summary_markdown(meta, metrics, rows)
    (args.out / f"{stem}.md").write_text(md, encoding="utf-8")
    print(md)
    print(f"wrote {args.out / stem}.json and .md", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
