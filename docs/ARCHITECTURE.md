# Ghost Chef — architecture

> How the pieces fit, what each technology is responsible for, what we assume about devices and APIs, and how the system behaves when something fails.
> Interfaces are specified in [API-CONTRACT.md](API-CONTRACT.md). The product concept is [TECH-SPEC.md](TECH-SPEC.md).
>
> Labels: **[TEAM]** stated by the team · **[VERIFIED-DOC]** read in vendor documentation on 2026-11-13, not tested by us · **[OPEN]** untested. Nothing in this file is marked "tested" until a track records it in its `STATUS.md`.

## 1. Components and folders

| Folder | Component | Runs on | Talks to |
|---|---|---|---|
| [`ios/`](../ios/README.md) | iOS app (Swift, SwiftUI, Meta DAT SDK), **one app with two modes: Chef (record a recipe) and Cook (follow along)** | iPhone paired with the glasses | Glasses (DAT over Bluetooth), backend (HTTPS), Supabase Storage (one signed upload per recording), Gemini Live (WebSocket) |
| [`backend/`](../backend/README.md) | FastAPI service: recipes, check, watch, sessions, live tokens, ffmpeg, storage | Laptop in development, Railway in production | Supabase, `ghostchef_ai` package |
| [`ai/`](../ai/README.md) | Python package `ghostchef_ai`: every prompt and every Gemini call; fixture recipe; evaluation | Imported by the backend; CLI on a laptop | Gemini API |
| [`web/`](../web/README.md) | Static web app: cook-along **simulator**, recipe **review page** (review / edit / publish, plus a dev-fallback MP4 upload), demo **monitor**; plus the pitch pack | Any browser; served by the backend at `/app/` | Backend (HTTPS); Supabase Storage only for the dev-fallback upload |

```
 ┌──────────────────────┐  Bluetooth / DAT  ┌─────────────────────────────┐
 │ Meta Ray-Ban Display │ ◄───────────────► │ ios/  iPhone app            │
 │ camera · mic · lens  │                   │  FrameSource (swappable)    │
 │ speakers · inputs    │                   │  Chef mode: Recorder + marks│
 │                      │                   │  CookSession state machine  │
 └──────────────────────┘                   │  Watcher loop + debounce    │
                                            │  LensModel → 2 renderers    │
                                            │  LiveClient (voice)         │
                                            └──────┬───────────────┬──────┘
                                         HTTPS     │               │ WebSocket, ephemeral token
                                                   ▼               ▼
 ┌───────────────────────┐  HTTPS   ┌───────────────────────┐   ┌──────────────────┐
 │ web/  browser         │ ───────► │ backend/  FastAPI     │   │ Gemini Live API  │
 │  simulator (webcam)   │          │  /recipes /steps      │   └──────────────────┘
 │  review page          │          │  /check /watch        │
 │  demo monitor         │          │  /sessions /live-token│
 └───────────────────────┘          │  ffmpeg · jobs        │
                                    └──────┬──────────┬─────┘
                                 import    │          │ service role
                                           ▼          ▼
                              ┌────────────────┐   ┌──────────────────────┐
                              │ ai/            │   │ Supabase             │
                              │ ghostchef_ai   │   │ Postgres + Storage   │
                              └───────┬────────┘   └──────────────────────┘
                                      ▼
                              Gemini API (video, vision, token minting)
```

Two things in this diagram are additions to TECH-SPEC, both for the weekend's practical needs:

- **Web simulator.** A browser client that runs the same cook-along loop with a webcam. It lets `backend/` and `ai/` be tested end to end without the Mac, the iPhone, or the glasses, and it is the demo of last resort. It is a development tool and a fallback, never presented as the Meta deliverable.
- **Demo monitor.** Glasses are personal: the audience cannot see the lens. The monitor shows the wearer's latest frame, the chef's reference, the verdict, and the event timeline on a laptop or projector.

## 2. Technology roles

