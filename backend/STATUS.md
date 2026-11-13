# `backend/` status

> Updated by the track owner after every batch. Clients read this file for the base URLs. Write only what was run and observed.

## Batches

| # | Batch | Status | Date / commit | Notes |
|---|---|---|---|---|
| 01 | Skeleton and full API on memory + fake AI | DONE (fake) | 2026-11-14 | Every §2–§5 endpoint on the memory store + fake AI (AI-01 `815f2a2`). See below. |
| 02 | Supabase schema, storage, seed | NOT STARTED | | |
| 03 | Check and watch, production-grade | NOT STARTED | | |
| 04 | Deploy to Railway + emergency mode | NOT STARTED | | |
| 05 | Live token, monitor, session summary | NOT STARTED | | |
| 06 | Ingestion pipeline with ffmpeg | NOT STARTED | | |
| 07 | Hardening and end-to-end | NOT STARTED | | |

Status words: `DONE`, `DONE (fake)`, `PARTIAL`, `BLOCKED`, `NOT STARTED` (defined in docs/PLAN.md §8).

## Where the API is

| Environment | Base URL | `ai_mode` | `storage` | Since |
|---|---|---|---|---|
| Owner's laptop on the LAN | `http://192.168.200.152:8000` (when the owner runs it; IP may change) | `fake` | `memory` | 2026-11-14 |
| Production (Railway) | — | — | — | — |
| Emergency laptop (hotspot) | — | — | — | — |

The demo key is shared privately, never written here.

## Contract conformance

| Endpoint group | Implemented | Tested | Notes |
|---|---|---|---|
| `/health` | yes | yes | Without `ghostchef_ai` installed `ai_mode` would be `unavailable` (not a contract value; broken setup only) |
| Recipes and steps (§2) | yes | yes | Upload via memory-mode `PUT /local-upload` (`resumable_endpoint: null`). `/process` uses fixture images as reference stills (no ffmpeg until BE-06); a changed `timestamp_s` is stored but not re-extracted. Publishing an already-published recipe returns 200 |
| `/check`, `/watch` (§3) | yes | yes | No JPEG validation / size limits / in-flight guard yet (BE-03); hard 8 MB read cap |
| Sessions, events, monitor (§4) | yes | yes | `steps_passed_first_try` ignores `check_unsure` (not a verdict). Monitor's last frame / result / latency are in-process memory |
| `/live-token` (§5) | yes | yes | Fake token (`locked: false`) |

## Last smoke run

| Date | Target | Result | check p50 / max ms | watch p50 / max ms |
|---|---|---|---|---|
| 2026-11-14 | `http://localhost:8000` (fake, memory) | exit 0, every status as expected | 751 / 751 (n=2) | 301 / 301 (n=6) |

Fake-mode latencies: they measure `GHOSTCHEF_AI_FAKE_DELAY` (0.3 s default), not Gemini.

## Accounts (who holds them; no secrets here)

| Service | Project name | Owner | Region / plan |
|---|---|---|---|
| Supabase | Echo (`trfaijfrgfyrjvhocqif`) | Stelios | eu-north-1, created 2026-11-14 |
| Railway | — | — | — |

## Recovery tests (BE-07)

| Test | Expected | Observed | Date |
|---|---|---|---|
| Model timeout forced | `504 model_timeout` | — | — |
| Quota error forced | `429 quota_exhausted` | — | — |
| Second `/watch` while one is in flight | `429`, retryable | — | — |
| Oversized frame | `413` | — | — |
| Non-JPEG frame | `415` | — | — |
| Wrong demo key | `401` | — | — |
| Supabase unreachable | `500 internal`, server stays up | — | — |

## BE-01 notes (2026-11-14)

Verified in this session: `ruff check .` clean; `pytest -q` 67 passed (fake AI, memory store, no network); `scripts/smoke.py --fast` exit 0 against a local uvicorn; `curl /health` → `{"status":"ok","contract_version":"2.0","ai_mode":"fake","storage":"memory"}`. `openapi.json` exported (the contract still wins).

- Seeded recipe id `00000000-0000-4000-8000-000000000001`; step ids are `uuid5(recipe_id, "step-<idx>")` (step 3 = `rice_too_thick`).
- Server must run with `ghostchef_ai` installed (`pip install -e ../ai`).
- Security review (security-tester) ran on the batch; its six findings were fixed and re-verified clean: `/process` race, auth checked before any body is parsed (`app/guard.py`), body caps (64 KB JSON → `413`, 8 MB `/check` `/watch`), upload token consumed only after a complete upload (a failed upload can retry the same URL), NaN/Infinity rejected, `/docs` and `/openapi.json` not served (use `backend/openapi.json`).
- Any path without a valid key, including unknown paths, answers `401`; only `/health`, `/app/*`, `/local-files/*`, `/local-upload/*` are open.
- Known, accepted for memory mode: sessions, events and monitor metrics grow in process memory without a limit.
- The LAN URL above was the owner's address when this was written; it has not been tested from another device.

## Needs from other tracks

- —
