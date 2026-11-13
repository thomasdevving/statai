# `backend/` status

> Updated by the track owner after every batch. Clients read this file for the base URLs. Write only what was run and observed.

## Batches

| # | Batch | Status | Date / commit | Notes |
|---|---|---|---|---|
| 01 | Skeleton and full API on memory + fake AI | PARTIAL | 2026-11-14 | Tasks 01.1–01.3 done; 01.4–01.8 next (AI-01 now on `main`). See below. |
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
| Owner's laptop on the LAN | — | — | — | — |
| Production (Railway) | — | — | — | — |
| Emergency laptop (hotspot) | — | — | — | — |

The demo key is shared privately, never written here.

## Contract conformance

| Endpoint group | Implemented | Tested | Notes |
|---|---|---|---|
| `/health` | yes | yes | Returns `ai_mode: "fake"` with AI-01 installed. Without `ghostchef_ai` it would say `unavailable` (not a contract value; broken setup only) |
| Recipes and steps (§2) | — | — | |
| `/check`, `/watch` (§3) | — | — | |
| Sessions, events, monitor (§4) | — | — | |
| `/live-token` (§5) | — | — | |

## Last smoke run

| Date | Target | Result | check p50 / max ms | watch p50 / max ms |
|---|---|---|---|---|
| — | — | — | — | — |

## Accounts (who holds them; no secrets here)

| Service | Project name | Owner | Region / plan |
|---|---|---|---|
| Supabase | — | — | — |
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

## BE-01 progress (2026-11-14)

Done and verified (`ruff check .` clean, `pytest -q`: 29 passed, with `ghostchef_ai` from AI-01 `815f2a2` installed):

- 01.1 scaffold: `pyproject.toml`, `.env.example`, `app/config.py`. `pip install -e ".[dev]"` works; `pip install -e ../ai` works since AI-01.
- 01.2 `create_app()`, CORS, `X-Demo-Key` auth (`hmac.compare_digest`), error envelope for `ApiError` / 404 / 422 / 500, `GET /health`. AI-error → HTTP handlers are registered automatically once `ghostchef_ai` is importable.
- 01.3 `Store` protocol, `MemoryStore` (rows in dicts, blobs under `DATA_DIR`), `/local-files` and `/local-upload` (memory mode only; path traversal rejected, single-use token, 413 past `MAX_VIDEO_MB`). Startup seed (`app/seed.py`): fixture recipe as `published` with fixed id `00000000-0000-4000-8000-000000000001`, `uuid5` step ids, reference images copied into `media`; its test passes against the AI-01 fixture.
- `GET /health` with AI-01 installed returned `{"status":"ok","contract_version":"2.0","ai_mode":"fake","storage":"memory"}`.

Not started: 01.4–01.8 (recipes/steps, check/watch, sessions, live token, upload flow, smoke script, `openapi.json`). The LAN URL is not shared yet.

## Needs from other tracks

- —