| Technology | Its job here | Why it is not replaceable by something simpler |
|---|---|---|
| **Meta glasses + DAT** | First-person camera frames, in-lens step cards, hands-free input, audio in/out | The learner's viewpoint must match the chef's; hands are occupied |
| **Gemini — video understanding** (`extract_recipe`) | Turns one chef recording into ordered steps with timestamps, success criteria, common mistakes, transcript | Needs joint understanding of what is said and what the hands do, with timestamps |
| **Gemini — multi-image vision** (`check_frame`) | Compares the learner's frame with the chef's reference frame under the step's criteria → pass / fix / unsure | The judgment is "same as the reference in the ways that matter", not object detection |
| **Gemini — fast vision** (`watch_frame`) | Every 2.5 s, classifies a low-res frame against the step's known mistakes only | Open-vocabulary mistakes defined in plain language per recipe, no training |
| **Gemini Live** | Spoken questions answered from the chef's transcript; voice commands arrive as function calls | Natural interruption and low-latency audio |
| **Structured output** | Every non-Live Gemini call returns schema-validated JSON | The app logic must never parse prose |
| **Application code (ours)** | Step state, debounce, stale-answer rejection, timeouts, pause rules, uncertainty handling, session log | A model alone over-talks or stays silent; control lives in ordinary code |
| **FastAPI backend** | Keeps keys server-side, runs long ingestion jobs and ffmpeg, mints Live tokens, records events | No serverless timeout; single place for latency measurement |
| **Supabase** | Postgres for recipes/steps/sessions/events; private Storage for video, stills, clips, frames | Managed, signed URLs, quick to set up |

## 3. Flows

### 3.1 Ingestion (chef → recipe)

