# Track: `ai/` — Gemini package, fixture recipe, evaluation

**Owner: Aleksandr**

You own **every prompt and every Gemini call** in Ghost Chef, the fixture recipe everyone develops against, and the evaluation that produces the numbers for the pitch. Your code is a Python package, `ghostchef_ai`, that the backend imports. You never write HTTP endpoints, database code, or ffmpeg calls.

New here? Read [../README.md](../README.md), then [../docs/API-CONTRACT.md](../docs/API-CONTRACT.md) §7 and §8 (your public interface), then this file.

## What you deliver

| Deliverable | Consumer |
|---|---|
| `ghostchef_ai` package with the exact public surface in API-CONTRACT §7 | `backend/` |
| Fake mode (`GHOSTCHEF_AI_FAKE=1`) | `backend/` tests, early `ios/` and `web/` work |
| `fixtures/sushi_recipe.json` + `fixtures/images/step-N.jpg` | `backend/` seed, client fixtures |
| Verified model IDs, rate limits, Live protocol facts in [STATUS.md](STATUS.md) | everyone |
| Chef footage and a labelled evaluation set | yourself, the pitch |
| Measured results | `web/` (deck), [../docs/EVALUATION.md](../docs/EVALUATION.md) |

## Setup

Requires Python 3.11 or newer. No ffmpeg needed for the package itself (AI-03 uses ffmpeg in a helper script).

```bash
cd ai
python -m venv .venv
source .venv/bin/activate            # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"
cp .env.example .env                 # then put your GEMINI_API_KEY in .env
pytest
```

These commands work after AI-01 has created `pyproject.toml` and `.env.example`.

## Target layout

```
ai/
  pyproject.toml
  .env.example
  README.md  STATUS.md
  src/ghostchef_ai/
    __init__.py        public surface, dispatches to fake or real
    schemas.py         pydantic models (API-CONTRACT §7)
    errors.py          AIError and subclasses
    config.py          env, model ids, is_fake()
    client.py          google-genai client, error mapping, timeouts      (AI-02)
    fake.py            deterministic fake implementations                 (AI-01)
    check.py           check_frame                                        (AI-04)
    watch.py           watch_frame                                        (AI-04)
    live.py            build_live_config, mint_live_token                 (AI-05)
    ingest.py          extract_recipe                                     (AI-06)
    eval.py            evaluation runner (python -m ghostchef_ai.eval)    (AI-07)
    cli.py / __main__.py   command line
    prompts/           prompt text as .md or .py constants, one per call
  fixtures/
    sushi_recipe.json
    images/step-1.jpg …
  eval/
    cases.csv          labelled frames (AI-03)
    qa.csv             voice Q&A cases (AI-05)
    frames/            committed, downscaled eval frames
    results/           one JSON + one markdown per run (AI-07)
  footage/             raw video — gitignored, shared outside git
  scripts/             helpers (placeholders, frame extraction, smoke tests)
  tests/
```

## Batches

Run them in order. One Claude session per batch. The kickoff prompt is in [../docs/PLAN.md §7](../docs/PLAN.md#7-working-with-claude-on-each-laptop).

| # | Batch | Gate | Needs | Unblocks | A human must |
|---|---|---|---|---|---|
| 01 | [Package skeleton, fake mode, fixture](tasks/01-package-skeleton-and-fixture.md) | G0 | — | BE-01, IOS-01, WEB-01 | — |
| 02 | [Gemini access and model selection](tasks/02-gemini-access-and-models.md) | G0→G1 | 01, an API key | 04, 05, 06 | Get the key; read limits in AI Studio |
| 03 | [Chef footage and evaluation set](tasks/03-footage-and-eval-set.md) | G1 | ingredients, a camera | 04, 06, 07, BE-02 | Cook, film, label |
| 04 | [Check and watch](tasks/04-check-and-watch-prompts.md) | G1 | 02, some frames from 03 | BE-03 | Judge prompt outputs |
| 05 | [Live voice config and token](tasks/05-live-voice-config-and-token.md) | G2→G3 | 02 | BE-05, IOS-05 | Listen to answers |
| 06 | [Recipe extraction from video](tasks/06-recipe-extraction.md) | G3 | 02, chef video from 03 | BE-06 | Review extracted steps |
| 07 | [Evaluation and tuning](tasks/07-evaluation-and-tuning.md) | G3→G4 | 03, 04, deployed backend | pitch evidence | Sign off the numbers |

03 is physical work (cooking and filming) and runs in parallel with 02 and 04. Start it as early as ingredients allow: every other batch gets better with real footage.

## Rules for this track

- **The public surface is frozen.** Function names, signatures, and model fields in API-CONTRACT §7 change only through the contract's change protocol. Add private helpers freely.
- **Fake mode must keep working forever.** Every later batch keeps `GHOSTCHEF_AI_FAKE=1` passing its tests. The backend's test suite depends on it.
- **Prompts are code.** Keep each prompt in `prompts/`, one file per call, and commit prompt changes with the dev-set result that motivated them.
- **Model IDs come from the account, not from memory.** AI-02 verifies them and writes them to STATUS.md. Until then the defaults in `config.py` are placeholders.
- **Look at `dev` frames only** while writing prompts. `heldout` frames are run once, at the end, in AI-07.
- **Never write a result you did not measure.** STATUS.md and `eval/results/` hold measured values with the date, the model ID, and the set size. Targets live in [../docs/EVALUATION.md](../docs/EVALUATION.md).
- **No footage of people's faces, no bystanders, no raw video in git.** The repository is public.
- Verify SDK parameter names (structured output, thinking configuration, media resolution, Live setup) against the current documentation at `https://aistudio.google.com/docs/` before using them. The SDK has changed across Gemini generations.

## Command line (available from AI-01, real from AI-04 onward)

```bash
python -m ghostchef_ai models
python -m ghostchef_ai check --step 3 --frame path/to/frame.jpg --ref fixtures/images/step-3.jpg
python -m ghostchef_ai watch --step 3 --frame path/to/frame.jpg
python -m ghostchef_ai extract path/to/chef.mp4 -o out.json
python -m ghostchef_ai live-config
python -m ghostchef_ai.eval --split dev --config full
```

`--step N` loads step N from `fixtures/sushi_recipe.json` unless `--recipe other.json` is given. `check --no-ref` sends no reference image; `-v` (real mode) also prints latency and the raw model answer (with `evidence`) to stderr. For several frames at two sizes, use `python scripts/dev_eval.py` (AI-04.5; dev rows only).
