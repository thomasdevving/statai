# Ghost Chef — Technical Spec

> Junction 2026 · Meta track (Meta Ray-Ban Display) · Google AI / Gemini track
> Companion to [CONCEPT.md](CONCEPT.md). Decisions agreed 2026-11-13.

## Summary

A chef records a recipe once while wearing Meta Ray-Ban Display glasses. Gemini turns the recording into steps, each with a point-of-view reference image, success criteria, and common mistakes to watch for. A cook then follows along wearing the glasses. The app shows each step in the lens, checks their work when asked, warns proactively when something goes wrong, and answers spoken questions grounded in the chef's own method.

**Demo:** volunteer rolls sushi on stage, makes a mistake (too much rice), glasses catch it and show the chef's reference, they fix it, ✓. They ask a question out loud and get an answer.

---

## Tech stack

| Layer | Choice | Owner |
|---|---|---|
| Glasses | Meta Ray-Ban Display + Meta Neural Band | — |
| Glasses SDK | Meta Wearables **Device Access Toolkit (DAT)**, iOS | Teammate |
| Phone app | iOS / Swift (Xcode, iOS 17.2+). **One app, two modes: Chef (record) and Cook (follow along)** | Teammate (has Mac + iPhone) |
| Voice Q&A | **Gemini Live API**, native audio, opened directly from phone with ephemeral token | Teammate (client) / Stelios (token) |
| Backend | **Python FastAPI** on **Railway** | Stelios |
| AI SDK | `google-genai` Python SDK (video understanding, frame checks) | Stelios |
| Media processing | ffmpeg (reference frames, step clips) | Stelios |
| Database + storage | **Supabase** (Postgres + Storage) | Stelios |
| Review web page | Small web page served by FastAPI. **Review/edit/publish only**, plus an MP4 upload as a dev fallback | Stelios |

### Why these choices

- **DAT, not Web Apps:** the Web Apps path for Ray-Ban Display exposes motion, GPS, Neural Band, and local storage, but no camera. Ghost Chef needs the camera, so the native DAT SDK is required.
- **iOS:** teammate has Mac + iPhone and owns the app. Backend dev works on Linux.
- **Thin backend:** keeps the Gemini API key off the phone, handles long video jobs (no serverless timeouts), and runs ffmpeg.
- **Gemini Live directly from phone:** lowest latency for voice. Backend only mints short-lived ephemeral tokens.

---

## Architecture

```
 ┌──────────────────────┐   Bluetooth/DAT   ┌──────────────────────────────┐
 │ Meta Ray-Ban Display │ ◄──────────────►  │ iOS app (Swift + DAT)        │
 │ camera · mic · lens  │                   │ - camera source (swappable)  │
 │ Neural Band gestures │                   │ - display UI state machine   │
 └──────────────────────┘                   │ - watcher loop (2–3 s)       │
                                            │ - Gemini Live session        │
                                            └───────┬──────────────┬───────┘
                                                    │ HTTPS        │ WebSocket (ephemeral token)
                                                    ▼              ▼
                              ┌──────────────────────────┐   ┌──────────────────┐
  Review web page ──────────► │ FastAPI backend (Railway)│   │ Gemini Live API  │
  (review / edit / publish)   │ - ingestion pipeline     │   └──────────────────┘
                              │ - /check, /watch         │
                              │ - /live-token            │──► Gemini (video + vision)
                              └────────────┬─────────────┘
                                           ▼
                              ┌──────────────────────────┐
                              │ Supabase                 │
                              │ Postgres + Storage       │
                              └──────────────────────────┘
```

**Camera source is swappable:** iPhone camera (until glasses arrive), DAT mock device if available, and the real glasses stream. Everything downstream only sees "a frame".

---

## Flows

### 1. Chef recording → recipe (ingestion)

**Record (iOS app, Chef mode).**
- The chef cooks while wearing the glasses and talks through each step.
- The app records the DAT camera stream and mic audio to an MP4 on the phone. There is no clip-length limit, unlike the glasses' built-in capture.
- The lens shows a minimal "● REC 03:12" indicator.
- A Neural Band pinch **marks a new step**. These marks are saved as `step_marks_s[]` and passed to Gemini as step-boundary hints.

**Upload.**
1. The app calls `POST /recipes` with the title and step marks. The backend creates the recipe with status `uploading` and returns a **signed Supabase Storage upload URL**.
2. The app uploads the MP4 **directly to Supabase Storage**, not through FastAPI, using resumable upload because of venue Wi-Fi.
3. The app calls `POST /recipes/{id}/process`, and status becomes `processing`.

**Dev fallback:** the review web page can upload any MP4 (for example, phone footage) through the same signed-URL flow. This lets the pipeline be built and tested before the glasses arrive.

**Process (background job on the backend).**
1. Download the video from Storage and send it to the Gemini Files API.
2. Gemini video understanding returns structured JSON steps (schema below) plus the transcript, using the step marks as hints.
3. ffmpeg extracts, for each step:
   - one **reference frame** at the step's key timestamp
   - one **3–5 s looping clip** for "show me"
4. Upload the frames and clips to Storage. Status becomes `review`.

