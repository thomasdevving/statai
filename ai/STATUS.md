# `ai/` status

> Updated by the track owner after every batch. Other tracks read this file for model IDs, limits, and Live protocol facts. Write only what was run and observed.

## Batches

| # | Batch | Status | Date / commit | Notes |
|---|---|---|---|---|
| 01 | Package skeleton, fake mode, fixture | DONE (fake) | 2026-11-14 · `273fadb` | Fake mode only: no Gemini call exists yet. 38 tests pass, ruff clean, all verification commands run (Windows, Python 3.13). Fixture recipe and the six reference images are **placeholders**, not chef footage. Model IDs in `config.py` are unverified placeholders until AI-02. |
| 02 | Gemini access and model selection | DONE | 2026-11-14 · `19091c3` + not yet committed | On the **event key** (project "Hack Junction 2026-7638", Tier 3, paid): image, two-image, video, Live audio, Live function call and fully locked ephemeral token all **PASS**; limits read in AI Studio; models pinned. Earlier tests ran on a different key (see account facts). `check` stays provisionally on the lite model; AI-04 decides with real frames. The account's data-use wording was not found on the pages read. The OpenAI stand-in is no longer used. |
| 03 | Chef footage and evaluation set | PARTIAL — team decided not to cook; see "Footage and evaluation set" | 2026-11-14 · `3491963` | **Tooling done, physical work not started.** Done: `scripts/extract_frames.py` (03.3), `scripts/check_cases.py` (validates `eval/cases.csv`, prints split × label counts, `--scaffold` adds unlabelled rows), `scripts/side_by_side.py` (for 03.6), `eval/` layout, empty `eval/cases.csv`, `eval/README.md` template; 18 new tests; 74 pass. ffmpeg 9.0.2 installed on the owner's laptop (winget `Gyan.FFmpeg`); extraction verified on a generated 6 s test video (frame names, 720×1280 size, `--at`), **not yet on real footage**. **Not done (human):** 03.1 chef take, 03.2 mistake clips, 03.4 labelling, 03.5 real stills + fixture v1, 03.6 the "can a person tell?" check. |
| 04 | Check and watch | NOT STARTED | | |
| 05 | Live voice config and token | NOT STARTED | | |
| 06 | Recipe extraction from video | NOT STARTED | | |
| 07 | Evaluation and tuning | NOT STARTED | | |

Status words: `DONE`, `DONE (fake)`, `PARTIAL`, `BLOCKED`, `NOT STARTED` (defined in docs/PLAN.md §8).

## Gemini account facts (AI-02 fills this in)

| Fact | Value | How verified |
|---|---|---|
| Key source (event credits / own project) | Event key "Workshop API key" (`…SarI`), project "Hack Junction 2026-7638" (`junction26hel-7638`), now in the owner's untracked `ai/.env`. The first round of tests on 2026-11-14 ran on a different key from an unknown project; everything in the "event key re-check" table below ran on the event key | AI Studio API keys page; last-4 check done locally, key never printed |
| Project tier | **Tier 3**, key marked **paid**, billing account `…7F15` | AI Studio API keys page |
| Data-use / retention setting of this account | Not stated on the pages read. AI Studio labels the event key "paid"; check the terms for paid use before quoting any policy | AI Studio API keys page |
| Model for `video` (extract_recipe) | `gemini-3.5-flash` | Video test PASS (below) |
| Model for `check` | `gemini-3.5-flash-lite` (**provisional**) | Image tests PASS; revisit `gemini-3.8-flash` in AI-04 when not overloaded |
| Model for `watch` | `gemini-3.5-flash-lite` | Image tests PASS, ~0.9 s |
| Model for `live` | `gemini-3.8-live` | Live audio + function call + locked token PASS |
| Rate limits for the watch model (RPM / TPM / RPD) | Event project, Gemini 3.5 Flash Lite: 30K / 30M / unlimited | AI Studio rate-limit page, 2026-11-14 |
| Rate limits for the check model | Same model as watch (30K / 30M / unlimited); Gemini 3.8 Flash 20K / 20M / unlimited if AI-04 switches | |
| Rate limits for the video model | Gemini 3.5 Flash: **not listed** on the page; the page shows 3 Flash, 3.6 Flash, 3.8 Flash (each 20K / 20M / unlimited) | |
| Rate limits for the Live model | Gemini 3.8 Live: RPM unlimited, TPM 10M, RPD unlimited (no concurrent-session figure shown) | |

All the limits above are for the **event project**. The page showed 0 usage on every model over 28 days, which fits our tests having run on the other key. The watcher's ~24 requests a minute per session is far below 30K RPM.

