# BE-05 — Live token for real, the monitor feed, session summary

| | |
|---|---|
| **Track** | `backend/` |
| **Gate** | G2 (monitor) → G3 (voice) |
| **Depends on** | BE-01, BE-03.5 (latest frame, metrics); AI-05 on `main` for the real token |
| **Unblocks** | IOS-05 (voice), WEB-03 (monitor) |
| **Size** | Small–medium |
| **Model** | Opus 5.5 |
| **Needs a human for** | Nothing |

## Goal

`/live-token` hands the phone a real, locked, short-lived credential and the exact configuration; the monitor endpoint gives the audience screen everything in one cheap call; the session summary is correct enough to show on the Done screen.

Tasks 2 and 3 do not depend on the AI track: do them first if AI-05 is not ready.

## Read first

- [../../docs/API-CONTRACT.md §4](../../docs/API-CONTRACT.md#4-sessions-and-events) and [§5](../../docs/API-CONTRACT.md#5-gemini-live-voice)
- `ai/STATUS.md` → "Live facts for `ios/`" (whether tokens are fully locked)

## Tasks

### BE-05.1 Real `/live-token`

**Do**
- Handler: validate `recipe_id` (must be `published`, else `409 recipe_not_ready`) and optional `session_id`; load steps and transcript; `build_live_config(...)`; `mint_live_token(config)`; return the §5 body with `api_version: "v1beta"`, `locked` from the token, and `config` always included.
- Cache the **config** per recipe (keyed by recipe id + a hash of its steps and transcript) so repeated calls do not rebuild it; never cache the **token** (single use).
- Never log the token. Log only: recipe id, model, locked, expiry.
- Error mapping as for other AI calls. In fake mode the endpoint returns the fake token so clients can develop their flow.
- Simple abuse guard: at most one token per `session_id` every 3 seconds (`429`), so a reconnect loop in a client cannot burn quota.

**Acceptance**
- Tests in fake mode: shape, `409` for an unpublished recipe, the 3-second guard.
- With real AI: the smoke script reports `model` and `locked`. Record both in `STATUS.md`.

### BE-05.2 Monitor endpoint, complete

**Do** — `GET /sessions/{id}/monitor` exactly as in §4:
- `current_step`: full `Step` object (with signed URLs) for the latest `step_change.to_idx`, else step 1.
- `last_frame_url` (the tokenised latest-frame route from BE-03.5) and `last_frame_at`; both `null` before any frame.
- `last_result`: `{source, at, body}` of the most recent check or watch response **including `ok` watch results** (kept in memory per session; `ok` results are not events).
- `events`: the latest 30, newest first.
- `latency`: p50, max, and n for check and watch from `metrics.py`.
- Must be cheap: no storage round trips per call beyond one events query. Cache the session and recipe for a few seconds. The monitor polls once a second.
- In-memory state is lost on restart; after a restart the endpoint still works and simply shows no latest frame until the next call.

**Acceptance:** tests for the empty session, after a step change, after an `ok` watch (appears in `last_result`, not in `events`), after a `warn`, and after a check. A 60-call loop against the local server stays under ~50 ms per call on the memory store.

### BE-05.3 Sessions list and summary, verified

**Do**
- `GET /sessions?active=true&limit=N`: `active=true` means `finished_at is null` and started within the last 3 hours; newest first; include `recipe_title`.
- Summary rules (finalise and test): `steps_total`; `steps_passed_first_try` = steps whose **first** check event is `check_pass` (a step with no check does not count); `fixes_caught` = number of `check_fix` events; `warnings` = number of `watch_warn` events; `questions` = number of `question` events. `check_unsure` affects none of them.
- `session_end` is idempotent.

**Acceptance:** a table-driven test with five event sequences and expected summaries.

### BE-05.4 Extend the smoke script

**Do** — `scripts/smoke.py` additionally: posts a `question` event; checks that the monitor's `current_step` follows a `step_change`; fetches `last_frame_url` and expects `image/jpeg`; prints the summary.

**Acceptance:** exits 0 locally and against production.

### BE-05.5 Deploy and tell the clients

Deploy (or let auto-deploy run), run the smoke script against production, and tell the iOS owner (`/live-token` is real) and the web owner (monitor feed is complete).

## Verification

```bash
cd backend
ruff check .
pytest -q
python scripts/smoke.py --base http://localhost:8000 --key dev-key --fast
python scripts/smoke.py --base https://<domain> --key <demo key> --frame <real frame>
```

## Out of scope

The WebSocket itself: the phone connects to Gemini directly; the backend never proxies audio. The monitor UI (WEB-03).

## When done

Update `STATUS.md`, commit `[backend] BE-05 live token, monitor, summary`, push.
