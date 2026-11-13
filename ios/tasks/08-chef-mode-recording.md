# IOS-08 — Chef mode: record through the glasses, mark steps, upload

| | |
|---|---|
| **Track** | `ios/` (Mac) |
| **Gate** | G3 (a Must since the 2026-11-14 TECH-SPEC update) |
| **Depends on** | IOS-01 (API client, settings), IOS-02 (camera stream, inputs and audio-route facts; proof h). BE-01 is enough to build the upload flow against (memory-mode upload route + fake ingestion); BE-02 for the real Supabase signed URL; BE-06 for real ingestion. Glasses for IOS-08.5. |
| **Unblocks** | The "chef records once" half of the demo on the glasses; WEB-02.5 (reviewing a real Chef-mode take) |
| **Size** | Large |
| **Model** | Opus 5.5, with Meta's `mwdat-ios` plugin and docs MCP for the DAT parts; Sonnet 5.5 is enough for the mode picker and the upload status screen |
| **Needs a human for** | Recording one real take wearing the glasses |

## Goal

The app has two modes, picked on the first screen: **Cook** (everything from IOS-03 to IOS-07) and **Chef**. In Chef mode the chef cooks wearing the glasses and talks through each step; the app records the DAT camera stream and the mic to an MP4 on the phone (no clip-length limit, unlike the glasses' built-in capture), shows "● REC 03:12" in the lens, and saves a **step mark** on every pinch. On stop it creates the recipe, uploads the MP4 **directly to Supabase Storage** (resumable, because of venue Wi-Fi), starts processing, and tells the chef to finish on the review web page.

## Read first

- [../../docs/TECH-SPEC.md](../../docs/TECH-SPEC.md) "1. Chef recording → recipe" (Record / Upload)
- [../../docs/API-CONTRACT.md §2](../../docs/API-CONTRACT.md#2-recipes-and-steps) — `POST /recipes` (v2.0: JSON, signed upload URL, `step_marks_s`, `consent`), `POST /recipes/{id}/process`, the `uploading` status, `409 upload_missing`
- `ios/STATUS.md` → "Device facts" (proofs b, e′, f, h) and "Decisions taken from the spike": which input is the "pinch", and which mic is used while the camera streams
- Supabase resumable uploads, "Presigned uploads": `https://supabase.com/docs/guides/storage/uploads/resumable-uploads`
- Current Apple documentation for `AVAssetWriter` (video + audio inputs, `expectsMediaDataInRealTime`) before writing the recorder

## Tasks

### IOS-08.1 Mode picker

**Do** — `GhostChef/UI/ModePickerView.swift` as the root: two large buttons, **Cook** (→ `RecipeListView`) and **Chef** (→ `ChefRecordView`). Remember the last choice in `Settings`. Settings stays reachable from both.

**Acceptance:** both modes open; the Cook path is unchanged.

### IOS-08.2 API client additions

**Do** — extend `GhostChefAPI` / `APIClient` / `MockAPI` with `createRecipe(title:chefName:stepMarksS:consent:) -> RecipeUpload` (decodes every field of the `201` body, `resumable_endpoint` optional) and `processRecipe(id:)`. Decode the new status `uploading` and the `step_marks_s` field; unknown statuses must not crash.

**Acceptance:** unit tests decode the literal `201` example from API-CONTRACT §2 with and without `resumable_endpoint`, and a `409 upload_missing` envelope.

### IOS-08.3 Recorder and step marks

**Do** — `GhostChef/Chef/ChefRecorder.swift` (`@MainActor @Observable`, dependencies injected as protocols so the logic is testable without a device):
- Before the first recording, a **consent screen**: "Everyone in this recording agrees to it being processed by Google Gemini and shown in the Ghost Chef demo." Recording cannot start without it; the answer is sent as `consent: true`.
- Recording source: the DAT camera stream when glasses are connected (reuse `DATFrameSource`'s stream if IOS-06 exists, else the IOS-02 Lab code), the phone camera otherwise. **The screen and the saved metadata say which source was used**; a phone-camera take is a development fallback, never presented as recorded on the glasses.
- Write video frames and microphone audio to `Documents/takes/<uuid>.mp4` with `AVAssetWriter` (H.264, AAC, `expectsMediaDataInRealTime = true`), using sample timestamps so audio and video stay in sync. Use the audio route IOS-02 proof f found (glasses mic if it works alongside the stream).
- **Step marks:** each "pinch" (the input chosen in the spike decision; a phone button and a display button as fallbacks) appends `elapsed seconds since recording start` to `stepMarksS`, plays a short click, and briefly shows "Step 3 marked" in the lens. Marks are strictly ascending; two marks within 1 s collapse into one.
- Lens while recording: "● REC 03:12" and "Step N" only, bright on black, updated at most once per second. Phone screen: the camera preview, the timer, the mark count, and a large **Stop** button.
- Stop → finalize the file → ask for title (required, ≤ 80 characters) and chef name (optional). The MP4 stays on the phone until processing has started successfully.

**Acceptance:** unit tests for mark collection (ascending, de-bounce of 1 s, marks relative to recording start, reset between takes). On the iPhone with the phone camera: a 60 s take plays back in Photos-quality with sound in sync, and its marks are listed.

### IOS-08.4 Upload and process

**Do** — `GhostChef/Chef/ChefUploader.swift`:
1. `createRecipe(...)` → `RecipeUpload`.
2. If `resumable_endpoint` is non-null: TUS upload against it with header `x-signature: <upload_token>`, metadata `bucketName`, `objectName` (= `object_path`), `contentType = video/mp4`, chunk size **exactly 6 MB**, retries with backoff (0, 3, 5, 10, 20 s). Use a small, maintained Swift TUS client if one fits (check it before adding; pin the exact version) or the TUS protocol by hand (`POST` create, `PATCH` chunks, `HEAD` to resume). If TUS fails twice, or `resumable_endpoint` is null (backend in memory mode), fall back to a single `PUT upload_url` with the file as the body and `Content-Type: video/mp4`, **without** `X-Demo-Key`.
3. Show progress (bytes and percent), "Retrying…" on errors, and keep going if the screen locks (background `URLSession` for the simple `PUT`; for TUS, resume from the last confirmed offset when the app returns).
4. `processRecipe(id)`. On `409 upload_missing`, retry the upload once. On success, show "Processing — finish on the review page" with the review page URL (`<API base>/app/review/`) and the recipe title, and delete the local MP4 only now.

**Acceptance:** against BE-01 in memory mode: a take goes `uploading → processing → review` and appears on the review page. Against the Supabase backend: a > 50 MB take uploads over a phone hotspot through TUS; killing Wi-Fi mid-upload and restoring it resumes rather than restarting (record what actually happened in `STATUS.md`).

### IOS-08.5 Real take on the glasses *(human wears them)*

Record the real sushi chef take in Chef mode, following the chef-take rules in [AI-03.1](../../ai/tasks/03-footage-and-eval-set.md#ai-031-the-chef-take-human): narrate each step with the reason, say what good looks like and what the common mistake is, hold still two seconds on each finished state — and **pinch at the start of each new step**. Hands and board only; no faces, no bystanders. Agree the timing with the AI owner: this take can replace AI-03's earlier footage as the source of the demo recipe.

**Acceptance:** `STATUS.md` → "Chef mode takes" has the row: date, glasses model and firmware, source (glasses / phone), duration, file size, frame rate and resolution as written, number of marks, upload path (TUS / PUT) and time, and whether it reached `review`. Tell the web owner it is ready for WEB-02.5.

## Verification

```bash
cd ios && xcodegen generate
xcodebuild -project GhostChef.xcodeproj -scheme GhostChef -destination 'generic/platform=iOS Simulator' test
xcodebuild -project GhostChef.xcodeproj -scheme GhostChef -destination 'generic/platform=iOS' build
```

Recording, upload, and the lens are verified on the device and written in `STATUS.md`.

## Out of scope

Editing the steps on the phone (that is the review page, WEB-02). Trimming or re-recording parts of a take. Accounts and sharing links or QR codes (pitched as "what's next"). Any change to `CookSession`'s rules.

## When done

Update `STATUS.md`, commit `[ios] IOS-08 chef mode recording`, push. Status is `DONE` only with a real take recorded on the glasses that reached `review`; `DONE (fake)` or `PARTIAL` otherwise, saying exactly what is missing.