`models.list` on 2026-11-14 showed 28 models, including `gemini-3.5-flash`, `gemini-3.5-flash-lite`, `gemini-3.1-flash-lite`, `gemini-3.6-flash`, `gemini-3.7-flash`, `gemini-3.8-flash`, `gemini-4-argon`, `gemini-4-carbon`, `gemini-4-hydrogen`. **No Live model appears in the list**, but `gemini-3.8-live` and `gemini-3.1-flash-live-preview` both connect.

### Gemini smoke tests, 2026-11-14 (owner's laptop, Windows; network not recorded)

Image tests used the placeholder `step-3.jpg` at low media resolution: "correct" = read the heading text; two-image = same / different picture. These are capability checks, **not** cooking-judgement results. The first run without a thinking setting was discarded (see the "Findings" list); this is the second run, 3 repeats per model.

| Model | image + JSON | latency p50 / max ms | two images | 512 px frame | Notes |
|---|---|---|---|---|---|
| `gemini-3.5-flash-lite` | 3/3 | 906 / 1842 | 2/2 | 860 ms | Most reliable and fastest |
| `gemini-3.1-flash-lite` | 1/3 (2 timeouts) | 1022 (n=1) | 2/2 | 6438 ms | Flaky |
| `gemini-3.6-flash` | 3/3 | 10837 / 12102 | 1/2 (1 timeout) | 12184 ms | Too slow for a 2 s check |
| `gemini-4-hydrogen` | 0/3 | — | 0/2 | — | Output cut off at 60 tokens even at minimal thinking; also 503s and one 429 |
| `gemini-3.8-flash` | 0/3 | — | 0/2 | — | Only 503 "high demand" and timeouts; **unverified, not rejected** |

| Gemini-only test | Model | Result |
|---|---|---|
| Video with timestamps (12 s generated counter clip, Files API) | `gemini-3.5-flash-lite` | PASS: moments at 0 s and 10 s, both correct; upload + processing 6.1 s, generate 1.2 s |
| | `gemini-3.5-flash` | PASS: 3 s and 8 s, correct; upload 4.9 s, generate 7.3 s, thinking MINIMAL |
| | `gemini-3.8-flash` | Not tested: rejects MINIMAL thinking, then 503 high demand |
| Live text → audio | `gemini-3.8-live` | PASS: 95,520 bytes of `audio/pcm;rate=24000`, first audio 411 ms, transcript "Hello, how can I help you today?" |
| | `gemini-3.1-flash-live-preview` | PASS: first audio 565 ms |
| Live function call | `gemini-3.8-live`, `gemini-3.1-flash-live-preview` | PASS: `ping` arrived as a tool call; tool response accepted |
| Ephemeral token, model + modalities + **system instruction + tools locked** | `gemini-3.8-live` | PASS: minted (`auth_tokens/…`), a session opened with only the token (API version `v1beta`), audio returned, first audio 407 ms |

Total paid generate calls: 70 image calls across both runs plus 5 video calls and a few Live turns; token counts are in the script output, cost not measured.

### Event key re-check, 2026-11-14 (the key now in use)

| Test | Model | Result |
|---|---|---|
| image + JSON, 5 repeats | `gemini-3.5-flash-lite` | 5/5, p50 827 ms, max 2356 ms; two images 2/2; 512 px frame 633 ms |
| image + JSON, 5 repeats | `gemini-3.8-flash` | 2/5: reachable (no 503s now), p50 2361 ms, but thinking level LOW still overruns a 60-token answer; needs a larger output limit if AI-04 tries it for `check` |
| Video with timestamps | `gemini-3.5-flash` | PASS: 0 s and 10 s, correct; upload 4.9 s, generate 2.1 s |
| Live text → audio + function call | `gemini-3.8-live` | PASS: first audio 446 ms, `audio/pcm;rate=24000`, `ping` tool call |
| Ephemeral token, fully locked | `gemini-3.8-live` | PASS: first audio 515 ms |

### Findings that change how we call Gemini

- **Thinking tokens count against `max_output_tokens`.** With a small limit, thinking models return empty or cut-off JSON. `client.py` now asks for thinking level MINIMAL, steps down to LOW for models that reject MINIMAL (`gemini-3.8-flash` does), and reports cut-off output as `AIInvalidOutput`.
- **Gemini pretty-prints JSON**, so it needs more output tokens than OpenAI for the same answer (two-image check: 20 tokens too few, 60 enough).
- **Live needs an explicit API version.** The SDK's default answered HTTP 404 on every Live model; `v1beta` and `v1alpha` both connect.
- **Ephemeral tokens:** the SDK warns they are "v1alpha only", yet a `v1beta` session opened with a fully locked token. Record which version IOS-05 uses.
- **High-demand 503s** happened repeatedly on `gemini-3.8-flash` and `gemini-4-hydrogen` during the test window. Plan for one retry on 503 in `/check`, which the contract already specifies.

