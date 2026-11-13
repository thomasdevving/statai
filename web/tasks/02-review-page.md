# WEB-02 — Review page: review, edit, publish (+ dev-fallback MP4 upload)

| | |
|---|---|
| **Track** | `web/` |
| **Gate** | G3 |
| **Depends on** | WEB-01 (shared modules). BE-01 is enough to build against (its fake ingestion moves a recipe `uploading → processing → review`); BE-06 for real video and frame re-picking. |
| **Unblocks** | The "chef records once" half of the story: the chef records in the iOS app's Chef mode (IOS-08) and reviews here. A Must in the spec |
| **Size** | Medium |
| **Model** | Opus 5.5; Sonnet 5.5 is enough for form styling and copy |
| **Needs a human for** | Reviewing a real ingested recipe (recorded in Chef mode, or uploaded here as the dev fallback) |

## Goal

One page where a chef (or a teammate, on a laptop) opens a recipe the iOS app recorded and uploaded, watches it turn into steps, corrects the text, re-picks a reference frame from the video, publishes, and can delete everything again. **Recording happens on the glasses (IOS-08), not here.** The page also keeps a small MP4 upload as a **dev fallback**, so the pipeline can be built and tested before the glasses arrive.

## Read first

- [../../docs/API-CONTRACT.md §2](../../docs/API-CONTRACT.md#2-recipes-and-steps) — every endpoint used here, the word limits, the status values
- [../../docs/TECH-SPEC.md](../../docs/TECH-SPEC.md) "Chef recording → recipe" (Record / Upload / Process / Review)
- [../../docs/PRODUCT.md §8](../../docs/PRODUCT.md#8-trust-consent-accessibility) — consent and deletion

## Tasks

### WEB-02.1 Recipe list, status polling, dev-fallback upload

**Do** — `review/index.html`, `review/review.js`; add to `shared/api.js`: `createRecipe({title, chef_name, step_marks_s, consent})`, `putVideo(uploadUrl, file, onProgress)`, `processRecipe(id)`, `patchRecipe`, `publishRecipe`, `deleteRecipe`, `patchStep`.
- List all recipes with a status chip (`uploading`, `processing`, `review`, `published`, `failed`), step count, created time. `failed` shows the `error` text. Recipes uploaded from the iOS app appear here on their own.
- Opening a recipe that is `uploading` or `processing` polls `GET /recipes/{id}` every 3 s until the status changes; show elapsed time. Polling stops when the tab is hidden and resumes when visible.
- **Dev-fallback upload**, in a collapsed section labelled "Dev fallback: upload an MP4 (the real path is Chef mode on the glasses)": MP4 file, title (required, ≤ 80 characters), chef name (optional), and a **consent checkbox that must be ticked**: "The person in this recording agreed to it being processed by Google Gemini and shown in the Ghost Chef demo." The submit button stays disabled without it.
- The upload follows contract v2.0: `POST /recipes` with `consent: true` and `step_marks_s: []` → `PUT upload_url` with the raw file and `Content-Type: video/mp4`, **without** `X-Demo-Key` (use `XMLHttpRequest` for progress) → `POST /recipes/{id}/process` → poll as above. If the `PUT` fails, show the error and offer "Retry upload" (same `upload_url` while it is valid), then `/process`.
- Client-side checks before sending: file type is MP4, size ≤ 500 MB (show the size).

**Acceptance:** against the fake backend, a dev-fallback upload of any small MP4 goes `uploading → processing → review` without a page reload; a missing consent tick cannot be submitted; a non-MP4 is rejected before upload; a recipe created by another client (e.g. `curl` following API-CONTRACT §2) shows up in the list.

### WEB-02.2 Review screen

**Do** — opening a recipe in `review` or `published` shows:
- Recipe title and chef name, editable (`PATCH /recipes/{id}`).
- The steps in order. Each step is a card: reference image (large enough to judge), a live **lens preview** of the step card rendered with `shared/lens.js` (so the chef sees what the wearer sees), and editable fields: `title`, `key_line`, `instruction`, `success_criteria` (one per line), `timer_s`.
- Live word counters next to `title` (max 4) and `key_line` (max 8) that turn red over the limit and block saving that card.
- `watch_fors` editor per step: rows of `id` (read-only once created; generated from the mistake text as snake_case for new rows), `mistake`, `headline` (max 4 words), `fix` (max 8 words), `spoken`; add and remove rows.
- Save per card (`PATCH /steps/{id}`) with a clear saved / failed state; server `422` messages are shown next to the card.
- The transcript, read-only, collapsible.

**Acceptance:** editing a title and saving survives a reload; a 5-word title cannot be saved and the server is not called; adding a watch-for and saving shows it after reload.

### WEB-02.3 Re-pick the reference frame

**Do**
- When `video_url` is present (status `review`), show the source video in a `<video>` element above the steps.
- Each step card has "Jump to this step" (seeks the video to `timestamp_s`) and "Use current frame as reference" (sends `PATCH /steps/{id}` with `timestamp_s = video.currentTime`), then reloads that step's image with a cache-busting query.
- Frame-step buttons (±0.1 s, ±1 s) for precise picking.
- Without `video_url` (published recipe, or the backend before BE-06), the control falls back to a numeric timestamp field and says why.

This is item 6 in the cut order: if time is short, ship the numeric field only.

**Acceptance (needs BE-06):** picking a different moment changes the reference image the lens preview shows.

### WEB-02.4 Publish and delete

**Do**
- "Publish" button, enabled in `review`. Show the server's `409` reason if a step lacks a reference image. After publishing, the recipe appears in the simulator's picker.
- "Delete recipe and all footage" with a typed confirmation of the recipe title. Explain what is removed (video, stills, clips, sessions, frames). Surface the server's refusal for the protected demo recipe.

**Acceptance:** a published recipe can be picked in the simulator; delete removes it from the list.

### WEB-02.5 Real video *(human, needs BE-06 and AI-06)*

Open the real chef take (recorded in Chef mode, or uploaded through the dev fallback; say which). Review every step against the video: is the still the finished state, are the criteria visible things, is the scripted mistake present, did the chef's pinch marks land on sensible step boundaries? Fix what is wrong using the review page itself and note what you had to change.

**Acceptance:** `STATUS.md` records: processing time, number of steps, number of fields edited by hand, number of frames re-picked. These numbers are honest material for the pitch ("the chef spent N minutes reviewing").

## Verification

```bash
python -m http.server 5173 --directory web      # then open http://localhost:5173/review/
```

Manual walk-through of each acceptance against the fake backend, then against the real one.

## Out of scope

Recording video in the browser (Chef mode in the iOS app does that). Resumable upload in the browser (a simple `PUT` is enough for the dev fallback). Authentication beyond the demo key. Editing step order or adding steps (not in the contract).

## When done

Update `STATUS.md`, commit `[web] WEB-02 review page`, push.