**Review (web page).** The chef or a teammate opens the review page on a laptop. The page polls the status. They check the steps, edit text, re-pick a reference frame by timestamp, then press **Publish**. Status becomes `published`.

### 1b. Recipe → cook's app (delivery)

1. Cook mode calls `GET /recipes?status=published` to show the recipe library. For the hackathon, all published recipes are visible to everyone, with no accounts.
2. The cook picks a recipe. `GET /recipes/{id}` returns the steps plus signed URLs for the reference images and clips.
3. **The app downloads every image and clip before cooking starts.** During cooking, only `/check`, `/watch` and Gemini Live need the network, so step changes are instant on bad Wi-Fi.
4. The phone sends the current step's image or clip to the glasses display through DAT.

In the pitch: chefs share a recipe link or QR code, and followers open it in the app.

### 2. Cook-along

- The app loads the recipe and shows the step card.
- **Proactive watcher:** every ~2–3 s, the phone sends a low-res frame to `POST /watch` along with the current step id. The backend compares the frame against the step's `watch_fors`. The app alerts only on high confidence **and 2 consecutive hits** (debounce), so false alarms don't spam the display.
- **On-demand check:** the user pinches or says "check". The phone sends a full-res frame to `POST /check`, which compares it with the chef's reference image and `success_criteria` and returns pass or fix.
- **Talk-back:** a Gemini Live session runs throughout. Its system prompt includes the chef transcript, the full recipe, and the current step, which is updated on every step change. Answers come back as native audio through the glasses speakers.

> Gemini Live is **not** used as the watcher. Left to decide when to speak, Live tends to either over-talk or stay silent. A polling classifier with debouncing is controllable and demo-safe.

---

## Data model (Supabase)

```sql
recipes (
  id uuid pk,
  title text,
  chef_name text,
  video_path text,            -- Storage path
  transcript text,            -- chef narration, used to ground Q&A
  step_marks_s numeric[],     -- chef's pinch marks while recording (step-boundary hints)
  status text,                -- 'uploading' | 'processing' | 'review' | 'published' | 'failed'
  created_at timestamptz
)

steps (
  id uuid pk,
  recipe_id uuid fk -> recipes,
  idx int,                    -- 1-based order
  title text,                 -- ≤ 4 words, shown in lens
  instruction text,           -- full instruction (spoken on request)
  key_line text,              -- ≤ 8 words, shown in lens
  chef_quote text,
  timestamp_s numeric,        -- key moment in source video
  clip_start_s numeric,
  clip_end_s numeric,
  success_criteria text[],
  watch_fors jsonb,           -- [{ "mistake": "...", "fix": "..." }]
  ref_image_path text,        -- Storage path
  clip_path text,             -- Storage path
  timer_s int null            -- optional countdown (e.g. rice resting)
)

sessions (
  id uuid pk,
  recipe_id uuid fk,
  started_at timestamptz,
  finished_at timestamptz
)

session_events (
  id uuid pk,
  session_id uuid fk,
  step_id uuid fk,
  kind text,                  -- 'check_pass' | 'check_fix' | 'watch_warn' | 'question'
  payload jsonb,
  created_at timestamptz
)
```

`session_events` feeds the "Done" summary screen. It is also the foundation for future personalization, which is out of scope for now.

---

## Backend API (contract between iOS and backend)

Agree on this first so both tracks can build in parallel.

### `POST /recipes`
```json
// request
{ "title": "Maki sushi", "chef_name": "...", "step_marks_s": [12.4, 58.0, 101.7] }
// response
{ "recipe_id": "...", "status": "uploading", "upload_url": "<signed Supabase Storage URL>" }
```
The client then uploads the MP4 directly to `upload_url`.

### `POST /recipes/{id}/process`
Called after the upload finishes. Starts the background ingestion job. Returns `{ status: "processing" }`.

### `GET /recipes?status=published` · `GET /recipes/{id}`
Returns the recipe library, or one recipe with its ordered steps and **signed URLs** for `ref_image` and `clip`. The review page polls `GET /recipes/{id}` for `status`.

### `POST /recipes/{id}/publish`
Called from the review page. Status changes from `review` to `published`.

### `PATCH /steps/{id}`
Chef edits from the web page: text fields, or a new `timestamp_s`, which triggers ffmpeg to re-extract the frame.

### `POST /check`
```json
// request (multipart): frame=<jpeg full-res>, step_id
// response
{
  "verdict": "pass" | "fix",
  "headline": "Too much rice",          // ≤ 4 words
  "fix": "Spread thinner, 2cm nori free", // ≤ 8 words
  "spoken": "There's a bit too much rice — spread it thinner and leave two centimetres of nori at the top.",
  "confidence": 0.0
}
```

### `POST /watch`
```json
// request (multipart): frame=<jpeg low-res>, step_id
// response
{
  "status": "ok" | "warn",
  "mistake_id": "rice_too_thick",
  "headline": "Too much rice",
  "fix": "Spread thinner, 2cm nori free",
  "spoken": "...",
  "confidence": 0.0
}
```
The client applies debouncing: it alerts only when `warn` with `confidence ≥ threshold` occurs on 2 consecutive calls with the same `mistake_id`.

