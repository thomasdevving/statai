# WEB-02 — Chef studio: upload, review, edit, publish

| | |
|---|---|
| **Track** | `web/` |
| **Gate** | G3 |
| **Depends on** | WEB-01 (shared modules). BE-01 is enough to build against (its fake ingestion moves a recipe `processing → review`); BE-06 for real video and frame re-picking. |
| **Unblocks** | The "chef records once" half of the story; a Must in the spec |
| **Size** | Medium |
| **Model** | Opus 5.5; Sonnet 5.5 is enough for form styling and copy |
| **Needs a human for** | Uploading the real chef video and reviewing the result |

## Goal

One page where a chef (or the team, standing in for one) uploads a recording with explicit consent, watches it turn into steps, corrects the text, re-picks a reference frame from the video, publishes, and can delete everything again.

## Read first

- [../../docs/API-CONTRACT.md §2](../../docs/API-CONTRACT.md#2-recipes-and-steps) — every endpoint used here, the word limits, the status values
- [../../docs/TECH-SPEC.md](../../docs/TECH-SPEC.md) "Chef recording → recipe"
- [../../docs/PRODUCT.md §8](../../docs/PRODUCT.md#8-trust-consent-accessibility) — consent and deletion

## Tasks

### WEB-02.1 Recipe list and upload

**Do** — `studio/index.html`, `studio/studio.js`; add to `shared/api.js`: `uploadRecipe(formData)`, `patchRecipe`, `publishRecipe`, `deleteRecipe`, `patchStep`.
- List all recipes with a status chip (`processing`, `review`, `published`, `failed`), step count, created time. `failed` shows the `error` text.
- Upload form: MP4 file, title (required, ≤ 80 characters), chef name (optional), and a **consent checkbox that must be ticked**: "The person in this recording agreed to it being processed by Google Gemini and shown in the Ghost Chef demo." The submit button stays disabled without it. Send `consent=true`.
- Client-side checks before sending: file type is MP4, size ≤ 500 MB (show the size).
- Upload progress (use `XMLHttpRequest` for progress events, or show an indeterminate state with `fetch`).
- After `202`, poll `GET /recipes/{id}` every 3 s until the status leaves `processing`; show elapsed time. Polling stops when the tab is hidden and resumes when visible.

**Acceptance:** against the fake backend, an upload of any small MP4 appears as `processing` and becomes `review` without a page reload; a missing consent tick cannot be submitted; a non-MP4 is rejected before upload.

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

Upload the real chef take. Review every step against the video: is the still the finished state, are the criteria visible things, is the scripted mistake present? Fix what is wrong using the studio itself and note what you had to change.

**Acceptance:** `STATUS.md` records: processing time, number of steps, number of fields edited by hand, number of frames re-picked. These numbers are honest material for the pitch ("the chef spent N minutes reviewing").

## Verification

```bash
python -m http.server 5173 --directory web      # then open http://localhost:5173/studio/
```

Manual walk-through of each acceptance against the fake backend, then against the real one.

## Out of scope

Recording video in the browser. Authentication beyond the demo key. Editing step order or adding steps (not in the contract).

## When done

Update `STATUS.md`, commit `[web] WEB-02 chef studio`, push.
