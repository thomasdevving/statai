# BE-06 — Ingestion pipeline: signed upload → process → Gemini → ffmpeg → review → publish

| | |
|---|---|
| **Track** | `backend/` |
| **Gate** | G3 |
| **Depends on** | BE-02 (storage); AI-06 on `main` for real extraction (everything else here can be built and tested with the fake) |
| **Unblocks** | IOS-08 (Chef mode) and WEB-02 (review page) end to end |
| **Size** | Medium–large |
| **Model** | Opus 5.5 |
| **Needs a human for** | Uploading the real chef video once and looking at the result |

## Goal

A chef's MP4 lands in Storage (uploaded by the iOS app in Chef mode, or by the review page's dev fallback, through the signed URL from `POST /recipes`); `POST /recipes/{id}/process` turns it into a reviewable recipe, with a real reference still and (optionally) a short clip for every step, cut by ffmpeg at the timestamps Gemini returned. The chef can correct text and re-pick frames, then publish. Failures are visible and never affect the seeded demo recipe.

## Read first

- [../../docs/API-CONTRACT.md §2](../../docs/API-CONTRACT.md#2-recipes-and-steps) — `POST /recipes`, `POST /recipes/{id}/process`, `PATCH /steps/{id}`, publish, delete
- [../../docs/ARCHITECTURE.md §3.1](../../docs/ARCHITECTURE.md#31-ingestion-chef--recipe)
- `backend/app/routers/recipes.py` — the BE-01 version you are upgrading

## Tasks

### BE-06.1 ffmpeg helpers

**Do** — `app/media/ffmpeg.py`, each running the binary with `asyncio.create_subprocess_exec` (never a shell string), a timeout, and stderr captured into the raised error:
- `probe(path) -> {duration_s, width, height, rotation}` via `ffprobe -print_format json`.
- `extract_still(path, at_s, out_path, long_edge=1280)`: seek **before** the input (`-ss <t> -i <file>`), one frame, scaled so the long edge is `long_edge` (keep aspect ratio; honour rotation metadata), JPEG quality ~`-q:v 3`.
- `extract_clip(path, start_s, end_s, out_path, long_edge=720)`: H.264, no audio, `-movflags +faststart`, `yuv420p`, duration capped at 6 s.
- `ffmpeg_available() -> bool`; `/health` gains an additive field `"ffmpeg": true|false`.

**Acceptance:** tests generate a 5-second test video with ffmpeg's `testsrc` and assert a still and a clip come out with the right dimensions. Tests are skipped with a clear reason when ffmpeg is not installed.

### BE-06.2 Upload completion and validation

The bytes never pass through FastAPI (contract v2.0), so validation moves to `/process` and the job.

**Do**
- `POST /recipes` and `POST /recipes/{id}/process` stay as built in BE-01, now on the Supabase store (signed upload URL from BE-02.3).
- First thing in the job: download `videos/<recipe_id>/source.mp4` to a temp file **in chunks**; stop and fail with `"video larger than <MAX_VIDEO_MB> MB"` once the limit is passed; then `probe` it — if `ffprobe` fails, fail with `"not a readable MP4"`. Nothing reaches Gemini before both pass.
- Recipes still `uploading` after 2 hours become `failed` with `"upload never completed"` (check on startup and whenever `GET /recipes` runs; no scheduler needed).

**Acceptance:** tests for the size limit (with a small `MAX_VIDEO_MB`), a non-video file uploaded to the signed URL, `/process` before the upload (`409 upload_missing`), the 2-hour timeout (inject the clock), and the happy path.

### BE-06.3 The job

**Do** — `app/jobs/ingest.py::run_ingestion(recipe_id)`:
1. Download the video from Storage to a temp dir (size check, BE-06.2).
2. `probe` → duration. Drop any `step_marks_s` beyond the duration.
3. `draft = await ghostchef_ai.extract_recipe(path, title_hint=recipe.title, step_marks_s=recipe.step_marks_s)`.
4. Clamp every `timestamp_s` into `[0, duration − 0.1]`; clamp clips into the duration; drop clips shorter than 1 s.
5. For each step: `extract_still` → upload to `media/<recipe_id>/steps/<idx>/ref.jpg`. If the step has a clip window: `extract_clip` → upload `clip.mp4`. A failed clip is logged and skipped; a failed still marks the step as having no reference image.
6. `replace_steps`, store the transcript, set status `review`.
7. Any exception → status `failed`, `error` = a short human-readable reason (no stack trace, no keys). Always clean the temp dir.

Operational rules:
- At most **one ingestion at a time** (an `asyncio.Semaphore(1)`); others wait as `processing`.
- The job runs as an `asyncio` task tracked in a set (so it is not garbage-collected) and never blocks request handling.
- On startup, any recipe still `processing` and older than 15 minutes is set to `failed` with error `"interrupted by a restart; upload again"`.

**Acceptance**
- Fake-mode test with the `testsrc` video: recipe reaches `review` with a real extracted still per step.
- A monkeypatched failing `extract_recipe` yields `failed` with a readable `error`.

### BE-06.4 Review-time endpoints

**Do**
- `GET /recipes/{id}` returns `video_url` (signed) while status is `review`.
- `PATCH /steps/{id}` with a new `timestamp_s`: validate against the duration, download the source video (cache the local copy for 10 minutes: the chef re-picks several frames in a row), re-extract the still, upload over the old path, invalidate the reference cache (BE-03.3) and the signed-URL cache, respond with the updated `Step`. Editing a step of a `published` recipe is allowed (the chef fixes a typo) and takes effect immediately.
- `POST /recipes/{id}/publish`: `409` if any step lacks a reference image.
- `DELETE /recipes/{id}`: refuse to delete the seeded demo recipe unless `?force=true` (protects the demo from a stray click).

**Acceptance:** tests for re-extraction (image bytes change), publish rules, and the delete guard.

### BE-06.5 Real run *(human looks at the result)*

- With real AI and Supabase, upload the real chef video from the iOS app (Chef mode), the review page, or `curl`:

  ```bash
  curl -s -H "X-Demo-Key: <key>" -H "Content-Type: application/json" \
       -d '{"title":"Maki roll (ingested)","step_marks_s":[],"consent":true}' <base>/recipes      # note recipe_id, upload_url
  curl -X PUT -H "Content-Type: video/mp4" --data-binary @chef-take-1.mp4 "<upload_url>"
  curl -X POST -H "X-Demo-Key: <key>" <base>/recipes/<recipe_id>/process
  ```
- Poll `GET /recipes/{id}` until `review`. Open each `ref_image_url`.

**Acceptance:** `STATUS.md` records: video length and size, total processing time, number of steps, how many stills landed on a usable frame. The seeded demo recipe is untouched.

## Verification

```bash
cd backend
ruff check .
pytest -q
ffmpeg -version | head -1
python scripts/smoke.py --base http://localhost:8000 --key dev-key --fast
```

## Out of scope

Recording through the glasses inside the app (IOS-08, owned by `ios/`). The review UI (WEB-02). Prompt quality (`ai/`).

## When done

Update `STATUS.md`, commit `[backend] BE-06 ingestion pipeline`, push, deploy, tell the web owner.
