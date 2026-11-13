# AI-06 — `extract_recipe`: chef video → structured steps

| | |
|---|---|
| **Track** | `ai/` |
| **Gate** | G3. Not on the demo's critical path (the demo uses the seeded recipe), but a Must in the spec and the strongest Gemini talking point. |
| **Depends on** | AI-02 (video model verified), the real chef video from AI-03 |
| **Unblocks** | BE-06 (ingestion pipeline) |
| **Size** | Medium |
| **Model** | Opus 5.5 |
| **Needs a human for** | Reviewing the extracted steps and timestamps against the video |

## Goal

One function that takes the chef's MP4 and returns a `RecipeDraft`: ordered steps with display text, visible success criteria, common mistakes with stable ids, timestamps for reference stills and clips, and the full transcript.

## Read first

- [../../docs/API-CONTRACT.md](../../docs/API-CONTRACT.md) §2 (Step object, word limits), §7 (`extract_recipe`, `RecipeDraft`, the "no I/O beyond Gemini" rule)
- [../../docs/TECH-SPEC.md](../../docs/TECH-SPEC.md) "Chef recording → recipe" and "Display spec"
- Current video-understanding and Files API documentation at `https://aistudio.google.com/docs/` — upload flow, size and duration limits, frame sampling options, timestamp format
- `ai/fixtures/sushi_recipe.json` — the hand-corrected version from AI-03.5 is your ground truth for comparison

## Tasks

### AI-06.1 Prompt

**Do** — `src/ghostchef_ai/prompts/extract.md`. The model watches a first-person cooking video with narration and must return JSON matching the schema. Rules to state:

- **Steps:** between 4 and 10. A step is one action with a visible finished state. Merge trivial actions; split a step if it has two separately checkable results.
- **`title`** ≤ 4 words, imperative. **`key_line`** ≤ 8 words: the one thing to get right, readable in a second.
- **`instruction`:** one to three sentences, in the chef's wording where possible.
- **`chef_quote`:** a verbatim sentence from the narration for this step, or null.
- **`success_criteria`:** 1–3 items, each something **visible in a single top-down photo of the work surface** (coverage, margins, position, shape, count). Nothing about taste, temperature, pressure, or timing.
- **`watch_fors`:** 0–3 per step, only mistakes that are (a) common for beginners, (b) visible in a photo, (c) different from an unfinished step. Each has `id` in `snake_case`, `mistake` (what it looks like), `headline` ≤ 4 words, `fix` ≤ 8 words (an action), `spoken` (one friendly sentence). Prefer mistakes the chef mentions.
- **`timestamp_s`:** the moment the **finished state of the step is clearly visible with hands mostly out of the way**. Not the start of the step.
- **`clip_start_s` / `clip_end_s`:** a 3–5 second window showing the key hand movement of the step.
- **`timer_s`:** only if the chef states a waiting time.
- **`transcript`:** the complete narration, verbatim, in order.
- **`title`** of the recipe: from the narration, else from the hint.

**Acceptance:** the prompt file is recipe-agnostic (no mention of sushi).

### AI-06.2 Implementation

**Do** — `src/ghostchef_ai/ingest.py::extract_recipe(video_path, *, title_hint=None)`:
1. Upload the file through the Files API; poll until it is ready to use; raise `AIUnavailable` with a clear message if processing fails or exceeds 5 minutes.
2. One generate call with the video model, the prompt, structured output using a schema equivalent to `RecipeDraft`. Use a longer timeout here (default 180 s; this runs in a background job).
3. **Repair before validating**, because one slightly long title should not fail a 3-minute job:
   - `clamp_words` on `title` (4), `key_line` (8), each `headline` (4), each `fix` (8);
   - slugify `watch_fors[].id` to `snake_case`; de-duplicate within a step by suffixing `_2`;
   - sort steps by `timestamp_s`, renumber `idx` from 1;
   - negative timestamps → 0; `clip_end_s` ≤ `clip_start_s` → set both to null;
   - drop `watch_fors` entries missing any string.
4. Validate with `RecipeDraft`. On failure retry the generate call once, then raise `AIInvalidOutput`.
5. Delete the uploaded file from the Files API in a `finally` block.
6. Timestamps may exceed the real video length; the backend clamps them (it has ffprobe). Do not add ffmpeg here.

**Acceptance**
- Unit tests with a stubbed client cover every repair rule and the retry.
- Fake mode unchanged and still passing.

### AI-06.3 Run on the real chef video *(human reviews)*

```bash
python -m ghostchef_ai extract footage/chef-take-1.mp4 -o /tmp/extracted.json
```

Review `/tmp/extracted.json` against the video and against the hand-corrected fixture:

| Check | How |
|---|---|
| Step count and order sensible | Read them |
| Each `timestamp_s` lands on the finished state | Open the video at that second. Record the error in seconds per step |
| Criteria are visible-in-a-photo | Read them; strike any that are not |
| The scripted mistake is present for "Spread rice" | Look for a too-much-rice watch-for |
| Transcript complete | Skim against the audio |
| Wall-clock time and video length | Note both |

Iterate on the prompt two or three times at most.

**Acceptance:** `STATUS.md` records: video length, extraction time, model ID, number of steps, per-step timestamp error, and a one-line judgment of how much hand-editing the result needed.

### AI-06.4 Decide the seeded recipe

The demo recipe must be reviewed by a person. Choose one and record the choice:

- **(a)** keep the hand-corrected fixture from AI-03.5 as the seed; or
- **(b)** replace `fixtures/sushi_recipe.json` with the extracted version **after** hand-fixing it, keeping the `rice_too_thick` id and strings the demo relies on, and regenerating `fixtures/images/` from the new timestamps with `scripts/extract_frames.py --at`.

Either way the fixture must validate and `pytest` must pass. Tell the backend owner if the fixture changed so they re-seed.

**Acceptance:** one line in `STATUS.md` stating (a) or (b) and why.

### AI-06.5 Wire the public surface

`__init__.py` dispatches the real path to `ingest.extract_recipe`.

## Verification

```bash
cd ai
ruff check .
GHOSTCHEF_AI_FAKE=1 GHOSTCHEF_AI_FAKE_DELAY=0 pytest -q
python -m ghostchef_ai extract footage/chef-take-1.mp4 -o /tmp/extracted.json
python -c "import json,pathlib; from ghostchef_ai.schemas import RecipeDraft; RecipeDraft.model_validate(json.loads(pathlib.Path('/tmp/extracted.json').read_text(encoding='utf-8'))); print('valid')"
```

## Out of scope

ffmpeg extraction of stills and clips, storage, job handling, the HTTP endpoint (all BE-06). The review UI (WEB-02).

## When done

Update `STATUS.md`, commit `[ai] AI-06 extract_recipe`, push, tell the backend owner BE-06 can use the real function.
