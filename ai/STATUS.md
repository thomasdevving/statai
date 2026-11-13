# `ai/` status

> Updated by the track owner after every batch. Other tracks read this file for model IDs, limits, and Live protocol facts. Write only what was run and observed.

## Batches

| # | Batch | Status | Date / commit | Notes |
|---|---|---|---|---|
| 01 | Package skeleton, fake mode, fixture | NOT STARTED | | |
| 02 | Gemini access and model selection | NOT STARTED | | |
| 03 | Chef footage and evaluation set | NOT STARTED | | |
| 04 | Check and watch | NOT STARTED | | |
| 05 | Live voice config and token | NOT STARTED | | |
| 06 | Recipe extraction from video | NOT STARTED | | |
| 07 | Evaluation and tuning | NOT STARTED | | |

Status words: `DONE`, `DONE (fake)`, `PARTIAL`, `BLOCKED`, `NOT STARTED` (defined in docs/PLAN.md §8).

## Gemini account facts (AI-02 fills this in)

| Fact | Value | How verified |
|---|---|---|
| Key source (event credits / own project) | — | |
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

## Needs from other tracks

- —