## Interim OpenAI stand-in (NOT Gemini — development only)

Used while Gemini access was pending. **No longer used** since the Gemini key arrived (2026-11-14); the code path stays for emergencies only, and the default provider is Gemini. **Nothing measured here may be reported as a Gemini result or used in the deck.**

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
| check_frame | — not implemented until AI-04 | — | — | — | — | — |
| watch_frame | — not implemented until AI-04 | — | — | — | — | — |
| One-image JSON call (smoke test, proxy for watch) | `gemini-3.5-flash-lite` | 3 | 906 | 1842 | 2026-11-14 | not recorded |
| extract_recipe | — not implemented until AI-06; video smoke on a 12 s clip: 4.9 s upload + 7.3 s generate (`gemini-3.5-flash`) | 1 | — | — | 2026-11-14 | not recorded |

## Tuned values the clients need

| Value | Current | Set by |
|---|---|---|
| `WATCH_THRESHOLD` (client debounce confidence) | 0.7 (contract default, untuned) | AI-07 |
| Watch frame long edge | 512 px (contract default, untuned) | AI-04 |
| Check frame long edge | 1280 px (contract default, untuned) | AI-04 |

## Live facts for `ios/` (AI-05 fills this in)

| Fact | Value |
|---|---|
| WebSocket URL used with an ephemeral token | — (AI-05). Known from AI-02: the API version must be explicit; `v1beta` and `v1alpha` connect, the SDK default gives HTTP 404 |
| How the token is passed | — (AI-05). Known from AI-02: the token name (`auth_tokens/…`) works in place of the API key with the Python SDK |
| First message (setup) shape when `locked` is true | — |
| Input audio format | — |
| Output audio format | `audio/pcm;rate=24000` (observed in AI-02 on `gemini-3.8-live` and `gemini-3.1-flash-live-preview`) |
| How a function call arrives and how to answer it | — |
| Session length limit and resumption | — |
| Can `system_instruction` and `tools` be locked into the token? | — |

## Footage and evaluation set (AI-03 fills this in)

| Item | Value |
|---|---|
| Chef video location (outside git) | — none filmed. **Team decision 2026-11-14: no cooking.** |
| Recorded with (glasses model / phone) | — |
| Who appears; consent given? | — |
| Dev cases / held-out cases | 0 / 0 labelled |

**Interim development material (not the evaluation set).** With no footage of our own, one third-party stock clip is used **privately** for AI-04 prompt work:

- Mixkit clip 46009, "Sushi rice being flattened while making sushi" (`https://mixkit.co/free-stock-video/sushi-rice-being-flattened-while-making-sushi-46009/`), free 720p version, downloaded 2026-11-14 from `assets.mixkit.co`. Licence shown on the page: **"720p Version for Personal Use only", "Mixkit Restricted License"**; the commercial version is a paid Envato licence. The owner chose private development use only.
- Stored in `ai/footage/mixkit/` (gitignored): the clip, 9 frames every 2.5 s (`frames/`), `contact-sheet.jpg`. **Never commit these, never use them in the fixture the backend serves, in the demo, or in the deck.**
- What it shows: 21.6 s, 1280×720 landscape, 25 fps, true top-down over a bamboo mat. The camera is **opposite the chef** (hands enter from the top of the frame), so it is not first-person; rotated 180° it approximates the wearer's view. Every frame is **mid-step**: rice heaped on half the nori while being spread, bare nori on the other half. No finished state, no deliberate mistakes.
- Useful for: checking the prompts treat work in progress as **not** a mistake (watch → `ok`), and that partly covered views give `unsure`. Not useful for: false-approval or detection numbers. Nothing measured on it may be reported as accuracy.
- Not labelled: labels must be set by a person (AI-03.4).

**What AI-03 still cannot do without real footage:** a labelled dev/held-out set with mistakes, real reference stills for the fixture, the "can a person tell?" check, and every number in EVALUATION.md §4. Options that avoid cooking (a team decision, not made here): ready-made rice and assembly only; non-food props; or a non-food task. Until one is chosen, AI-07's evaluation has no data.

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