1. **Record (iOS, Chef mode).** The chef cooks wearing the glasses and narrates. The app writes the DAT camera stream and mic audio to an MP4 on the phone (no clip-length limit, unlike the glasses' built-in capture). The lens shows "● REC 03:12". Each Neural Band pinch saves a **step mark** (seconds since start) into `step_marks_s`.
2. **Create.** On stop: `POST /recipes` with title, `step_marks_s`, consent → `201 uploading` + a signed Supabase Storage upload URL.
3. **Upload.** The app uploads the MP4 **directly to Supabase Storage** (resumable TUS, because of venue Wi-Fi), never through FastAPI. Dev fallback: the review page uploads any MP4 through the same signed URL with a simple `PUT`.
4. **Process.** `POST /recipes/{id}/process` → `processing`. The background job downloads the video from Storage and calls `ghostchef_ai.extract_recipe(video_path, step_marks_s=…)` → `RecipeDraft` (steps, timestamps, transcript); the marks are hints.
5. Backend runs ffmpeg per step: reference still at `timestamp_s`, optional clip `clip_start_s…clip_end_s`; uploads them to Storage; sets status `review` (or `failed` with `error`).
6. **Review (web page).** The chef or a teammate opens the review page on a laptop, which polls the status, edits text / re-picks timestamps → `PATCH /steps/{id}` → `POST /recipes/{id}/publish` → `published`.

### 3.1b Delivery (recipe → cook's app)

1. Cook mode lists the library: `GET /recipes?status=published` (no accounts; every published recipe is visible).
2. The cook picks one: `GET /recipes/{id}` → steps + signed URLs.
3. **The app downloads every reference image and clip before cooking starts.** During cooking only `/check`, `/watch` and Gemini Live need the network.
4. The phone sends the current step's image or clip to the glasses display through DAT.

Pitch framing: chefs share a recipe link or QR code and followers open it in the app. Not built this weekend.

**The demo never depends on this running live.** One seeded, pre-reviewed recipe is always present. **[TEAM]**

### 3.2 On-demand check

Pinch, tap, or "check" → client grabs one full-res frame → `POST /check` with `request_id`, `step_id`, `session_id` → backend loads the step and its reference image → `check_frame` → response → client applies the stale-result rule → Pass / Fix / Unsure screen + on-device TTS of `spoken`.

### 3.3 Proactive watcher

Client loop every 2.5 s → low-res frame → `POST /watch` → `watch_frame` against the step's `watch_fors` → client debounce (2 consecutive, same `mistake_id`, confidence ≥ threshold) → Warning screen + TTS. Rules: [API-CONTRACT §3.3](API-CONTRACT.md#33-client-rules-for-the-watcher-ios-and-web-implement-these-identically).

Gemini Live is deliberately **not** the watcher. **[TEAM]**

### 3.4 Voice

Session start → `GET /live-token` → phone opens the Live WebSocket with the ephemeral token → microphone audio streams up, answers stream down → on each step change the phone sends a `[CONTEXT]` line → voice commands arrive as function calls and run the same code paths as gestures. Details: [API-CONTRACT §5](API-CONTRACT.md#5-gemini-live-voice).

## 4. Environments and configuration

| Environment | Backend | Storage | AI | Used for |
|---|---|---|---|---|
| **Mock** | Laptop, `uvicorn` | `STORAGE=memory` | `GHOSTCHEF_AI_FAKE=1` | First hours; UI work; tests |
| **Local real** | Laptop, reachable on the LAN | `memory` or `supabase` | Real Gemini | Integration at the table |
| **Production** | Railway | Supabase | Real Gemini | The demo |
| **Emergency** | A laptop on a phone hotspot | `memory` + local files | Real Gemini | Venue Wi-Fi or Railway failure |

Secrets and where they live (never committed; `.example` files show the names):

| Variable | Used by | Notes |
|---|---|---|
| `GEMINI_API_KEY` | `ai/` (CLI, eval), `backend/` | Server-side only |
| `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` | `backend/` | Service role; never in a client |
| `DEMO_API_KEY` | `backend/` (expects it), `ios/`, `web/` (send it) | A shared random string; rotate after the event |
| `API_BASE_URL` | `ios/`, `web/` | Local LAN IP or the Railway URL |

Browsers only grant camera access on `https://` or `localhost`. The web simulator therefore works from `localhost` on a laptop or from the deployed HTTPS URL, but **not** from a LAN IP over plain HTTP.

## 5. Device and API assumptions

Each row must end the weekend as either *tested* (with the result written in the named `STATUS.md`) or *explicitly dropped*.

### 5.1 Meta glasses and DAT

| # | Assumption | Status | Resolved by |
|---|---|---|---|
| A1 | We get a Ray-Ban Meta **Display** pair for development and for the demo slot | **[OPEN]** — ten Display and ten Gen 2 pairs are shared across teams **[TEAM]**; nothing is booked for us | Meta booth; IOS-02 |
| A2 | DAT for **iOS** supports Display output | **[VERIFIED-DOC]** — `MWDATDisplay` since 0.7.0; components `FlexBox`, `Text`, `Button`, `Image`, `Icon`, `VideoPlayer`, `ButtonGroup` ([changelog](https://github.com/facebook/meta-wearables-dat-ios/blob/main/CHANGELOG.md)) | IOS-02 |
| A3 | Latest iOS SDK is **1.0.1** (2026-10-09), Swift Package at `https://github.com/facebook/meta-wearables-dat-ios`, minimum **iOS 17.2** | **[VERIFIED-DOC]** | Pin in IOS-02 |
| A4 | An image and two lines of text can be combined in one lens view | **[OPEN]** — `FlexBox` + `Image` + `Text` exist; the actual layout limits are unknown | IOS-02 |
| A5 | Camera stream and display UI run **at the same time** | **[TEAM]** "confirmed with Meta" verbally; untested | IOS-02 |
| A6 | Gemini Live audio can use the glasses' Bluetooth mic and speakers **while** DAT streams video | **[TEAM]** "confirmed with Meta" verbally; untested | IOS-02 |
| A7 | Neural Band pinch / swipe reach our app | **[OPEN]** — the iOS changelog does not mention Neural Band. It lists an *experimental* `MWDATInputs` module (1.0.0) and display `Button` / `ButtonGroup`. The spec's gesture table may have to map onto display buttons, captouch, or voice | IOS-02 |
| A8 | Camera frames are good enough to judge filling placement and spread coverage | **[OPEN]** — documented stream sizes are 504×896 (medium) and 720×1280 (high); frame rate and real quality unknown | IOS-02, AI-03 |
| A9 | Looking down at a board puts the work in frame | **[OPEN]** — a camera near the eyes does not guarantee the hands are in view | IOS-02, AI-03 |
| A10 | Development without hardware is possible | **[VERIFIED-DOC]** — `MockDeviceKit` with a phone-camera mock feed (0.6.0), `pairGlasses(model:)` (0.8.0), mock display preview (1.0.0) | IOS-02 |
| A11 | The Web Apps route cannot replace DAT for us | **[TEAM]** + consistent with Meta's FAQ, which lists position, location, Neural Band wrist motion and input for Web Apps but no camera ([FAQ](https://developers.meta.com/wearables/faq/)) | Settled (D-03) |
| A12 | Full toolkit capabilities are available where we are | **[OPEN]** — the FAQ says only users in "AI glasses supported countries" get full capabilities; also needs Developer Mode enabled through the Meta AI app | Meta booth; IOS-02 |
| A13 | On-site DAT help covers iOS | **[OPEN]** — the named mentor is listed as an *Android* DAT mentor **[TEAM]** | Ask at the booth |

Meta publishes agent tooling for the SDK: a Claude Code plugin (`claude plugin marketplace add facebook/meta-wearables-dat-ios`, then `claude plugin install mwdat-ios@mwdat-ios-marketplace`) and a docs MCP server at `https://mcp.developer.meta.com/wearables`. **[VERIFIED-DOC]** The `ios/` track installs these instead of relying on remembered API names.

### 5.2 Gemini

| # | Assumption | Status | Resolved by |
|---|---|---|---|
| G1 | We have a working API key with event credits | **[OPEN]** — credits are reportedly available to up to 400 teams; participants must be 18+ **[TEAM]** | AI-02 |
| G2 | Model IDs | **[VERIFIED-DOC]**, account access **[OPEN]** — the public models page lists Gemini 4 models (`gemini-4-carbon`, `gemini-4-argon`, `gemini-4-hydrogen`), stable `gemini-3.8-flash`, `gemini-3.6-flash`, `gemini-3.5-flash-lite`, and Live models `gemini-3.8-live`, `gemini-3.8-live-extended-thinking`. `gemini-2.5-flash` and `gemini-2.5-pro` are deprecated. Which of these the team's key can call, and at what rate, is unverified | AI-02 writes the chosen IDs to `ai/STATUS.md` |
| G3 | Ephemeral tokens work for a phone-opened Live session | **[VERIFIED-DOC]** — preview feature; `client.auth_tokens.create(...)` on API version `v1beta`; defaults: 1 use, 1 minute to open a session, 30 minutes to send messages; can be locked to a model and config; a non-SDK client passes the token as an `access_token` query parameter or `Authorization: Token <token>` header; reconnecting needs session resumption about every 10 minutes | AI-05, IOS-05 |
| G4 | The watcher's call volume fits our rate limit | **[OPEN]** — one call per 2.5 s is ~24 requests per minute per active session. Limits are per project and tier | AI-02 reads the real limits in AI Studio |
| G5 | `/check` answers in 1–2 s and `/watch` in under 2.5 s end to end | **[OPEN]** — a target from the spec, not a measurement | AI-02 baseline, AI-07 |
| G6 | A single frame is enough to tell "filling piled in the middle" from "even layer to the edges" | **[OPEN]** — the central product risk | AI-03, AI-04, AI-07 |
| G7 | There is no Swift SDK path we can rely on for Live with ephemeral tokens | **[OPEN]** — plan is a raw WebSocket client; verify the endpoint and message shapes in the current Live API reference before writing it | IOS-05 |

Google's Gemini API docs moved: `ai.google.dev/gemini-api/docs/*` now redirects to `aistudio.google.com/docs/*`. **[VERIFIED-DOC]**

## 6. Failure behaviour

The rule: **the wearer always knows whether the system is watching, and never receives a verdict about a state that is no longer true.**

| Failure | Detection | What the wearer experiences | Recovery |
|---|---|---|---|
| Camera permission denied | DAT / AVFoundation permission result | Phone screen explains what is needed; lens shows "Camera off" | Re-request; deep-link to Settings |
| Glasses disconnect mid-session | DAT device state listener | Spoken "Glasses disconnected"; phone shows status; session state is kept | Auto-resume on reconnect at the same step; option to continue with the phone camera |
| Display unavailable (Gen 2 pair, or display error) | `supportsDisplay` false or display start fails | Audio-only mode: step title + key line spoken on step change, results spoken | Automatic; no feature is lost except "show me" |
| Audio route lost / too noisy | Audio session route change; user toggle | Display-only mode: results as headline + fix; voice Q&A unavailable | Push-to-talk toggle; reconnect |
| Network offline | Request error | Dot turns grey; check shows "No connection" | Step cards and reference images keep working from cache; retry on next check |
| `/watch` error or timeout | Non-200 / client timeout 4 s | Nothing, except the grey dot | Next tick; 3 in a row → pause 15 s |
| `/check` error or timeout | Non-200 / client timeout 10 s | "Can't check right now" + spoken equivalent | One automatic retry for 503/504; then manual |
| Gemini quota exhausted | `429` | Watcher pauses 10 s; check says "Can't check right now" | Backoff; operator can switch the watch model or slow the interval in settings |
| Low-confidence or unjudgeable frame | `verdict: unsure` | "Can't tell" + how to give a better view | Wearer re-frames and re-checks |
| Stale answer | Stale-result rule | Nothing | Discarded silently |
| Step changed while a check is pending | Stale-result rule | The pending spinner clears | Discarded silently |
| Live session drops | WebSocket close | Mic icon shows unavailable; everything else works | Reconnect with session resumption, else fetch a new token |
| Live talks over a result | Arbitration in the audio layer | Result TTS wins; Live is ducked | Automatic |
| Backend down | `/health` fails | Phone shows "Server unreachable" | Operator switches base URL to the emergency laptop |
| Signed URL expired | Image load fails | Nothing: images are cached at session start | Refetch recipe |
| Chef upload interrupted | TUS error / app backgrounded | Chef mode shows upload progress and "Retrying…"; the MP4 stays on the phone | TUS resumes from the last chunk; else a simple `PUT` retry; after 2 h the recipe becomes `failed` ("upload never completed") |
| Ingestion fails | Job exception | Review page shows `failed` with the reason | Re-upload; the seeded recipe is unaffected |

Implemented in IOS-07 and BE-07; tested in the recovery checklist in [EVALUATION.md](EVALUATION.md#6-recovery-tests).

## 7. Security and privacy

- The Gemini API key and the Supabase service key exist only on the backend. The phone receives ephemeral Live tokens, signed Storage download URLs, and — in Chef mode — one signed **upload** URL scoped to `videos/<recipe_id>/source.mp4`. **[TEAM]**
- Every endpoint except `/health` requires the shared `X-Demo-Key`.
- Uploads are limited by type (MP4) and size; because the video bypasses FastAPI, the ingestion job checks size and runs `ffprobe` before anything else, and marks the recipe `failed` if either fails. Frames are limited by type (JPEG) and size. Storage paths are scoped per recipe and per session.
- Row Level Security is on for all tables; clients never touch Supabase tables. The only direct client → Supabase call is the signed, single-object video upload. **[TEAM]**
- The repository is public and MIT-licensed submissions are expected by the event FAQ, so no key, token, or personal footage is ever committed. See `.gitignore`.
- Only frames from `/check` calls and from `/watch` calls that returned `warn` are stored. Deleting a recipe deletes its sessions and frames.
