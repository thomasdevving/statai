"""AI-02 smoke test: which models can our key call, and how fast. Costs real credits.

Usage (from ai/, with the key in ai/.env and GHOSTCHEF_AI_FAKE unset or 0):

    python scripts/smoke_models.py list                         # free: models visible to the key
    python scripts/smoke_models.py test --models MODEL [MODEL…] # paid: capability + latency

The provider comes from GHOSTCHEF_PROVIDER (gemini | openai). OpenAI is a TEMPORARY dev
stand-in while Gemini access is pending; its numbers are never Gemini results.

Cost control: a hard cap of GHOSTCHEF_MAX_CALLS paid calls (this script defaults it to 40),
low image detail, and outputs capped at a few dozen tokens. Per model: `--repeats` image
calls (default 5) + 2 two-image calls + 1 small-image call.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import os
import statistics
import sys
import time
from pathlib import Path

AI_DIR = Path(__file__).resolve().parents[1]
os.environ.setdefault("GHOSTCHEF_MAX_CALLS", "40")

from dotenv import load_dotenv  # noqa: E402

load_dotenv(AI_DIR / ".env", override=False)

from PIL import Image  # noqa: E402

from ghostchef_ai import client  # noqa: E402
from ghostchef_ai.config import is_fake, max_calls, provider  # noqa: E402
from ghostchef_ai.errors import AIError  # noqa: E402

IMAGES = AI_DIR / "fixtures" / "images"

TEXT_SCHEMA = {
    "type": "object",
    "properties": {"has_text": {"type": "boolean"}, "text": {"type": "string"}},
    "required": ["has_text", "text"],
    "additionalProperties": False,
}
SAME_SCHEMA = {
    "type": "object",
    "properties": {"same_image": {"type": "boolean"}},
    "required": ["same_image"],
    "additionalProperties": False,
}
SKIP_WORDS = ("embedding", "tts", "whisper", "dall-e", "moderation", "transcribe", "audio",
              "realtime", "image", "search", "babbage", "davinci", "codex", "computer-use",
              "sora", "embed", "aqa", "imagen", "veo", "lyria")


def _small(jpeg: bytes, long_edge: int) -> bytes:
    with Image.open(io.BytesIO(jpeg)) as im:
        im.thumbnail((long_edge, long_edge))
        buf = io.BytesIO()
        im.convert("RGB").save(buf, "JPEG", quality=60)
        return buf.getvalue()


async def list_models() -> None:
    names: list[str] = []
    try:
        if provider() == "openai":
            async for m in client.openai_client().models.list():
                names.append(m.id)
        else:
            for m in client.gemini_client().models.list():
                names.append(m.name.removeprefix("models/"))
    except AIError as exc:
        sys.exit(f"error: {exc}")
    except Exception as exc:  # noqa: BLE001
        sys.exit(f"error: {client.map_error(exc)}")
    chat = sorted(n for n in names if not any(w in n.lower() for w in SKIP_WORDS))
    print(f"provider={provider()}  models visible to this key: {len(names)}  "
          f"(showing {len(chat)} text/vision candidates; listing is free)")
    for n in chat:
        print("  ", n)


async def _timed(coro):
    t0 = time.perf_counter()
    try:
        res = await coro
        return res, (time.perf_counter() - t0) * 1000, None
    except AIError as exc:
        return None, (time.perf_counter() - t0) * 1000, exc


async def test_model(model: str, repeats: int) -> dict:
    step3 = (IMAGES / "step-3.jpg").read_bytes()
    step4 = (IMAGES / "step-4.jpg").read_bytes()
    out: dict = {"model": model, "image_ok": 0, "image_n": 0, "lat": [], "errors": []}

    # 1. image + structured output, repeated (latency sample). The placeholder says
    #    "3. Spread rice", so a correct answer reads the text.
    for _ in range(repeats):
        res, ms, err = await _timed(client.image_json(
            model=model, schema=TEXT_SCHEMA, schema_name="text_check", timeout_s=20,
            prompt="Does this image contain text? Return the main heading text exactly.",
            images=[("IMAGE:", step3)], max_output_tokens=60))
        out["image_n"] += 1
        if err:
            out["errors"].append(f"image: {err}")
            if "budget exhausted" in str(err) or "not set" in str(err):
                return out
            continue
        out["lat"].append(ms)
        if res.data.get("has_text") and "spread" in res.data.get("text", "").lower():
            out["image_ok"] += 1
        out["resolved_model"] = res.model

    # 2. two images in one request: identical pair, then different pair
    pairs = [("same", step3, step3, True), ("different", step3, step4, False)]
    out["two_image"] = []
    for label, a, b, want in pairs:
        res, ms, err = await _timed(client.image_json(
            model=model, schema=SAME_SCHEMA, schema_name="same_check", timeout_s=20,
            prompt="Are IMAGE A and IMAGE B exactly the same picture?",
            images=[("IMAGE A:", a), ("IMAGE B:", b)], max_output_tokens=60))
        if err:
            out["two_image"].append(f"{label}: ERROR {err}")
        else:
            ok = res.data.get("same_image") is want
            out["two_image"].append(f"{label}: {'PASS' if ok else 'WRONG'} ({ms:.0f} ms)")

    # 3. watcher-sized frame (512 px long edge)
    res, ms, err = await _timed(client.image_json(
        model=model, schema=TEXT_SCHEMA, schema_name="text_check", timeout_s=20,
        prompt="Does this image contain text? Return the main heading text exactly.",
        images=[("IMAGE:", _small(step3, 512))], max_output_tokens=60))
    out["small"] = f"ERROR {err}" if err else f"{ms:.0f} ms, read: {res.data.get('text')!r}"
    return out


def _fmt(r: dict) -> str:
    lat = r["lat"]
    p50 = f"{statistics.median(lat):.0f}" if lat else "—"
    mx = f"{max(lat):.0f}" if lat else "—"
    lines = [
        f"## {r['model']}  (resolved: {r.get('resolved_model', '—')})",
        f"image + structured output: {r['image_ok']}/{r['image_n']} correct, "
        f"latency p50 {p50} ms, max {mx} ms (n={len(lat)})",
    ]
    lines += [f"two images: {x}" for x in r.get("two_image", [])]
    if "small" in r:
        lines.append(f"512 px frame: {r['small']}")
    lines += [f"error: {e}" for e in r["errors"][:3]]
    return "\n".join(lines)


async def run_tests(models: list[str], repeats: int) -> None:
    per_model = repeats + 3
    print(f"provider={provider()}  models={models}  ~{per_model * len(models)} paid calls, "
          f"cap {max_calls() or 'none'}")
    for m in models:
        print()
        print(_fmt(await test_model(m, repeats)))
    print()
    print(f"TOTAL paid calls: {client.usage.calls}, input tokens: {client.usage.input_tokens}, "
          f"output tokens: {client.usage.output_tokens}")
    for m, (n, i, o) in client.usage.by_model.items():
        print(f"  {m}: {n} calls, {i} in, {o} out")
    if provider() == "gemini":
        print("\nGemini-only tests (video, Live, Live function call, ephemeral token): "
              "run scripts/gemini_smoke.py.")
    else:
        print("\nNot testable on the OpenAI stand-in: video with timestamps, Gemini Live, "
              "Live function calls, ephemeral tokens (Gemini-only).")


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if is_fake():
        sys.exit("GHOSTCHEF_AI_FAKE is on; set GHOSTCHEF_AI_FAKE=0 for a real smoke test")
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    t = sub.add_parser("test")
    t.add_argument("--models", nargs="+", required=True)
    t.add_argument("--repeats", type=int, default=5)
    args = p.parse_args()
    if args.cmd == "list":
        asyncio.run(list_models())
    else:
        asyncio.run(run_tests(args.models, args.repeats))


if __name__ == "__main__":
    main()
