# `backend/` status

> Updated by the track owner after every batch. Clients read this file for the base URLs. Write only what was run and observed.

## Batches

| # | Batch | Status | Date / commit | Notes |
|---|---|---|---|---|
| 01 | Skeleton and full API on memory + fake AI | NOT STARTED | | |
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
| `/health` | — | — | |
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

## Needs from other tracks

- —
