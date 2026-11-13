# AI-01 — Package skeleton, schemas, fake mode, fixture recipe

| | |
|---|---|
| **Track** | `ai/` |
| **Gate** | G0 — this batch unblocks all three other tracks. Do it first and push within the hour. |
| **Depends on** | nothing |
| **Unblocks** | BE-01 (imports the package), IOS-01 and WEB-01 (use the fixture) |
| **Size** | Small |
| **Model** | Opus 5.5. Task 6 (writing the fixture text) is fine on Sonnet 5.5. |
| **Needs a human for** | nothing |

## Goal

An installable Python package `ghostchef_ai` whose public surface matches [API-CONTRACT §7](../../docs/API-CONTRACT.md#7-internal-interface-backend--ai) exactly, working end to end in **fake mode** with no network and no API key, plus a hand-written sushi fixture recipe with placeholder images.

## Read first

- [../README.md](../README.md) — layout and rules of this track
- [../../docs/API-CONTRACT.md](../../docs/API-CONTRACT.md) §2 (Step object and word limits), §3 (check / watch responses), §5 (Live), §7, §8
- [../../docs/TECH-SPEC.md](../../docs/TECH-SPEC.md) "Flows" and "Display spec" for what the text fields are used for

## Tasks

### AI-01.1 Project scaffold

**Do**
- Create `ai/pyproject.toml`: project name `ghostchef-ai`, version `0.1.0`, `requires-python = ">=3.11"`, `src/` layout, package `ghostchef_ai`.
- Runtime dependencies: `google-genai`, `pydantic>=2`, `python-dotenv`. Optional group `dev`: `pytest`, `pytest-asyncio`, `ruff`, `pillow`.
- Configure pytest (`asyncio_mode = "auto"`, `testpaths = ["tests"]`) and ruff (line length 100) in `pyproject.toml`.
- Create `ai/.env.example` with `GEMINI_API_KEY=`, `GHOSTCHEF_AI_FAKE=1`, and commented `GHOSTCHEF_MODEL_VIDEO`, `GHOSTCHEF_MODEL_CHECK`, `GHOSTCHEF_MODEL_WATCH`, `GHOSTCHEF_MODEL_LIVE`, `GHOSTCHEF_FIXTURE_DIR`, `GHOSTCHEF_AI_FAKE_DELAY`.

**Acceptance**
- `pip install -e ".[dev]"` succeeds in a fresh virtualenv.
- `python -c "import ghostchef_ai"` succeeds.

### AI-01.2 Schemas and errors

**Do**
- `src/ghostchef_ai/schemas.py`: the pydantic models `WatchFor`, `StepSpec`, `RecipeDraft`, `CheckResult`, `WatchResult`, `LiveConfig`, `LiveToken`, copied field-for-field from API-CONTRACT §7.
- Add validation that fails loudly on contract violations: `StepSpec.title` ≤ 4 words, `key_line` ≤ 8 words, `WatchFor.headline` ≤ 4 words, `WatchFor.fix` ≤ 8 words, `WatchFor.id` matches `^[a-z][a-z0-9_]*$` and is unique within a step, `idx ≥ 1`, `0 ≤ confidence ≤ 1`, `RecipeDraft.steps` have consecutive `idx` starting at 1.
- A helper `clamp_words(text, n)` (used later to repair model output) in `schemas.py` or a small `text.py`.
- `src/ghostchef_ai/errors.py`: `AIError(Exception)` and subclasses `AITimeout`, `AIQuotaError`, `AIUnavailable`, `AIInvalidOutput`.

**Acceptance**
- Unit tests cover: a valid step parses; each word-limit violation raises; duplicate `watch_fors` ids raise; `CheckResult(verdict="maybe", …)` raises.

### AI-01.3 Configuration

**Do**
- `src/ghostchef_ai/config.py`:
  - `is_fake() -> bool`: true when `GHOSTCHEF_AI_FAKE` is `1`, `true`, or `yes` (case-insensitive).
  - `model_ids() -> dict[str, str]` with keys `video`, `check`, `watch`, `live`. Defaults are **placeholders** to be replaced in AI-02; each is overridable by its `GHOSTCHEF_MODEL_*` env var. In fake mode every value is the string `"fake"`.
  - `fixture_dir() -> Path`: `GHOSTCHEF_FIXTURE_DIR` if set, else `<this file>/../../../fixtures` resolved. Works for editable installs, which is how the backend installs the package.
  - Load `.env` from the current directory if present (`python-dotenv`), without overriding real environment variables.

**Acceptance**
- Tests: env overrides are honoured; fake mode returns `"fake"` for all four.

### AI-01.4 Fake implementations

**Do** — `src/ghostchef_ai/fake.py`, all deterministic, no network:

| Function | Fake behaviour |
|---|---|
| `extract_recipe` | Sleeps the fake delay ×4, then returns the `RecipeDraft` loaded from `fixture_dir()/sushi_recipe.json`. If `title_hint` is given it replaces the title. |
| `check_frame` | If `len(frame_jpeg) < 5000` → `unsure` (headline `"Can't tell"`, fix `"Look straight down at mat"`, confidence 0.3). Otherwise a per-step call counter: 1st, 3rd, 5th… call for a step that has `watch_fors` → `fix` using the step's **first** watch-for (its `id`, `headline`, `fix`, `spoken`; confidence 0.9); 2nd, 4th… call → `pass` (headline `"Looks right"`, fix `""`, spoken `"That looks right."`, confidence 0.9). Steps without `watch_fors` always pass. |
| `watch_frame` | Per-step call counter: calls 1–3 → `ok`; calls 4–6 → `warn` with the step's first watch-for (confidence 0.9); then the cycle repeats. Steps without `watch_fors` always `ok`. |
| `build_live_config` | Not faked: this is a pure function. Implement a simple first version here or in `live.py`: model from `model_ids()["live"]`, a short system instruction that includes the recipe title, every step's `idx`, `title`, `instruction`, and the transcript; `response_modalities=["AUDIO"]`; `voice=None`; `tools` containing the five function declarations from API-CONTRACT §5.2; `session_resumption=True`. AI-05 refines it. |
| `mint_live_token` | Returns `LiveToken(token="fake-token", expires_at=now+30min, new_session_expires_at=now+1min, locked=False)`. |

- Fake delay: `GHOSTCHEF_AI_FAKE_DELAY` seconds (default `0.3` for watch, ×2.5 for check). Tests set it to `0`.
- Provide `fake.reset()` to clear the counters (used by tests and by the backend's test fixtures).
- `model` field in fake results is `"fake"`.

**Acceptance**
- Tests assert the exact sequences above, the `< 5000` byte rule, and that every returned object validates against the schemas.

### AI-01.5 Public surface and CLI

**Do**
- `src/ghostchef_ai/__init__.py` exports exactly the names in API-CONTRACT §7. Each async function dispatches: fake mode → `fake.py`; otherwise → the real module. Until the real module exists, the real path raises `AIUnavailable("<function> is not implemented yet; set GHOSTCHEF_AI_FAKE=1")`.
- `src/ghostchef_ai/cli.py` + `__main__.py` using `argparse`, with subcommands `models`, `check`, `watch`, `extract`, `live-config` as shown in [../README.md](../README.md#command-line-available-from-ai-01-real-from-ai-04-onward). Output is pretty-printed JSON on stdout; errors go to stderr with a non-zero exit code.

**Acceptance**
- `GHOSTCHEF_AI_FAKE=1 python -m ghostchef_ai check --step 3 --frame fixtures/images/step-3.jpg` prints a valid `CheckResult`.
- `python -m ghostchef_ai models` prints four keys.
- With fake mode off and no key, `check` exits non-zero with the "not implemented yet" message, not a stack trace.

### AI-01.6 Fixture recipe (hand-written first version)

**Do** — create `ai/fixtures/sushi_recipe.json` as a valid `RecipeDraft`. It is a placeholder for a real chef's lesson and will be replaced by real footage in AI-03 and AI-06, so write plausible content but do not agonise.

- Title: `"Maki roll"`. Six steps is enough for the first version:

  | idx | title | What the step is | Must include watch-fors? |
  |---|---|---|---|
  | 1 | Place nori | Nori shiny side down on the mat, long edge towards you | optional |
  | 2 | Wet hands | Dip fingers in water so rice does not stick | none (not visually checkable) |
  | 3 | Spread rice | Thin even layer, leave about 2 cm of bare nori at the far edge | **yes: `rice_too_thick`, `rice_covers_top_edge`** |
  | 4 | Add fillings | One line of filling across the near third | yes: `too_much_filling` |
  | 5 | Roll | Lift the near edge of the mat, tuck, roll forward, press | optional |
  | 6 | Slice | Wet knife, cut in half, then each half in three | none |

- The **`rice_too_thick`** entry must be exactly the one used in the contract examples: headline `"Too much rice"`, fix `"Spread thinner, 2cm nori free"`, spoken `"There's a bit too much rice — spread it thinner and leave two centimetres of nori at the top."` The demo script depends on this mistake.
- Every `success_criteria` item must be something **visible in one top-down photo** (coverage, margins, placement, shape). No temperature, taste, or pressure.
- `timestamp_s`, `clip_start_s`, `clip_end_s`: invented but plausible and increasing (the fake video is imagined as about 4 minutes long).
- `transcript`: 150–300 words of invented chef narration covering all six steps, including one sentence explaining **why you wet your hands** (the demo's spoken question uses it). Mark the first line of the transcript with `[PLACEHOLDER NARRATION — replace with the real chef transcript]`.
- Respect every word limit; the schema validation from AI-01.2 must pass.

**Acceptance**
- `python -c "from ghostchef_ai.schemas import RecipeDraft; import json,pathlib; RecipeDraft.model_validate(json.loads(pathlib.Path('fixtures/sushi_recipe.json').read_text(encoding='utf-8')))"` exits 0.
- A test loads the fixture and asserts step 3 contains a watch-for with id `rice_too_thick`.

### AI-01.7 Placeholder reference images

**Do**
- `ai/scripts/make_placeholders.py` (uses Pillow): for each step in the fixture write `ai/fixtures/images/step-<idx>.jpg`, **720×1280 portrait** (the glasses' high stream size), dark background, large text `"<idx>. <title>"` and a smaller line `"PLACEHOLDER — not chef footage"`. JPEG quality 80. Each file must be larger than 5000 bytes so the fake `check_frame` does not treat it as unjudgeable.
- Run it and commit the six images.

**Acceptance**
- Six JPEGs exist, each 720×1280 and > 5 KB.

### AI-01.8 Tests green, status updated

**Do**
- `tests/` covers everything listed above. Run `ruff check .` and `pytest`.
- Update `ai/STATUS.md`: batch 01 → `DONE (fake)`, with the commit hash.

## Verification

```bash
cd ai
ruff check .
GHOSTCHEF_AI_FAKE=1 GHOSTCHEF_AI_FAKE_DELAY=0 pytest -q
GHOSTCHEF_AI_FAKE=1 python -m ghostchef_ai check --step 3 --frame fixtures/images/step-3.jpg
GHOSTCHEF_AI_FAKE=1 python -m ghostchef_ai watch --step 3 --frame fixtures/images/step-3.jpg
GHOSTCHEF_AI_FAKE=1 python -m ghostchef_ai live-config
```

On Windows PowerShell set the variables first: `$env:GHOSTCHEF_AI_FAKE='1'; $env:GHOSTCHEF_AI_FAKE_DELAY='0'; pytest -q`.

## Out of scope

Any real Gemini call (AI-02 onward). Any HTTP, database, or ffmpeg code (that is `backend/`).

## When done

Commit as `[ai] AI-01 package skeleton, fake mode, fixture`, push, and tell the backend owner the package is on `main`.
