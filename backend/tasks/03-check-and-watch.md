# BE-03 — Check and watch, production-grade

| | |
|---|---|
| **Track** | `backend/` |
| **Gate** | G1 (first real verdict) and G2 (reliable loop) |
| **Depends on** | BE-01; AI-04 on `main` for the real-AI parts |
| **Unblocks** | IOS-03, IOS-04, WEB-01's real runs, the monitor's frame view |
| **Size** | Medium |
| **Model** | Opus 5.5 |
| **Needs a human for** | Nothing, apart from pointing a webcam at something |

## Goal

`/check` and `/watch` behave exactly as the contract says under real conditions: real Gemini, bad input, slow answers, overlapping calls, and a monitor that needs to see the latest frame.

**For gate G1 the minimum is task 1.** Do it the moment AI-04 lands, announce it, then continue.

## Read first

- [../../docs/API-CONTRACT.md §3](../../docs/API-CONTRACT.md#3-checking-and-watching) and §1.1 (errors)
- [../../docs/ARCHITECTURE.md §6](../../docs/ARCHITECTURE.md#6-failure-behaviour)
- `ai/STATUS.md` — chosen models, tuned frame sizes, latency baseline

## Tasks

### BE-03.1 Switch to real Gemini

**Do**
- `git pull`, `pip install -e ../ai` again (dependencies may have changed), set `GHOSTCHEF_AI_FAKE=0` and `GEMINI_API_KEY` in `.env`, restart.
- `GET /health` must report `ai_mode: gemini`.
- Run the smoke script with a **real photo** as `--frame` (ask the AI owner for one dev frame of a mistake and one of a correct result).

**Acceptance:** a real verdict comes back through `/check` for both frames; latencies recorded in `STATUS.md` → Last smoke run. Tell the team G1's backend part is met.

### BE-03.2 Input validation and normalisation

**Do** — `app/media/images.py`:
- `validate_jpeg(data, max_bytes)`: checks the size limit (`413 payload_too_large`) and that Pillow can open it as JPEG (`415 unsupported_media`).
- `downscale_jpeg(data, long_edge)`: if the image is larger than the endpoint's limit (1280 for check, 512 for watch) re-encode it at that long edge, quality 80; otherwise return the bytes untouched. Apply EXIF orientation before measuring. Run in a thread (`asyncio.to_thread`): Pillow is blocking.
- Limits: check 1.5 MB / 1280 px; watch 200 KB / 512 px. A watch frame over 200 KB but under 1.5 MB is **downscaled, not rejected** (be lenient with clients; log a warning).
- `step_id`, `request_id`, `session_id` must be valid UUIDs (`422`).

**Acceptance:** tests for oversized, non-JPEG, rotated-EXIF, and exactly-at-limit inputs.

### BE-03.3 Reference image cache

**Do**
- Loading the reference still from storage on every check costs a network round trip. Add an in-process LRU cache keyed by `(step_id, ref_image_path)` holding the bytes (max ~64 entries).
- Invalidate the entry when `PATCH /steps/{id}` changes the image (BE-06) and when a recipe is deleted or re-seeded.
- A step without a reference image still works: pass `None` to `check_frame`.

**Acceptance:** test that two checks on the same step read the blob once.

### BE-03.4 Budgets, errors, one-in-flight

**Do**
- Pass `timeout_s` from settings to the AI calls **and** wrap the whole handler's AI section in `asyncio.wait_for` with the same budget plus 0.5 s, so a hang inside the package still returns `504`.
- `/watch` in-flight guard: a per-`session_id` flag (a dict of sets or locks; no session id → no guard). If a watch call for the session is running, answer immediately with `429 quota_exhausted`, `retryable: true`, message `"watch already in flight"`. Always clear the flag in `finally`.
- Every error response carries the client's `request_id`.
- A cancelled request (client disconnected) must not record an event.

**Acceptance:** tests using a monkeypatched slow `watch_frame` prove the `504` and the in-flight `429`; a monkeypatched `AIQuotaError` gives `429`.

### BE-03.5 Frames, events, metrics

**Do**
- With `session_id`: always keep the **latest frame in memory** per session (bytes + timestamp + source) for the monitor, regardless of result.
- Persist to the `frames` bucket: every `/check` frame; `/watch` frames only when the result is `warn`. Persist **after** responding (background task) so storage latency never delays the wearer.
- Record events as the contract's table says; payload = the response body plus `frame_path` when a frame was stored.
- `app/metrics.py`: per-session ring buffers (last 500) of check and watch `latency_ms`; counts of errors by code. Expose through the monitor endpoint (BE-05 completes it).
- Serve the in-memory latest frame at `GET /sessions/{id}/latest-frame.jpg?t=<token>`, where the token is a random string generated per session and returned only inside the monitor response's `last_frame_url`. An `<img>` tag cannot send `X-Demo-Key`, so this route is authorised by the token. `Cache-Control: no-store`.

**Acceptance:** tests: latest frame is served and changes after a new call; a `warn` produces a stored frame and an event, an `ok` produces neither; a failed AI call produces no event.

### BE-03.6 Structured logging

**Do** — one log line per `/check` and `/watch` call: endpoint, session id, step idx, request id, verdict or status, mistake id, confidence, `latency_ms`, model, HTTP status. No frame bytes, no keys. Use the standard `logging` module with a JSON-ish formatter.

**Acceptance:** lines appear when the smoke script runs.

### BE-03.7 Real-condition run

**Do** — with real Gemini, run the web simulator (or the smoke script with `--watch-n 30`, real spacing) for two minutes against a real scene. Watch the logs.

**Acceptance:** `STATUS.md` records: number of calls, error counts by code, check and watch p50 / max. Anything surprising (timeouts, quota errors) is reported to the AI owner the same hour.

## Verification

```bash
cd backend
ruff check .
pytest -q
GHOSTCHEF_AI_FAKE=0 uvicorn app.main:app --host 0.0.0.0 --port 8000 &
python scripts/smoke.py --base http://localhost:8000 --key dev-key --frame /path/to/real-frame.jpg --watch-n 10
```

## Out of scope

Prompt quality (that is `ai/`). Client debounce (clients). Live token (BE-05).

## When done

Update `STATUS.md`, commit `[backend] BE-03 production check and watch`, push.
