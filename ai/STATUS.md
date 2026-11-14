# `ai/` status

> Updated by the track owner after every batch. Other tracks read this file for model IDs, limits, and Live protocol facts. Write only what was run and observed.

## Batches

| # | Batch | Status | Date / commit | Notes |
|---|---|---|---|---|
| 01 | Package skeleton, fake mode, fixture | DONE (fake) | 2026-11-14 · `273fadb` | Fake mode only: no Gemini call exists yet. 38 tests pass, ruff clean, all verification commands run (Windows, Python 3.13). Fixture recipe and the six reference images are **placeholders**, not chef footage. Model IDs in `config.py` are unverified placeholders until AI-02. |
| 02 | Gemini access and model selection | PARTIAL | 2026-11-14 · `e21276f` | **Gemini access pending** (form submitted, no answer yet). Done: client wrapper (error mapping, timeouts, per-process call cap) with 18 network-free tests; smoke script; a **temporary OpenAI stand-in** for check/watch, smoke-tested and pinned (see below). Not done until a Gemini key exists: 02.3–02.6 for Gemini (model listing, image / two-image / video / Live / function-call / ephemeral-token tests, rate limits, data settings, latency baseline, model pinning). The Gemini code path in `client.py` is written but never run. |
| 03 | Chef footage and evaluation set | PARTIAL | 2026-11-14 · not yet committed | **Tooling done, physical work not started.** Done: `scripts/extract_frames.py` (03.3), `scripts/check_cases.py` (validates `eval/cases.csv`, prints split × label counts, `--scaffold` adds unlabelled rows), `scripts/side_by_side.py` (for 03.6), `eval/` layout, empty `eval/cases.csv`, `eval/README.md` template; 18 new tests; 74 pass. ffmpeg 9.0.2 installed on the owner's laptop (winget `Gyan.FFmpeg`); extraction verified on a generated 6 s test video (frame names, 720×1280 size, `--at`), **not yet on real footage**. **Not done (human):** 03.1 chef take, 03.2 mistake clips, 03.4 labelling, 03.5 real stills + fixture v1, 03.6 the "can a person tell?" check. |
| 04 | Check and watch | NOT STARTED | | |
| 05 | Live voice config and token | NOT STARTED | | |
| 06 | Recipe extraction from video | NOT STARTED | | |
| 07 | Evaluation and tuning | NOT STARTED | | |

Status words: `DONE`, `DONE (fake)`, `PARTIAL`, `BLOCKED`, `NOT STARTED` (defined in docs/PLAN.md §8).

## Gemini account facts (AI-02 fills this in)

| Fact | Value | How verified |
|---|---|---|
| Key source (event credits / own project) | — (requested via the event form 2026-11-14, no answer yet) | |
| Project tier | — | |
| Data-use / retention setting of this account | — | |
| Model for `video` (extract_recipe) | — | |
| Model for `check` | — | |
| Model for `watch` | — | |
| Model for `live` | — | |
| Rate limits for the watch model (RPM / TPM / RPD) | — | |
| Rate limits for the check model | — | |
| Rate limits for the Live model (concurrent sessions) | — | |

Candidates seen on the public models page on 2026-11-13, **not yet tried with our key**: `gemini-4-carbon`, `gemini-4-argon`, `gemini-4-hydrogen`, `gemini-3.8-flash`, `gemini-3.6-flash`, `gemini-3.5-flash-lite`, `gemini-3.8-live`.

## Interim OpenAI stand-in (NOT Gemini — development only)

Used while Gemini access is pending, so check/watch prompts can be developed. **Nothing measured here may be reported as a Gemini result or used in the deck.** Remove once Gemini works.

- Switch: `GHOSTCHEF_PROVIDER=openai` in `ai/.env` (default `gemini`). Needs `OPENAI_API_KEY` and `pip install -e ".[openai]"`. Only `check` and `watch` exist on this path; `video` and `live` report `unsupported-on-openai`.
- Cost guard: at most 300 paid calls per process on OpenAI (`GHOSTCHEF_MAX_CALLS`; the smoke script uses 40). Low image detail, small outputs. Owner has $21 of credit; a hard spend limit in the OpenAI dashboard is the owner's job.
- Key: the owner's personal OpenAI key, in the untracked `ai/.env` only. Free listing on 2026-11-14 showed 96 models.