### `GET /live-token`
Returns a short-lived Gemini Live ephemeral token plus a session config (model, system prompt containing the recipe and transcript).

### `POST /sessions` · `POST /sessions/{id}/events`
Logs checks, warnings, and questions for the Done screen.

All Gemini calls use **structured output (JSON schema)**, so responses are always parseable.

---

## Display spec (in-lens)

**Constraints:** monocular (right lens), small field of view, see-through. Black is transparent, so use bright elements on black. Never use dark backgrounds.

**Principle:** the display shows *what* and *where*, and voice carries *why* and the detail. At most 2 short lines of text, readable in under 1 second at a glance. Don't cover the user's view of the cutting board for long.

### Screens

**1. Recipe pick:** a list. Neural Band swipe scrolls, pinch selects.

**2. Step card** (default)
```
 3/8  Spread rice
 ─────────────────
 [chef ref image]
 Thin layer, leave 2cm top
 ● watching
```
Shows step number, title (≤ 4 words), the chef's POV reference still, and a key line (≤ 8 words). A green dot means the watcher is active.

**3. Checking:** reference image with a "Checking…" spinner (target 1–2 s).

**4. Pass:** big green ✓ "Looks right" with a chime. Auto-advances after 2 s, or pinch to advance now.

**5. Fix / proactive warning**
```
 ⚠ Too much rice
 ─────────────────
 [chef ref image]
 Spread thinner, 2cm nori free
```
Amber. One sentence is spoken at the same time. It interrupts the step card and clears when a re-check passes or the user dismisses it.

**6. Talking:** a mic icon while listening. During the answer, a 3–5 word caption is shown and the full answer is audio only.

**7. "Show me":** the chef's 3–5 s POV clip loops in place of the still image.

**8. Timer** (only for steps with `timer_s`): a single countdown widget.

**9. Done:** "Sushi done ✓" plus a summary: steps passed on the first try and fixes caught.

### Inputs

| Input | Action |
|---|---|
| Pinch | Check / next |
| Swipe | Previous / next step |
| Double-pinch or "show me" | Play chef clip |
| Voice | Questions, "check", "next", "show me" |

### Not doing

- Full instruction paragraphs in the lens (spoken on request instead)
- AR overlays on the food: the display is not spatially anchored, so overlays would misalign

---

## Scope

### Must (demo script)
- Ingestion pipeline: video → steps + reference frames (+ clips)
- One seeded, pre-ingested sushi recipe (the demo never depends on live ingestion)
- iOS step-card flow on the glasses display, with gesture navigation
- `/check` with pass/fix
- `/watch` proactive warning with debouncing; the scripted "too much rice" mistake must be in `watch_fors`
- Gemini Live voice Q&A grounded in the recipe
- iOS Chef mode: record through DAT with pinch step marks, then upload
- Review web page: review, edit, publish (plus MP4 upload as a dev fallback)

### Nice to have
- "Show me" clips
- Timer widget
- Done summary screen

### Cut (pitch as "what's next")
- Personalization: "learns where you tend to slip"
- Multi-user accounts / auth beyond a demo key
- Other domains (first aid, repairs, onboarding)

---

## Development before the glasses arrive

Glasses will be picked up at the Meta booth.

1. Build against the **iPhone camera** as the frame source. The display UI is mirrored in an in-app "lens preview" view that uses the same state machine.
2. Check whether DAT offers a **mock device** for development without hardware.
3. When the glasses arrive, swap the frame source to the DAT stream and route the UI state to the DAT display components.

---

## Confirmed with Meta

- ✅ DAT can run the **camera stream and the display UI at the same time**.
- ✅ Gemini Live audio can use the **glasses' Bluetooth mic/speakers** while DAT streams video.

## Open risks / verify early

1. Camera stream **frame rate and resolution** under DAT. This sets the resolution for `/check` and `/watch` frames.
2. **DAT display layout:** can an image and text be combined in one view, or is it a fixed component stack? The mockups assume image + text together. Ask the Meta booth.
3. Current **Gemini model IDs** for video understanding, fast vision checks, and Live native audio. Also the **ephemeral token** flow from a Swift client.
4. Watcher **latency and cost**: a frame every 2–3 s over a ~10 min session is about 200–300 calls. Use the fastest Flash-tier model at low resolution.
5. Stage conditions: lighting and noise. Tune the confidence threshold with real sushi footage on Saturday.

---

## Security notes

- The Gemini API key and the Supabase service key stay on the backend only. The phone gets ephemeral Live tokens and signed Storage URLs.
- Uploads: limit size and type (MP4 only), and scope storage paths per recipe.
- Supabase RLS on all tables, even for the demo. The backend uses the service role, and the iOS app never touches Supabase directly.
- A simple shared demo API key on backend endpoints, so the public Railway URL isn't open to anyone.

---

## Next steps

1. Agree the API contract above with the iOS teammate (30 min).
2. Run the planner to produce a phased plan with a backend track (Stelios) and an iOS track (teammate).
3. Record raw sushi footage early, even from a phone, so the ingestion pipeline has real input.
