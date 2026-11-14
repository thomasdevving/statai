"""AI-02.4 Gemini-only capability checks: video, Live audio, Live function call, ephemeral token.

Usage (from ai/, GEMINI_API_KEY in ai/.env):

    python scripts/gemini_smoke.py video --model gemini-3.8-flash      # needs ffmpeg
    python scripts/gemini_smoke.py live --models gemini-3.8-live other-live-model
    python scripts/gemini_smoke.py token --model gemini-3.8-live

Each test prints PASS or FAIL with the observed detail, for ai/STATUS.md. Live models are not
always returned by models.list, so `live` simply tries to connect to each name given.
These are small, single calls; they still use the account's quota.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

AI_DIR = Path(__file__).resolve().parents[1]

from dotenv import load_dotenv  # noqa: E402

load_dotenv(AI_DIR / ".env", override=False)

from google import genai  # noqa: E402
from google.genai import types  # noqa: E402

PING = types.FunctionDeclaration(name="ping", description="Call this when the user asks you "
                                 "to ping. It takes no arguments.")


def _client(api_key: str | None = None, api_version: str | None = None) -> genai.Client:
    key = api_key or os.environ.get("GEMINI_API_KEY")
    if not key:
        sys.exit("GEMINI_API_KEY is not set (ai/.env)")
    return genai.Client(api_key=key, http_options={"api_version": api_version}
                        if api_version else None)


def _short(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {str(exc).splitlines()[0][:220] if str(exc) else ''}"


# ------------------------------------------------------------------ video

def _make_clip(path: Path, seconds: int = 12) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        sys.exit("ffmpeg not on PATH (needed to generate the test clip); open a new terminal "
                 "after installing it")
    # ffmpeg's `testsrc` pattern shows a running counter: something time-dependent to describe.
    # (drawtext is avoided: without an explicit font file it crashes on Windows.)
    subprocess.run([ffmpeg, "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    f"testsrc=size=720x1280:rate=10:duration={seconds}",
                    "-pix_fmt", "yuv420p", str(path)], check=True)


async def test_video(model: str) -> None:
    seconds = 12
    with tempfile.TemporaryDirectory() as d:
        clip = Path(d) / "clip.mp4"
        _make_clip(clip, seconds)
        c = _client()
        t0 = time.perf_counter()
        f = c.files.upload(file=str(clip))
        try:
            while getattr(f.state, "name", str(f.state)) == "PROCESSING":
                await asyncio.sleep(1)
                f = c.files.get(name=f.name)
            ready = time.perf_counter()
            schema = {"type": "object", "properties": {"moments": {"type": "array", "items": {
                "type": "object", "properties": {"t_s": {"type": "number"},
                                                 "what": {"type": "string"}},
                "required": ["t_s", "what"]}}}, "required": ["moments"]}
            resp, level = None, None
            for level in ("MINIMAL", "LOW"):
                try:
                    resp = await c.aio.models.generate_content(
                        model=model,
                        contents=[f, "List exactly 2 moments in this video, with the time in "
                                     "seconds from the start and what is visible then."],
                        config=types.GenerateContentConfig(
                            temperature=0, max_output_tokens=2048,
                            response_mime_type="application/json",
                            response_json_schema=schema,
                            thinking_config=types.ThinkingConfig(
                                thinking_level=getattr(types.ThinkingLevel, level))))
                    break
                except Exception as exc:  # noqa: BLE001
                    if "thinking level" not in str(exc).lower() or level == "LOW":
                        raise
            done = time.perf_counter()
            moments = json.loads(resp.text)["moments"]
            inside = all(0 <= m["t_s"] <= seconds for m in moments)
            print(f"video [{model}]: {'PASS' if moments and inside else 'FAIL'} "
                  f"— {len(moments)} moments, timestamps {[m['t_s'] for m in moments]} "
                  f"(clip {seconds} s); upload+processing {ready - t0:.1f} s, "
                  f"generate {done - ready:.1f} s, thinking {level}")
            for m in moments:
                print(f"    {m['t_s']} s: {m['what'][:100]}")
        except Exception as exc:  # noqa: BLE001
            print(f"video [{model}]: FAIL — {_short(exc)}")
        finally:
            try:
                c.files.delete(name=f.name)
            except Exception:  # noqa: BLE001
                pass


# ------------------------------------------------------------------ Live

async def _one_turn(session, text: str, timeout_s: float = 30) -> dict:
    """Send a text turn; collect audio bytes, transcript, tool calls until turn_complete."""
    await session.send_client_content(
        turns=types.Content(role="user", parts=[types.Part(text=text)]), turn_complete=True)
    out = {"audio_bytes": 0, "mime": None, "transcript": "", "tool_calls": [], "first_ms": None}
    t0 = time.perf_counter()

    async def collect():
        async for msg in session.receive():
            if msg.tool_call:
                out["tool_calls"] += list(msg.tool_call.function_calls or [])
                return
            sc = msg.server_content
            if not sc:
                continue
            for part in (sc.model_turn.parts if sc.model_turn else []) or []:
                if part.inline_data and part.inline_data.data:
                    if out["first_ms"] is None:
                        out["first_ms"] = (time.perf_counter() - t0) * 1000
                    out["audio_bytes"] += len(part.inline_data.data)
                    out["mime"] = part.inline_data.mime_type
            if sc.output_transcription and sc.output_transcription.text:
                out["transcript"] += sc.output_transcription.text
            if sc.turn_complete:
                return

    await asyncio.wait_for(collect(), timeout=timeout_s)
    return out


def _live_config() -> types.LiveConnectConfig:
    return types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        tools=[types.Tool(function_declarations=[PING])],
        output_audio_transcription=types.AudioTranscriptionConfig(),
        system_instruction="Answer in one short sentence.",
    )


async def test_live(model: str, client: genai.Client | None = None, label: str = "live",
                    config: types.LiveConnectConfig | None = None) -> bool:
    # Live needs an explicit API version: the SDK default answered HTTP 404 on 2026-11-14.
    c = client or _client(api_version="v1beta")
    try:
        async with c.aio.live.connect(model=model, config=config or _live_config()) as s:
            hello = await _one_turn(s, "Say hello.")
            ok_audio = hello["audio_bytes"] > 0
            first = round(hello["first_ms"]) if hello["first_ms"] else None
            print(f"{label} [{model}] text→audio: {'PASS' if ok_audio else 'FAIL'} — "
                  f"{hello['audio_bytes']} bytes, mime {hello['mime']}, first audio "
                  f"{first} ms, transcript {hello['transcript'][:80]!r}")
            if label != "live":
                return ok_audio
            ping = await _one_turn(s, "Please ping.")
            calls = ping["tool_calls"]
            print(f"live [{model}] function call: {'PASS' if calls else 'FAIL'} — "
                  f"{[fc.name for fc in calls]}")
            if calls:
                await s.send_tool_response(function_responses=[types.FunctionResponse(
                    id=calls[0].id, name=calls[0].name, response={"status": "done"})])
            return ok_audio and bool(calls)
    except Exception as exc:  # noqa: BLE001
        print(f"{label} [{model}]: FAIL — {_short(exc)}")
        return False


# ------------------------------------------------------------------ ephemeral token

async def test_token(model: str) -> None:
    now = dt.datetime.now(tz=dt.UTC)
    c = _client(api_version="v1beta")
    attempts = [
        ("model + modalities + instruction + tools locked", {
            "model": model,
            "config": {"response_modalities": ["AUDIO"],
                       "system_instruction": "Answer in one short sentence.",
                       "tools": [{"function_declarations": [{"name": "ping",
                                                             "description": "ping"}]}],
                       "session_resumption": {}}}),
        ("model + modalities locked", {
            "model": model, "config": {"response_modalities": ["AUDIO"]}}),
    ]
    for desc, constraints in attempts:
        try:
            tok = c.auth_tokens.create(config={
                "uses": 1,
                "expire_time": now + dt.timedelta(minutes=30),
                "new_session_expire_time": now + dt.timedelta(minutes=2),
                "live_connect_constraints": constraints,
            })
        except Exception as exc:  # noqa: BLE001
            print(f"token [{desc}]: mint FAIL — {_short(exc)}")
            continue
        prefix = tok.name.split("/")[0] if tok.name else "?"
        print(f"token [{desc}]: minted (name prefix {prefix!r})")
        tc = _client(api_key=tok.name, api_version="v1beta")
        ok = await test_live(model, client=tc, label=f"token session [{desc}]",
                             config=types.LiveConnectConfig(response_modalities=["AUDIO"]))
        if ok:
            return


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("video")
    v.add_argument("--model", required=True)
    lv = sub.add_parser("live")
    lv.add_argument("--models", nargs="+", required=True)
    tk = sub.add_parser("token")
    tk.add_argument("--model", required=True)
    args = p.parse_args()
    if args.cmd == "video":
        asyncio.run(test_video(args.model))
    elif args.cmd == "live":
        async def run():
            for m in args.models:
                await test_live(m)
        asyncio.run(run())
    else:
        asyncio.run(test_token(args.model))


if __name__ == "__main__":
    main()
