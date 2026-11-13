# Ghost Chef — API & data contract (v1)

> **This file is the single source of truth for every interface between the four tracks.**
> It refines the "Backend API" and "Data model" sections of [TECH-SPEC.md](TECH-SPEC.md). Where the two differ, this file wins; every difference is listed in [§10 Differences from TECH-SPEC](#10-differences-from-tech-spec).
>
> `contract_version: 1.0` · frozen 2026-11-13 · change it only through [§9 Change protocol](#9-change-protocol).

Who implements what:

| Interface | Provider | Consumers |
|---|---|---|
| HTTP API (§2–§6) | `backend/` | `ios/`, `web/` |
| Python package `ghostchef_ai` (§7) | `ai/` | `backend/` |
| Fixture recipe `ai/fixtures/sushi_recipe.json` (§8) | `ai/` | `backend/` (seed), `ios/` + `web/` (offline fixtures) |
| Gemini Live session config (§5) | `ai/` writes it, `backend/` serves it | `ios/` |

---

## 1. Conventions

- **Base URL:** local `http://<laptop-LAN-IP>:8000`, production `https://<railway-app>.up.railway.app` (recorded in `backend/STATUS.md` once it exists). No path prefix.
- **Auth:** every endpoint except `GET /health` requires header `X-Demo-Key: <DEMO_API_KEY>`. Missing or wrong key → `401 unauthorized`. Signed Storage URLs returned by the API need no header.
- **Bodies:** JSON (`application/json; charset=utf-8`) unless marked *multipart*. Field names are `snake_case`.
- **IDs:** UUID v4 strings. **Times:** ISO 8601 UTC, e.g. `2026-11-14T09:30:00Z`. **Durations:** seconds as numbers (`timestamp_s`) or milliseconds as integers (`latency_ms`).
- **`request_id`:** a UUID the *client* generates for every `/check` and `/watch` call. The server echoes it. The client uses it to drop stale answers (§3.4).
- **CORS:** the backend allows all origins in development and the deployed web origin in production, with `X-Demo-Key` and `Content-Type` as allowed headers.
- **Unknown fields:** clients must ignore response fields they don't know. Servers must ignore request fields they don't know. This is what makes additive changes safe.

### 1.1 Error format

Every non-2xx response has this body:

```json
{ "error": { "code": "model_timeout", "message": "Gemini did not answer within 8 s", "retryable": true, "request_id": "…or null" } }
```

| HTTP | `code` | Meaning | Client behaviour |
|---|---|---|---|
| 401 | `unauthorized` | Bad or missing `X-Demo-Key` | Show setup error. Do not retry. |
| 404 | `not_found` | Unknown recipe / step / session | Show error. Do not retry. |
| 409 | `recipe_not_ready` | Recipe is not in the status the call needs | Show status. |
| 413 | `payload_too_large` | Upload or frame over the limit | Downscale and retry once. |
| 415 | `unsupported_media` | Not MP4 / not JPEG | Show error. |
| 422 | `validation_error` | Missing or malformed field | Bug. Log it. |
| 429 | `quota_exhausted` | Gemini quota or rate limit hit, or a watch call already in flight | Back off 10 s. Watcher pauses, check shows "Can't check right now". |
| 503 | `model_unavailable` | Gemini error other than timeout/quota | Retry once after 1 s for `/check`. Never retry `/watch`. |
| 504 | `model_timeout` | Model exceeded the server budget | Same as 503. |
| 500 | `internal` | Anything else | Same as 503. |

---

## 2. Recipes and steps

### `GET /health` (no auth)

```json
{ "status": "ok", "contract_version": "1.0", "ai_mode": "fake", "storage": "memory" }
```

`ai_mode` is `fake` or `gemini`. `storage` is `memory` or `supabase`. Clients show these in their debug/settings view so nobody demos against a fake by accident.

### `POST /recipes` *(multipart)*

Fields: `video` (file, `video/mp4`, ≤ 500 MB), `title` (string, 1–80 chars), `chef_name` (string, optional), `consent` (must be the string `"true"`: the uploader confirms the chef agreed to be recorded and to the footage being processed by Gemini).

`202`:
```json
{ "recipe_id": "uuid", "status": "processing" }
```
Errors: `415`, `413`, `422` (including missing consent).

### `GET /recipes?status=published`

`status` filter is optional (`processing | review | published | failed`). Without it, returns all.

```json
{ "recipes": [ { "id": "uuid", "title": "Maki roll", "chef_name": "…", "status": "published", "step_count": 8, "created_at": "…" } ] }
```

### `GET /recipes/{id}`

```json
{
  "id": "uuid",
  "title": "Maki roll",
  "chef_name": "…",
  "status": "published",
  "error": null,
  "video_url": "https://…signed, only while status is review (for the studio scrubber), else null",
  "transcript": "full chef narration",
  "created_at": "…",
  "steps": [ "<Step>", "…" ]
}
```

`steps` is ordered by `idx` and is empty while the recipe is `processing`.

**`Step` object** (identical everywhere it appears):

```json
{
  "id": "uuid",
  "recipe_id": "uuid",
  "idx": 3,
  "title": "Spread rice",
  "key_line": "Thin layer, leave 2cm top",
  "instruction": "Full instruction, spoken on request.",
  "chef_quote": "Verbatim sentence from the chef's narration, or null",
  "timestamp_s": 74.5,
  "clip_start_s": 72.0,
  "clip_end_s": 76.5,
  "success_criteria": ["Rice layer is thin enough to see nori through it in places", "…"],
  "watch_fors": [
    {
      "id": "rice_too_thick",
      "mistake": "Rice layer is thick and covers the whole sheet",
      "headline": "Too much rice",
      "fix": "Spread thinner, 2cm nori free",
      "spoken": "There's a bit too much rice — spread it thinner and leave two centimetres of nori at the top."
    }
  ],
  "ref_image_url": "https://…signed | null",
  "clip_url": "https://…signed | null",
  "timer_s": null
}
```

| Field | Rule |
|---|---|
| `idx` | 1-based order within the recipe |
| `title` | ≤ 4 words, shown in the lens |
| `key_line` | ≤ 8 words, shown in the lens |
| `timestamp_s` | Key moment in the source video; the reference still is extracted here |
| `watch_fors[].id` | Stable `snake_case` id, unique within the step |
| `watch_fors[].headline` | ≤ 4 words |
| `watch_fors[].fix` | ≤ 8 words |
| `ref_image_url` | Chef point-of-view still for this step |
| `clip_url` | 3–5 s looping clip (nice-to-have feature) |
| `timer_s` | Optional countdown in seconds |

Signed URLs are valid for at least 2 hours. Clients download and cache the images when a session starts, so an expired URL never breaks a running session.

### `PATCH /recipes/{id}`

Body: any of `title`, `chef_name`. Returns the full recipe.

### `POST /recipes/{id}/publish`

Moves `review → published`. `409 recipe_not_ready` if the recipe is `processing` or `failed`, or if any step has no reference image. Returns the full recipe.

### `DELETE /recipes/{id}`

Deletes the recipe, its steps, sessions, events, the source video, and all derived images and clips. `204`. This exists so the chef can withdraw consent.

### `PATCH /steps/{id}`

Body: any of `title`, `key_line`, `instruction`, `success_criteria`, `watch_fors`, `timer_s`, `timestamp_s`. If `timestamp_s` changes, the server re-extracts the reference frame with ffmpeg before responding. Returns the updated `Step`. The word limits above are enforced with `422`.

---

## 3. Checking and watching

### 3.1 `POST /check` *(multipart)* — on-demand, full resolution

| Field | Type | Notes |
|---|---|---|
| `frame` | file, `image/jpeg` | Long edge ≤ 1280 px, ≤ 1.5 MB |
| `step_id` | uuid | Required |
| `request_id` | uuid | Required, client-generated |
| `session_id` | uuid | Optional. When present the server logs the result as a session event and stores the frame for the monitor. |
| `captured_at` | ISO time | Optional. When the frame was captured on the device. |

`200`:
```json
{
  "request_id": "same uuid",
  "step_id": "same uuid",
  "verdict": "pass",
  "mistake_id": null,
  "headline": "Looks right",
  "fix": "",
  "spoken": "That looks right. On to the next step.",
  "confidence": 0.86,
  "latency_ms": 1420,
  "model": "model id actually used"
}
```

| Field | Rule |
|---|---|
| `verdict` | `"pass"`, `"fix"`, or `"unsure"` |
| `mistake_id` | The `watch_fors` id when a fix matches a known mistake, else `null` |
| `headline` | ≤ 4 words |
| `fix` | ≤ 8 words; empty string for `pass` |
| `confidence` | 0.0–1.0, the model's confidence in the verdict |
| `latency_ms` | Server-measured, model call included |

`unsure` means the model cannot judge from this frame (food out of frame, blur, occlusion, criteria not visible). `headline` is then something like `"Can't tell"` and `fix` tells the wearer how to give a better view, e.g. `"Look straight down at mat"`. `unsure` is a deliberate outcome, not an error.

Server budget: 8 s, then `504 model_timeout`.

### 3.2 `POST /watch` *(multipart)* — proactive, low resolution

| Field | Type | Notes |
|---|---|---|
| `frame` | file, `image/jpeg` | Long edge ≤ 512 px, ≤ 200 KB |
| `step_id` | uuid | Required |
| `request_id` | uuid | Required |
| `session_id` | uuid | Optional. Only `warn` results are logged as events. |
| `captured_at` | ISO time | Optional |

`200`:
```json
{
  "request_id": "same uuid",
  "step_id": "same uuid",
  "status": "ok",
  "mistake_id": null,
  "headline": "",
  "fix": "",
  "spoken": "",
  "confidence": 0.0,
  "latency_ms": 640,
  "model": "model id actually used"
}
```

`status` is `"ok"` or `"warn"`. On `warn`, `mistake_id` is always one of the step's `watch_fors` ids and `headline`, `fix`, `spoken` are filled. The watcher only reports mistakes listed in `watch_fors`. It never invents new ones.

Server budget: 3.5 s, then `504`. If a `/watch` call for the same `session_id` is still running, the server answers the new one immediately with `429 quota_exhausted` and `retryable: true` (one in flight per session).

### 3.3 Client rules for the watcher (`ios/` and `web/` implement these identically)

- Interval: one frame every **2.5 s**, measured from the *end* of the previous call. Never overlap calls.
- **Debounce:** raise an alert only after **2 consecutive** responses with `status: "warn"`, the **same `mistake_id`**, and `confidence ≥ WATCH_THRESHOLD` (default **0.7**, configurable at runtime).
- The watcher is **paused** while: a `/check` is in flight, a Pass/Fix/Warning screen is showing, the user is talking to Gemini Live, or the app is not on a step card.
- After a warning is dismissed, the same `mistake_id` is muted for **20 s**. A warning that receives no input for **12 s** dismisses itself and counts as dismissed.
- Any `/watch` error is silent: the "● watching" dot turns grey until the next success. Three consecutive errors pause the watcher for 15 s.

### 3.4 Stale-result rule (mandatory)

A response is **discarded without any UI effect** if either is true when it arrives:

1. its `step_id` is not the step currently on screen, or
2. its `request_id` is not the most recent request the client sent for that endpoint.

This prevents a slow answer about an old frame from being shown as a verdict on the current state.

---

## 4. Sessions and events

### `POST /sessions`

Body: `{ "recipe_id": "uuid", "client": "ios", "device_label": "Display #4 / iPhone 15" }`. `client` is `"ios"` or `"web-sim"`.
`201`: `{ "session_id": "uuid", "started_at": "…" }`

### `POST /sessions/{id}/events`

Body:
```json
{ "kind": "step_change", "step_id": "uuid or null", "request_id": "uuid or null", "payload": { } }
```
`201`: `{ "event_id": "uuid" }`

| `kind` | Recorded by | `payload` |
|---|---|---|
| `check_pass` / `check_fix` / `check_unsure` | **server**, inside `/check` when `session_id` is sent | The full check response plus `frame_path` |
| `watch_warn` | **server**, inside `/watch` when `status` is `warn` | The full watch response plus `frame_path` |
| `step_change` | client | `{ "from_idx": 2, "to_idx": 3, "via": "pinch" }` — `via` is `pinch`, `swipe`, `voice`, `auto`, or `tap` |
| `question` | client | `{ "caption": "3–5 word caption", "transcript": "if available" }` |
| `warning_shown` / `warning_dismissed` | client | `{ "mistake_id": "…" }` |
| `show_me` | client | `{}` |
| `client_error` | client | `{ "where": "live", "detail": "…" }` — `where` is `live`, `dat`, or `network` |
| `session_end` | client | `{}` — sets `finished_at` |

Clients never post the server-recorded kinds.

### `GET /sessions?active=true&limit=5`

Most recent first. The monitor uses this to attach to the running session automatically.
```json
{ "sessions": [ { "id": "uuid", "recipe_id": "uuid", "recipe_title": "…", "client": "ios", "device_label": "…", "started_at": "…", "finished_at": null } ] }
```

### `GET /sessions/{id}`

```json
{
  "id": "uuid", "recipe_id": "uuid", "client": "ios", "started_at": "…", "finished_at": null,
  "events": [ { "id": "uuid", "kind": "check_fix", "step_id": "uuid", "request_id": "uuid", "payload": { }, "created_at": "…" } ],
  "summary": { "steps_total": 8, "steps_passed_first_try": 6, "fixes_caught": 2, "warnings": 1, "questions": 1 }
}
```
`summary` feeds the Done screen.

### `GET /sessions/{id}/monitor`

One cheap call the demo monitor polls every second.
```json
{
  "session": { "id": "uuid", "client": "ios", "device_label": "…", "started_at": "…", "finished_at": null },
  "recipe_title": "Maki roll",
  "current_step": { "…": "a full Step object" },
  "last_frame_url": "https://…signed | null",
  "last_frame_at": "…",
  "last_result": { "source": "check", "at": "…", "body": { "…": "the check or watch response" } },
  "events": [ "…last 30 events, newest first…" ],
  "latency": { "check_p50_ms": 1400, "check_max_ms": 2900, "watch_p50_ms": 650, "watch_max_ms": 1800, "n_check": 12, "n_watch": 140 }
}
```

`current_step` comes from the latest `step_change` event, else step 1. `last_frame_url` is the most recent frame the server received from either endpoint. `last_result.source` is `"check"` or `"watch"`.

---

## 5. Gemini Live (voice)

### `GET /live-token?recipe_id=<uuid>&session_id=<uuid>`

```json
{
  "token": "auth_tokens/…",
  "expires_at": "…",
  "new_session_expires_at": "…",
  "model": "live model id",
  "api_version": "v1beta",
  "locked": true,
  "config": {
    "system_instruction": "…full text, contains the recipe, all steps, and the chef transcript…",
    "response_modalities": ["AUDIO"],
    "voice": null,
    "tools": [ { "function_declarations": [ "…" ] } ],
    "session_resumption": true
  }
}
```

- `token` is an ephemeral token used in place of an API key. The phone opens the Live WebSocket **directly** with it. The real Gemini API key never leaves the backend.
- `expires_at`: messages may be sent until then (Gemini default 30 min). `new_session_expires_at`: a session must be opened before then (Gemini default 1 min).
- `locked` is `true` when model and config are bound to the token server-side. The client must then not send its own `config`. `config` is still returned so the client can log and display it.
- The token is single-use for opening a session. To start a new session (app restart), call `/live-token` again.

### 5.1 Step context updates

On every step change the client sends one text message into the Live session, exactly in this form. The system instruction tells the model not to answer it:

```
[CONTEXT] Cook is now on step 3 of 8: "Spread rice". Do not reply to this message.
```

### 5.2 Voice commands as function calls

The Live config declares these functions. The client executes them through the same code paths as the gestures and replies with the tool response shown.

| Function | Arguments | Client action | Tool response |
|---|---|---|---|
| `check_my_work` | none | Runs the `/check` flow | `{ "status": "done", "note": "The app has shown and spoken the result. Say nothing more." }` |
| `next_step` | none | Advances one step | `{ "status": "done", "now_on": "4 of 8: Roll" }` |
| `previous_step` | none | Goes back one step | Same shape as `next_step` |
| `show_me` | none | Plays the chef clip (or shows the reference still) | `{ "status": "done" }` |
| `repeat_instruction` | none | None | `{ "instruction": "<full instruction text>" }` — the model reads it out |

### 5.3 Who speaks what

- **`spoken` strings from `/check` and `/watch` are always spoken by on-device text-to-speech.** That path is deterministic and works when Live is down.
- **Gemini Live speaks only answers to questions** and `repeat_instruction`.
- While on-device TTS is speaking, Live audio output is ducked or queued. They must never talk over each other.

---

## 6. Data model (Supabase Postgres)

```sql
create table recipes (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  chef_name text,
  video_path text,                 -- Storage path, bucket "videos"
  transcript text,
  status text not null,            -- 'processing' | 'review' | 'published' | 'failed'
  error text,                      -- human-readable reason when status = 'failed'
  consent_at timestamptz,          -- when the uploader confirmed consent
  created_at timestamptz not null default now()
);

create table steps (
  id uuid primary key default gen_random_uuid(),
  recipe_id uuid not null references recipes on delete cascade,
  idx int not null,                -- 1-based
  title text not null,
  key_line text not null,
  instruction text not null,
  chef_quote text,
  timestamp_s numeric not null,
  clip_start_s numeric,
  clip_end_s numeric,
  success_criteria text[] not null default '{}',
  watch_fors jsonb not null default '[]',   -- [{id, mistake, headline, fix, spoken}]
  ref_image_path text,             -- Storage path, bucket "media"
  clip_path text,                  -- Storage path, bucket "media"
  timer_s int,
  unique (recipe_id, idx)
);

create table sessions (
  id uuid primary key default gen_random_uuid(),
  recipe_id uuid not null references recipes on delete cascade,
  client text not null,            -- 'ios' | 'web-sim'
  device_label text,
  started_at timestamptz not null default now(),
  finished_at timestamptz
);

create table session_events (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references sessions on delete cascade,
  step_id uuid references steps on delete set null,
  kind text not null,
  request_id uuid,
  payload jsonb not null default '{}',
  created_at timestamptz not null default now()
);
```

Storage buckets (all private):

| Path | Content |
|---|---|
| `videos/{recipe_id}/source.mp4` | Chef recording |
| `media/{recipe_id}/steps/{idx}/ref.jpg` | Reference still |
| `media/{recipe_id}/steps/{idx}/clip.mp4` | "Show me" clip |
| `frames/{session_id}/{request_id}.jpg` | Wearer frames kept for the monitor |

Row Level Security is enabled on all four tables with no policies for `anon`. Only the backend (service role) reads and writes.

---

## 7. Internal interface: `backend/` ⇄ `ai/`

`ai/` ships an installable Python package named **`ghostchef_ai`** (`pip install -e ../ai`). `backend/` imports it and calls nothing else in `ai/`. All Gemini calls and all prompts live inside this package.

```python
# ghostchef_ai/__init__.py — the complete public surface
from ghostchef_ai.schemas import (
    WatchFor, StepSpec, RecipeDraft, CheckResult, WatchResult, LiveConfig, LiveToken,
)
from ghostchef_ai.errors import AIError, AITimeout, AIQuotaError, AIUnavailable, AIInvalidOutput

async def extract_recipe(video_path: Path, *, title_hint: str | None = None) -> RecipeDraft: ...

async def check_frame(frame_jpeg: bytes, step: StepSpec, ref_image_jpeg: bytes | None,
                      *, timeout_s: float = 8.0) -> CheckResult: ...

async def watch_frame(frame_jpeg: bytes, step: StepSpec,
                      *, timeout_s: float = 3.5) -> WatchResult: ...

def build_live_config(recipe_title: str, chef_name: str | None, transcript: str,
                      steps: list[StepSpec]) -> LiveConfig: ...

async def mint_live_token(live_config: LiveConfig) -> LiveToken: ...

def model_ids() -> dict[str, str]: ...   # keys: "video", "check", "watch", "live"
```

Pydantic models. Field names match §2, §3 and §5 exactly.

```python
class WatchFor(BaseModel):
    id: str
    mistake: str
    headline: str
    fix: str
    spoken: str

class StepSpec(BaseModel):
    idx: int
    title: str
    key_line: str
    instruction: str
    chef_quote: str | None = None
    timestamp_s: float
    clip_start_s: float | None = None
    clip_end_s: float | None = None
    success_criteria: list[str]
    watch_fors: list[WatchFor]
    timer_s: int | None = None

class RecipeDraft(BaseModel):
    title: str
    transcript: str
    steps: list[StepSpec]

class CheckResult(BaseModel):
    verdict: Literal["pass", "fix", "unsure"]
    mistake_id: str | None
    headline: str
    fix: str
    spoken: str
    confidence: float
    model: str

class WatchResult(BaseModel):
    status: Literal["ok", "warn"]
    mistake_id: str | None
    headline: str
    fix: str
    spoken: str
    confidence: float
    model: str

class LiveConfig(BaseModel):
    model: str
    system_instruction: str
    response_modalities: list[str]
    voice: str | None
    tools: list[dict]
    session_resumption: bool

class LiveToken(BaseModel):
    token: str
    expires_at: datetime
    new_session_expires_at: datetime
    locked: bool
```

Rules:

- **Fake mode.** With env `GHOSTCHEF_AI_FAKE=1` every function returns deterministic, contract-valid data without any network call (details in [ai/tasks/01](../ai/tasks/01-package-skeleton-and-fixture.md)). Backend development and tests never need a Gemini key.
- **Errors.** Functions raise only `AIError` subclasses. Mapping to HTTP: `AITimeout → 504 model_timeout`, `AIQuotaError → 429 quota_exhausted`, `AIUnavailable` and `AIInvalidOutput → 503 model_unavailable`.
- **Env.** The package reads `GEMINI_API_KEY` and the optional model overrides `GHOSTCHEF_MODEL_VIDEO`, `GHOSTCHEF_MODEL_CHECK`, `GHOSTCHEF_MODEL_WATCH`, `GHOSTCHEF_MODEL_LIVE`. It reads no other configuration.
- **No I/O beyond Gemini.** The package never touches Supabase or ffmpeg, and reads nothing from disk except `video_path`. `backend/` owns storage, ffmpeg, HTTP, and latency measurement.
- **ffmpeg** frame and clip extraction is done by `backend/`, using the `timestamp_s`, `clip_start_s`, `clip_end_s` values in the `RecipeDraft`.

---

## 8. Fixture recipe

`ai/fixtures/sushi_recipe.json` is a `RecipeDraft` (same schema as §7). Next to it, `ai/fixtures/images/step-<idx>.jpg` holds one reference still per step.

- First version: hand-written by the `ai/` track with placeholder images, available from the first hour so nobody is blocked.
- Later versions: replaced by real ingestion output from the team's own chef footage. The file path and schema do not change.
- `backend/` seeds the database from it. `ios/` and `web/` may bundle a copy for offline UI work, but must load real data from the API in any integrated run.

---

## 9. Change protocol

1. Prefer **additive** changes (new optional field, new endpoint, new event kind). They cannot break a consumer that follows §1 "Unknown fields". Bump to `1.x`.
2. Whoever needs the change edits this file in a commit that touches **only** `docs/API-CONTRACT.md`, adds a line to the changelog below, and posts the commit link in the team chat. The `backend/` owner must agree before it is pushed, because they implement it.
3. A **breaking** change (rename, removal, type change) additionally needs a yes from every consuming track, and bumps `contract_version` to `2.0`. Avoid these after gate G1.
4. Implementation must not drift from this file. If code and contract disagree, fix one of them the same hour.

### Changelog

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-11-13 | Initial contract derived from TECH-SPEC.md. |

---

## 10. Differences from TECH-SPEC

These are additions made while turning the spec into a buildable contract. None removes a spec feature. They are recorded as decision D-10 in [DECISIONS-AND-RISKS.md](DECISIONS-AND-RISKS.md) and can be reverted through §9.

| # | Difference | Why |
|---|---|---|
| 1 | `verdict` gains a third value, `unsure` | The Meta rubric scores useful uncertainty. A forced pass/fix on a blurry frame produces confident mistakes on stage. |
| 2 | `request_id`, `step_id`, `latency_ms`, `model` on `/check` and `/watch`; the stale-result rule | Stops an old frame's answer being shown for the current state. Gives measured latency for judging evidence. |
| 3 | `watch_fors` items gain `id`, `headline`, `spoken` | The spec's `/watch` response returns `mistake_id` and display strings, but the spec's `watch_fors` had only `{mistake, fix}`. |
| 4 | `POST /recipes/{id}/publish`, `PATCH /recipes/{id}`, `DELETE /recipes/{id}`, the `consent` field | The spec says "then publish" without an endpoint. Delete and consent support the trust criterion. |
| 5 | `GET /health`, `GET /sessions`, `GET /sessions/{id}`, `GET /sessions/{id}/monitor` | Needed by the Done screen and by the audience-facing demo monitor. |
| 6 | The server records check/watch events itself | One source of truth. The phone does not double-post. |
| 7 | Extra event kinds: `step_change`, `check_unsure`, `warning_shown`, `warning_dismissed`, `show_me`, `client_error`, `session_end` | The monitor and the Done summary need them. The spec's four kinds are unchanged. |
| 8 | `/live-token` takes `recipe_id` and returns the config, tool declarations, and lock state | Makes the voice commands ("check", "next", "show me") implementable as Live function calls. |
| 9 | Columns `recipes.error`, `recipes.consent_at`, `sessions.client`, `sessions.device_label`, `session_events.request_id` | Support the items above. |
| 10 | The `ghostchef_ai` package boundary (§7) and fake mode | Lets `backend/` and `ai/` be built on different laptops without touching each other's files. |
