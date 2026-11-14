"""AI-05.3 end-to-end Live check, speaking the raw WebSocket protocol the iOS app will use.

    python scripts/live_smoke.py                       # 1 attempt + protocol extras
    python scripts/live_smoke.py --attempts 5          # ratios for the silence rules
    python scripts/live_smoke.py --question-wav footage/live-smoke/question-spread-edges-16k.wav

Each attempt: build the config from the fixture, mint a real token with
ghostchef_ai.mint_live_token (needs GEMINI_API_KEY, fake mode off), open the Live WebSocket with
ONLY the token (never the API key), send the AI-05.3 exchanges and print PASS / FAIL per row.
Attempt 1 also runs the protocol extras for ai/STATUS.md "Live facts for ios/": spoken audio
input, session resumption with the same token, reuse of a spent token, and the access_token
query parameter. Audio replies are saved as WAV under footage/live-smoke/<run>/ (gitignored);
one raw example of each server message kind goes to messages.jsonl (audio data shortened).
No secrets are printed: tokens are shown by prefix only.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import sys
import time
import wave
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

AI_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_DIR / "src"))

import ghostchef_ai as gc  # noqa: E402
from ghostchef_ai.config import load_env  # noqa: E402
from ghostchef_ai.live import LIVE_API_VERSION, SILENT_FUNCTIONS  # noqa: E402
from ghostchef_ai.schemas import RecipeDraft  # noqa: E402

load_env()

# Demo beat 6 and the words a grounded answer uses (the placeholder narration says the spread
# goes to the edges "so every bite has flavour and the filling has something to stick to").
DEMO_QUESTION = "Why spread it to the edges?"
GROUNDED_WORDS = ("flavour", "flavor", "bite", "stick")

HOST = "wss://generativelanguage.googleapis.com"
PATH = (f"/ws/google.ai.generativelanguage.{LIVE_API_VERSION}"
        ".GenerativeService.BidiGenerateContentConstrained")
OUT_RATE = 24000
SILENCE_WAIT_S = 8.0
ANSWER_WAIT_S = 25.0


# --------------------------------------------------------------------------- session


@dataclass
class Turn:
    audio: bytearray = field(default_factory=bytearray)
    mime: str | None = None
    transcript: str = ""
    input_transcript: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    end: str = "timeout"  # turn_complete | tool_call | timeout | closed
    first_audio_ms: float | None = None
    audio_before_call: int = 0


class Live:
    def __init__(self, ws, log_dir: Path):
        self.ws = ws
        self.q: asyncio.Queue = asyncio.Queue()
        self.handle: str | None = None
        self.resumable: bool | None = None
        self.go_away: dict | None = None
        self.kinds: Counter = Counter()
        self.frame_types: Counter = Counter()
        self.closed: tuple[int, str] | None = None
        self.log_dir = log_dir
        self._task = asyncio.create_task(self._reader())

    async def _reader(self):
        try:
            async for raw in self.ws:
                self.frame_types["binary" if isinstance(raw, bytes) else "text"] += 1
                msg = json.loads(raw)
                for k in msg:
                    kind = k
                    if k == "serverContent":
                        kind = "serverContent." + ",".join(sorted(msg[k]))
                    if self.kinds[kind] == 0:
                        _log_example(self.log_dir, kind, msg)
                    self.kinds[kind] += 1
                if "sessionResumptionUpdate" in msg:
                    u = msg["sessionResumptionUpdate"]
                    self.resumable = u.get("resumable")
                    if u.get("newHandle"):
                        self.handle = u["newHandle"]
                if "goAway" in msg:
                    self.go_away = msg["goAway"]
                await self.q.put(msg)
        except ConnectionClosed as exc:
            rcvd = exc.rcvd
            self.closed = (rcvd.code, rcvd.reason) if rcvd else (1006, "no close frame")
        await self.q.put(None)

    async def send(self, obj: dict):
        await self.ws.send(json.dumps(obj))

    async def text(self, text: str, turn_complete: bool = True):
        await self.send({"clientContent": {
            "turns": [{"role": "user", "parts": [{"text": text}]}],
            "turnComplete": turn_complete}})

    async def tool_response(self, call: dict, response: dict):
        fr = {"id": call["id"], "name": call["name"], "response": response}
        if call["name"] in SILENT_FUNCTIONS:
            fr["scheduling"] = "SILENT"  # add to context only; trigger no speech
        await self.send({"toolResponse": {"functionResponses": [fr]}})

    async def collect(self, wait_s: float) -> Turn:
        """Read until turnComplete / toolCall, or until wait_s pass with nothing new."""
        t = Turn()
        t0 = time.perf_counter()
        while True:
            try:
                msg = await asyncio.wait_for(self.q.get(), timeout=wait_s)
            except TimeoutError:
                return t
            if msg is None:
                t.end = "closed"
                return t
            if "toolCall" in msg:
                t.tool_calls += msg["toolCall"].get("functionCalls", [])
                t.audio_before_call = len(t.audio)
                t.end = "tool_call"
                return t
            sc = msg.get("serverContent")
            if not sc:
                continue
            for part in (sc.get("modelTurn") or {}).get("parts", []):
                inline = part.get("inlineData")
                if inline and inline.get("data"):
                    if t.first_audio_ms is None:
                        t.first_audio_ms = (time.perf_counter() - t0) * 1000
                    t.audio += base64.b64decode(inline["data"])
                    t.mime = inline.get("mimeType")
            if (sc.get("outputTranscription") or {}).get("text"):
                t.transcript += sc["outputTranscription"]["text"]
            if (sc.get("inputTranscription") or {}).get("text"):
                t.input_transcript += sc["inputTranscription"]["text"]
            if sc.get("turnComplete"):
                t.end = "turn_complete"
                return t

    async def answer_tool(self, call: dict, response: dict, wait_s: float) -> Turn:
        """Reply to a tool call and collect the model's reaction.

        The server closes the tool-call turn right after the toolCall (generationComplete,
        turnComplete, no audio). That close is drained first; otherwise it would be mistaken for
        the end of the reply. The reply to the tool response is a NEW turn.
        """
        stale = await self.collect(3.0)
        if stale.audio:
            print(f"  note: audio after the toolCall, before the tool response: {show(stale)}")
        await self.tool_response(call, response)
        return await self.collect(wait_s)

    async def close(self):
        await self.ws.close()
        self._task.cancel()


def _log_example(log_dir: Path, kind: str, msg: dict):
    def shorten(o):
        if isinstance(o, dict):
            return {k: (v[:24] + f"…({len(v)} chars)" if k == "data" and isinstance(v, str)
                        else ("<handle>" if k == "newHandle" and v else shorten(v)))
                    for k, v in o.items()}
        if isinstance(o, list):
            return [shorten(x) for x in o]
        return o
    with open(log_dir / "messages.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"kind": kind, "example": shorten(msg)}, ensure_ascii=False) + "\n")


async def open_session(token: str, model: str, log_dir: Path, *, query: bool = False,
                       handle: str | None = None) -> tuple[Live | None, str, float]:
    """Connect with the token only, send the minimal setup, wait for setupComplete."""
    t0 = time.perf_counter()
    if query:
        url, headers = f"{HOST}{PATH}?access_token={token}", {}
    else:
        url, headers = f"{HOST}{PATH}", {"Authorization": f"Token {token}"}
    # The token locks everything except session resumption, which the client sends itself.
    setup: dict = {"model": f"models/{model}",
                   "sessionResumption": {"handle": handle} if handle else {}}
    try:
        ws = await connect(url, additional_headers=headers, max_size=None)
    except Exception as exc:  # noqa: BLE001
        detail = str(exc).replace(token, "<token>")[:160]  # the URL may hold the token
        return None, f"connect failed: {type(exc).__name__}: {detail}", 0
    live = Live(ws, log_dir)
    await live.send({"setup": setup})
    try:
        msg = await asyncio.wait_for(live.q.get(), timeout=15)
    except TimeoutError:
        return None, "no setupComplete within 15 s", 0
    ms = (time.perf_counter() - t0) * 1000
    if msg is None:
        return None, f"closed before setupComplete: {live.closed}", ms
    if "setupComplete" not in msg:
        return None, f"first message was {list(msg)}", ms
    return live, "setupComplete", ms


# --------------------------------------------------------------------------- checks


def save_wav(path: Path, pcm: bytes):
    if not pcm:
        return
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(OUT_RATE)
        w.writeframes(pcm)


def silent(t: Turn) -> bool:
    """No audio bytes. A caption such as '<no speech detected>' with no audio still counts."""
    return not t.audio


def show(t: Turn) -> str:
    secs = len(t.audio) / (2 * OUT_RATE)
    first = f", first audio {t.first_audio_ms:.0f} ms" if t.first_audio_ms else ""
    return (f"end={t.end}, audio {secs:.1f} s{first}, mime {t.mime}, "
            f"calls {[c['name'] for c in t.tool_calls]}, said {t.transcript.strip()!r}")


class Report:
    def __init__(self):
        self.rows: list[tuple[int, str, bool, str]] = []

    def add(self, attempt: int, row: str, ok: bool, detail: str):
        self.rows.append((attempt, row, ok, detail))
        print(f"  [{'PASS' if ok else 'FAIL'}] {row}: {detail}")

    def ratio(self, row: str) -> str:
        hits = [ok for _, r, ok, _ in self.rows if r == row]
        return f"{sum(hits)}/{len(hits)}"


def context_line(idx: int, total: int, title: str) -> str:
    return (f'[CONTEXT] Cook is now on step {idx} of {total}: "{title}". '
            "Do not reply to this message.")


async def run_attempt(n: int, recipe: RecipeDraft, out: Path, rep: Report, wav: Path | None,
                      extras: bool) -> None:
    print(f"\n=== attempt {n} ===")
    cfg = gc.build_live_config(recipe.title, None, recipe.transcript, recipe.steps)
    t0 = time.perf_counter()
    tok = await gc.mint_live_token(cfg)
    print(f"  token minted in {(time.perf_counter() - t0) * 1000:.0f} ms: prefix "
          f"{tok.token.split('/')[0]!r}, locked={tok.locked}, expires {tok.expires_at:%H:%M:%S}, "
          f"new session by {tok.new_session_expires_at:%H:%M:%S} UTC")
    rep.add(n, "token minted, locked", tok.token.startswith("auth_tokens/") and tok.locked,
            f"locked={tok.locked}")
    d = out / f"attempt-{n}"
    d.mkdir(parents=True, exist_ok=True)
    live, why, ms = await open_session(tok.token, cfg.model, out)
    rep.add(n, "session opened with token only (Authorization header)", live is not None,
            f"{why} in {ms:.0f} ms")
    if live is None:
        return
    total = len(recipe.steps)
    s2, s3 = recipe.step(2), recipe.step(3)

    await live.text(context_line(2, total, s2.title), turn_complete=False)
    t = await live.collect(SILENCE_WAIT_S)
    save_wav(d / "1-context.wav", bytes(t.audio))
    rep.add(n, "[CONTEXT] turnComplete=false -> silence", silent(t) and not t.tool_calls,
            show(t))

    # The demo question (DEMO-AND-SUBMISSION §2 beat 6): answered from the chef's narration.
    await live.text(DEMO_QUESTION)
    t = await live.collect(ANSWER_WAIT_S)
    save_wav(d / "2-demo-question.wav", bytes(t.audio))
    grounded = any(w in t.transcript.lower() for w in GROUNDED_WORDS)
    rep.add(n, "demo question -> grounded answer", bool(t.audio) and grounded and not t.tool_calls,
            show(t))

    await live.text("Is this right?")
    t = await live.collect(ANSWER_WAIT_S)
    called = [c["name"] for c in t.tool_calls] == ["check_my_work"]
    rep.add(n, "is this right -> check_my_work", called and t.audio_before_call == 0, show(t))
    if t.tool_calls:
        after = await live.answer_tool(t.tool_calls[0], {
            "status": "done", "note": "The app has shown and spoken the result. Say nothing more."},
            SILENCE_WAIT_S)
        save_wav(d / "3-after-check.wav", bytes(after.audio))
        rep.add(n, "silent after check_my_work", silent(after), show(after))

    await live.text("What's next?")
    t = await live.collect(ANSWER_WAIT_S)
    called = [c["name"] for c in t.tool_calls] == ["next_step"]
    rep.add(n, "what's next -> next_step", called and t.audio_before_call == 0, show(t))
    if t.tool_calls:
        after = await live.answer_tool(t.tool_calls[0], {
            "status": "done", "now_on": f"3 of {total}: {s3.title}"}, SILENCE_WAIT_S)
        save_wav(d / "4-after-next.wav", bytes(after.audio))
        rep.add(n, "silent after next_step", silent(after), show(after))
        # The app sends a context line on every step change (API-CONTRACT §5.1). This one goes
        # with turnComplete=true, which asks the model for a turn it must leave silent.
        await live.text(context_line(3, total, s3.title))
        t = await live.collect(SILENCE_WAIT_S)
        save_wav(d / "4b-context-turn.wav", bytes(t.audio))
        rep.add(n, "[CONTEXT] turnComplete=true -> silence", silent(t) and not t.tool_calls,
                show(t))
        await live.text("Which step am I on? Just the number and name.")
        t = await live.collect(ANSWER_WAIT_S)
        said = t.transcript.lower()
        rep.add(n, "knows the step from [CONTEXT]", bool(t.audio) and not t.tool_calls and (
            "3" in said or "three" in said or "spread" in said), show(t))

    await live.text("Say that again")
    t = await live.collect(ANSWER_WAIT_S)
    called = [c["name"] for c in t.tool_calls] == ["repeat_instruction"]
    rep.add(n, "say that again -> repeat_instruction", called, show(t))
    if t.tool_calls:
        after = await live.answer_tool(t.tool_calls[0], {"instruction": s3.instruction},
                                       ANSWER_WAIT_S)
        save_wav(d / "5-repeat.wav", bytes(after.audio))
        said = after.transcript.lower()
        # Read aloud = most of the instruction's longer words are in the transcript (works for
        # any recipe; the old fixed keywords were sushi-specific).
        words = {w.strip(".,;:!?'\"").lower() for w in s3.instruction.split() if len(w) > 4}
        hits = sum(1 for w in words if w in said)
        read = bool(after.audio) and bool(words) and hits >= max(1, len(words) // 2)
        rep.add(n, "instruction read aloud", read, show(after))

    await live.text("How long do I boil an egg?")
    t = await live.collect(ANSWER_WAIT_S)
    save_wav(d / "6-boil-egg.wav", bytes(t.audio))
    said = t.transcript.lower().replace("’", "'")
    rep.add(n, "boil an egg -> not covered", bool(t.audio) and (
        "doesn't cover" in said or "does not cover" in said), show(t))

    if extras and wav:
        await spoken_question(n, live, wav, d, rep)

    handle = live.handle
    print(f"  server message kinds: {dict(live.kinds)}; frames {dict(live.frame_types)}; "
          f"resumable={live.resumable}, handle {'received' if handle else 'none'}, "
          f"goAway={live.go_away}")
    await live.close()

    if extras:
        await protocol_extras(n, tok.token, cfg.model, handle, recipe, out, rep)


async def spoken_question(n: int, live: Live, wav: Path, d: Path, rep: Report):
    """Send 16 kHz mono PCM as realtimeInput in 100 ms chunks at real-time pace."""
    with wave.open(str(wav)) as w:
        rate, ch, width = w.getframerate(), w.getnchannels(), w.getsampwidth()
        pcm = w.readframes(w.getnframes())
    if (rate, ch, width) != (16000, 1, 2):
        rep.add(n, "spoken question", False,
                f"WAV must be 16 kHz mono 16-bit, got {rate, ch, width}")
        return
    chunk = rate * 2 // 10  # 100 ms = 3200 bytes
    frames = [pcm[i:i + chunk] for i in range(0, len(pcm), chunk)] + [bytes(chunk)] * 15
    for f in frames:  # speech, then 1.5 s of silence as a live mic would send
        await live.send({"realtimeInput": {"audio": {
            "data": base64.b64encode(f).decode(), "mimeType": "audio/pcm;rate=16000"}}})
        await asyncio.sleep(0.1)
    t = await live.collect(ANSWER_WAIT_S)
    save_wav(d / "7-spoken-question.wav", bytes(t.audio))
    rep.add(n, "spoken question (16 kHz PCM) -> heard and answered",
            bool(t.audio) and bool(t.input_transcript.strip()),
            f"heard {t.input_transcript.strip()!r}; {show(t)}")


async def protocol_extras(n: int, token: str, model: str, handle: str | None, recipe: RecipeDraft,
                          out: Path, rep: Report):
    print("  --- protocol extras ---")
    cfg = gc.build_live_config(recipe.title, None, recipe.transcript, recipe.steps)
    if handle:
        live, why, ms = await open_session(token, model, out, handle=handle)
        rep.add(n, "resume with the SAME single-use token + handle", live is not None,
                f"{why} in {ms:.0f} ms")
        if live:
            await live.close()
        fresh = await gc.mint_live_token(cfg)
        live, why, ms = await open_session(fresh.token, model, out, handle=handle)
        ok = live is not None
        detail = f"{why} in {ms:.0f} ms"
        if live:
            await live.text("Which step am I on? Just the number and name.")
            t = await live.collect(ANSWER_WAIT_S)
            save_wav(out / f"attempt-{n}" / "8-resumed.wav", bytes(t.audio))
            detail += f"; {show(t)}"
            said = t.transcript.lower()
            ok = ok and bool(t.audio) and ("3" in said or "three" in said or "spread" in said)
            await live.close()
        rep.add(n, "resume with a NEW token + handle keeps the history", ok, detail)
    else:
        rep.add(n, "resume with a NEW token + handle keeps the history", False,
                "no handle received")

    live, why, _ = await open_session(token, model, out)
    rep.add(n, "spent token, fresh session (no handle) is refused", live is None, why)
    if live:
        await live.close()

    tok2 = await gc.mint_live_token(cfg)
    live, why, ms = await open_session(tok2.token, model, out, query=True)
    detail = f"{why} in {ms:.0f} ms"
    ok = live is not None
    if live:
        await live.text(DEMO_QUESTION)
        t = await live.collect(ANSWER_WAIT_S)
        detail += f"; {show(t)}"
        ok = ok and bool(t.audio)
        await live.close()
    rep.add(n, "token as ?access_token= query parameter", ok, detail)


async def main_async(args) -> int:
    if gc.model_ids()["live"] == "fake" or not os.environ.get("GEMINI_API_KEY"):
        print("needs GHOSTCHEF_AI_FAKE=0 and GEMINI_API_KEY (ai/.env)")
        return 2
    recipe = RecipeDraft.model_validate(json.loads(
        (AI_DIR / "fixtures" / "sushi_recipe.json").read_text(encoding="utf-8")))
    out = AI_DIR / "footage" / "live-smoke" / datetime.now().strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    print(f"model {gc.model_ids()['live']}, API {LIVE_API_VERSION}, output in {out}")
    rep = Report()
    wav = Path(args.question_wav) if args.question_wav else None
    for n in range(1, args.attempts + 1):
        try:
            await run_attempt(n, recipe, out, rep, wav, extras=(n == 1 and not args.no_extras))
        except gc.AIError as exc:
            rep.add(n, "attempt", False, f"{type(exc).__name__}: {exc}")
    print("\n=== summary (PASS count / attempts) ===")
    for row in dict.fromkeys(r for _, r, _, _ in rep.rows):
        print(f"  {rep.ratio(row):>5}  {row}")
    (out / "summary.json").write_text(json.dumps(
        [{"attempt": a, "row": r, "pass": ok, "detail": d} for a, r, ok, d in rep.rows],
        indent=1, ensure_ascii=False), encoding="utf-8")
    return 0


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--attempts", type=int, default=1)
    p.add_argument("--question-wav", help="16 kHz mono 16-bit WAV of a spoken question")
    p.add_argument("--no-extras", action="store_true", help="skip the protocol extras")
    return asyncio.run(main_async(p.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
