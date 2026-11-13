# AI-04 — `check_frame` and `watch_frame` for real

| | |
|---|---|
| **Track** | `ai/` |
| **Gate** | G1 — the first real loop needs `check_frame` |
| **Depends on** | AI-02 (models chosen). A handful of real frames from AI-03 makes this much better; start on placeholder or phone photos if footage is late. |
| **Unblocks** | BE-03 |
| **Size** | Medium |
| **Model** | Opus 5.5 |
| **Needs a human for** | Looking at outputs on dev frames and judging whether the wording is usable |

## Goal

The two core judgments, implemented against Gemini with structured output, fast enough for the product, and honest when the frame does not show enough.

- `check_frame`: learner frame + chef reference + step criteria → `pass` / `fix` / `unsure`.
- `watch_frame`: one low-res frame + the step's known mistakes → `ok` / `warn`.

## Read first

- [../../docs/API-CONTRACT.md](../../docs/API-CONTRACT.md) §3 (responses, budgets), §7 (signatures, error rules)
- [../../docs/PRODUCT.md §7](../../docs/PRODUCT.md#7-what-correct-means-here)
- `ai/STATUS.md` — chosen model IDs and the "how to" findings from AI-02 (structured output, latency settings, image resolution)
- `ai/eval/cases.csv` — **dev rows only**

## Design decisions already made

1. **The model returns as little as possible.** Short outputs are faster and safer. Display strings come from the recipe where they exist.
2. **`watch_frame` never writes text.** The model returns only `status`, `mistake_id`, `confidence`. `headline`, `fix`, `spoken` are copied in code from the matching `WatchFor`. A `mistake_id` that is not in the step → treated as `ok`.
3. **`check_frame` reuses a known mistake's strings** when its `mistake_id` matches one of the step's `watch_fors`; only otherwise does it use the model's own `headline` / `fix` / `spoken`, clamped to the word limits.
4. **`unsure` is a first-class answer**, chosen whenever the relevant part of the work is not clearly visible.
5. **Temperature 0**, minimal thinking, small max output tokens, both calls.

## Tasks

### AI-04.1 Prompts

**Do** — `src/ghostchef_ai/prompts/check.md` and `prompts/watch.md` (or `.py` constants).

`check` prompt must establish:
- Role: comparing a learner's first-person photo with a chef's first-person reference photo for **one step** of a recipe.
- Inputs, in this order and labelled in text: `REFERENCE (chef, correct result of this step)` image, `LEARNER (current state)` image, then the step as JSON (`title`, `instruction`, `success_criteria`, `watch_fors` with ids).
- Decision policy:
  - `pass` only if every success criterion that can be seen is satisfied.
  - `fix` only if a criterion is **visibly** violated. Prefer the id of a listed `watch_fors` entry when it matches; otherwise `mistake_id: null` and write a headline (≤ 4 words) and fix (≤ 8 words, an action the learner can take with their hands).
  - `unsure` if the food is out of frame, blocked, blurred, too dark, or the step in view is clearly a different one. Then `fix` says how to give a better view.
  - Differences that do not matter (different hands, mat, lighting, a tidier or messier but acceptable result) are not mistakes.
  - Never comment on taste, temperature, hygiene, or anything not visible.
- `spoken`: one friendly sentence, at most ~20 words, no lists, suitable for text-to-speech.
- `confidence`: probability that the verdict is right.

`watch` prompt must establish:
- One photo, the step title, and a list of known mistakes with ids and descriptions.
- Answer `warn` with a `mistake_id` **only** when that specific mistake is clearly visible right now. Work in progress is not a mistake: a half-covered sheet is `ok`. Anything unclear is `ok` with low confidence.
- Never report a mistake that is not in the list.

**Acceptance:** prompts are committed as files; nothing in them mentions sushi specifically (they must work for any recipe).

### AI-04.2 `check_frame`

**Do** — `src/ghostchef_ai/check.py`:
- Build the request with the check model from `model_ids()`, structured output with this response schema: `verdict` (enum), `mistake_id` (nullable string), `headline`, `fix`, `spoken`, `confidence` (number), plus an optional short `evidence` string (what the model saw; logged, not returned).
- `ref_image_jpeg=None` is allowed: the prompt then says no reference is available and relies on criteria only (this path is also the "no-ref" ablation in AI-07).
- Post-processing, in this order:
  1. Unknown `mistake_id` → `None`.
  2. If `mistake_id` matches a `WatchFor`, overwrite `headline`, `fix`, `spoken` with that entry's strings.
  3. `pass` → `fix = ""`, `mistake_id = None`; empty headline → `"Looks right"`.
  4. `clamp_words` headline to 4 and fix to 8.
  5. Clamp `confidence` to 0–1. **If `verdict` is `pass` or `fix` and `confidence < 0.5` → convert to `unsure`** with headline `"Can't tell"` and a generic better-view instruction.
  6. Fill `model` with the model ID used.
- Wrap the call in the timeout budget (`timeout_s`), map errors with `client.map_error`, retry once on `AIInvalidOutput`.

**Acceptance**
- Unit tests with a stubbed client cover every post-processing rule, the timeout → `AITimeout`, and quota → `AIQuotaError`.
- `python -m ghostchef_ai check --step 3 --frame <a real dev frame> --ref fixtures/images/step-3.jpg` returns a valid result against the real API.

### AI-04.3 `watch_frame`

**Do** — `src/ghostchef_ai/watch.py`:
- If the step has no `watch_fors` → return `ok` immediately, no model call.
- Request with the watch model, the lowest image-resolution setting that still works (from AI-02), response schema `status` (enum), `mistake_id` (nullable), `confidence`.
- Post-processing: `warn` with an unknown or null id → `ok`; on `warn` copy `headline`, `fix`, `spoken` from the `WatchFor`; on `ok` set them to `""`.
- Same timeout and error handling as `check_frame`, **no retry** (the next tick is the retry).

**Acceptance**
- Unit tests as above.
- CLI call on a real dev frame of a mistake returns `warn` with the right id; on a correct frame returns `ok`. Record what happened, including if it did not.

### AI-04.4 Wire the public surface

**Do** — `__init__.py` dispatches the real path to `check.check_frame` and `watch.watch_frame`. Fake mode unchanged.

**Acceptance:** `GHOSTCHEF_AI_FAKE=1 pytest` still passes; with fake off and a key set, the CLI uses the real functions.

### AI-04.5 Iterate on the dev set

**Do**
- A small script or the beginnings of `eval.py`: run `check_frame` over all **dev** rows of `cases.csv`, print a table `label → verdict` counts, and list every disagreement with the file name and the model's `evidence`.
- Read the disagreements. Change the prompt or the criteria wording in the fixture, not the labels. Three or four rounds at most; stop when the remaining errors are frames a person also finds ambiguous.
- Try the two frame sizes (long edge 1280 vs 768 for check; 512 vs 384 for watch) and note the effect on latency and correctness.
- **Do not open or run `heldout` rows.**

**Acceptance**
- `STATUS.md` records, for the dev set: counts per cell of the confusion table for check, the same for watch (single-frame, before debounce), median latency for each, the model IDs, the date. Label it clearly as **dev-set, used for tuning**.
- If false approvals remain on clear mistakes after iteration, say so plainly in `STATUS.md` and raise it at the next sync: this is risk R-02 materialising.

## Verification

```bash
cd ai
ruff check .
GHOSTCHEF_AI_FAKE=1 GHOSTCHEF_AI_FAKE_DELAY=0 pytest -q
python -m ghostchef_ai check --step 3 --frame eval/frames/dev/<some-frame>.jpg --ref fixtures/images/step-3.jpg
python -m ghostchef_ai watch --step 3 --frame eval/frames/dev/<some-frame>.jpg
```

## Out of scope

Debounce logic (clients own it; AI-07 simulates it for measurement). Held-out evaluation and the ablation (AI-07). HTTP error codes (backend maps them).

## When done

Update `STATUS.md` (batch 04, the tuned frame sizes in "Tuned values the clients need"), commit `[ai] AI-04 real check_frame and watch_frame`, push, and tell the backend owner that BE-03 can switch `GHOSTCHEF_AI_FAKE` off.