Smoke test, 2026-11-14, owner's laptop on Windows (network not recorded), fixture placeholder image `step-3.jpg` with low image detail. "Correct" = read the heading text; two-image = same / different picture. These are capability checks, **not** cooking-judgement results.

| Model (resolved) | image + JSON | latency p50 / max ms (n=5) | two images | 512 px frame |
|---|---|---|---|---|
| `gpt-5.4-nano` (`gpt-5.4-nano-2026-03-17`) | 5/5 | 923 / 4055 | 2/2 | 920 ms, read |
| `gpt-5.4-mini` (`gpt-5.4-mini-2026-03-17`) | 5/5 | 920 / 1945 | 2/2 | 808 ms, read |
| `gpt-4.1-mini` (`gpt-4.1-mini-2025-04-14`) | 5/5 | 890 / 1266 | 2/2 | 772 ms, read |

Run cost: 24 calls, 35,189 input tokens, 382 output tokens. The dollar charge was not measured; check the OpenAI usage page.

**Pinned interim models:** `check` = `gpt-5.4-mini` (stronger model for the judgement), `watch` = `gpt-5.4-nano` (cheapest tier; one 4 s outlier in five calls). All three passed, so this is a cost choice, not a quality finding. OpenAI rate limits for these models were **not read**: the owner can check them on the dashboard's Limits page.

## Latency baseline (measured from a laptop at the venue)

| Call | Model | n | p50 ms | max ms | Date | Network |
|---|---|---|---|---|---|---|
| check_frame | — | — | — | — | — | — |
| watch_frame | — | — | — | — | — | — |
| extract_recipe (video length: —) | — | — | — | — | — | — |

## Tuned values the clients need

| Value | Current | Set by |
|---|---|---|
| `WATCH_THRESHOLD` (client debounce confidence) | 0.7 (contract default, untuned) | AI-07 |
| Watch frame long edge | 512 px (contract default, untuned) | AI-04 |
| Check frame long edge | 1280 px (contract default, untuned) | AI-04 |

## Live facts for `ios/` (AI-05 fills this in)

| Fact | Value |
|---|---|
| WebSocket URL used with an ephemeral token | — |
| How the token is passed | — |
| First message (setup) shape when `locked` is true | — |
| Input audio format | — |
| Output audio format | — |
| How a function call arrives and how to answer it | — |
| Session length limit and resumption | — |
| Can `system_instruction` and `tools` be locked into the token? | — |

## Footage and evaluation set (AI-03 fills this in)

| Item | Value |
|---|---|
| Chef video location (outside git) | — |
| Recorded with (glasses model / phone) | — |
| Who appears; consent given? | — |
| Dev cases / held-out cases | — / — |

## Results (AI-07 fills this in; copy the table into docs/EVALUATION.md §4 through a `[docs]` commit)

Nothing measured yet.

## For other tracks: using the package (AI-01)

- Install from `backend/`: `pip install -e ../ai`, set `GHOSTCHEF_AI_FAKE=1` (and `GHOSTCHEF_AI_FAKE_DELAY=0` in tests).
- Call `ghostchef_ai.fake.reset()` between tests: the fake check/watch sequences use per-step counters.
- Fake sequences: `check_frame` → frame under 5000 bytes is `unsure`; otherwise odd calls per step are `fix` with the step's first watch-for, even calls `pass`. `watch_frame` → per step, calls 1–3 `ok`, 4–6 `warn`, repeating. Steps without watch-fors always `pass` / `ok`.
- Fixture: `ai/fixtures/sushi_recipe.json` (6 steps, `RecipeDraft`) and `ai/fixtures/images/step-1.jpg` … `step-6.jpg` (720×1280). The demo mistake is step 3, `rice_too_thick`.
- Real (non-fake) calls raise `AIUnavailable("… not implemented yet …")` until AI-04/05/06.
- Backend: keep `GHOSTCHEF_AI_FAKE=1`. The OpenAI stand-in is for `ai/` prompt work only and is not wired into `check_frame` / `watch_frame` yet (that is AI-04).

## Needs from other tracks

- **Contract wording (docs owner, no rush):** API-CONTRACT §7 says the package reads only `GEMINI_API_KEY` and the four `GHOSTCHEF_MODEL_*` variables, but the package also reads `GHOSTCHEF_AI_FAKE`, `GHOSTCHEF_AI_FAKE_DELAY` and `GHOSTCHEF_FIXTURE_DIR` (all specified by AI-01 and referenced by the backend tasks). Suggest listing them in §7 as an additive change. Nothing is blocked.
