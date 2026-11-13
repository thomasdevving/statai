# `backend/` status

> Updated by the track owner after every batch. Clients read this file for the base URLs. Write only what was run and observed.

## Batches

| # | Batch | Status | Date / commit | Notes |
|---|---|---|---|---|
| 01 | Skeleton and full API on memory + fake AI | DONE (fake) | 2026-11-14 | Every §2–§5 endpoint on the memory store + fake AI (AI-01 `815f2a2`). See below. |
| 02 | Supabase schema, storage, seed | DONE (fake) | 2026-11-14 | `STORAGE=supabase` works: migration applied, `SupabaseStore`, `scripts/seed.py`, smoke exit 0 against Supabase. AI still fake. See BE-02 notes. |
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
| Owner's laptop, Supabase store (local test only) | `http://localhost:8001` (started for BE-02 verification, then stopped) | `fake` | `supabase` | 2026-11-14 |
| Production (Railway) | — | — | — | — |
| Emergency laptop (hotspot) | — | — | — | — |

The demo key is shared privately, never written here.

## Contract conformance

| Endpoint group | Implemented | Tested | Notes |
|---|---|---|---|
| `/health` | yes | yes | Without `ghostchef_ai` installed `ai_mode` would be `unavailable` (not a contract value; broken setup only) |
| Recipes and steps (§2) | yes | yes | Supabase mode: signed upload URL + `resumable_endpoint` (`https://trfaijfrgfyrjvhocqif.storage.supabase.co/storage/v1/upload/resumable`); a simple `PUT` to it was run and worked (TUS not tested). `/process` in Supabase mode marks the recipe `failed` until BE-06 downloads the video. Memory mode: upload via `PUT /local-upload` (`resumable_endpoint: null`). `/process` uses fixture images as reference stills (no ffmpeg until BE-06); a changed `timestamp_s` is stored but not re-extracted. Publishing an already-published recipe returns 200 |
| `/check`, `/watch` (§3) | yes | yes | No JPEG validation / size limits / in-flight guard yet (BE-03); hard 8 MB read cap |
| Sessions, events, monitor (§4) | yes | yes | `steps_passed_first_try` ignores `check_unsure` (not a verdict). Monitor's last frame / result / latency are in-process memory |
| `/live-token` (§5) | yes | yes | Fake token (`locked: false`) |

## Last smoke run

| Date | Target | Result | check p50 / max ms | watch p50 / max ms |
|---|---|---|---|---|
| 2026-11-14 | `http://localhost:8000` (fake, memory) | exit 0, every status as expected | 751 / 751 (n=2) | 301 / 301 (n=6) |
| 2026-11-14 | `http://localhost:8001` (fake, **supabase**) | exit 0, all 6 signed ref-image URLs returned 200 `image/jpeg` | 751 / 751 (n=2) | 300 / 301 (n=6) |

Fake-mode latencies: they measure `GHOSTCHEF_AI_FAKE_DELAY` (0.3 s default), not Gemini.

## Accounts (who holds them; no secrets here)

| Service | Project name | Owner | Region / plan |
|---|---|---|---|
| Supabase | Echo (`trfaijfrgfyrjvhocqif`) | Stelios | eu-north-1, created 2026-11-14; `migrations/001_init.sql` applied 2026-11-14 |
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

## BE-02 notes (2026-11-14)

Verified in this session, every item run and seen:
- **Migration** `migrations/001_init.sql` applied to `trfaijfrgfyrjvhocqif` (through the Supabase MCP rather than the SQL editor; same SQL). Result: 4 tables, RLS on for all of them with no policies; buckets `videos` (private, 524288000 bytes, `{video/mp4}`), `media` and `frames` (private).
- **Anon check** with the project's publishable key: `GET rest/v1/recipes?select=*` → `200 []`. `POST rest/v1/recipes` → `401` (`42501 new row violates row-level security policy`). Storage `list` on `media` → `200 []`. The Supabase security advisor reports only "RLS enabled, no policy" (INFO) ×4, which is intended (contract §6).
- `pytest -q` → 71 passed, 3 skipped (the skips are the opt-in Supabase tests). `ruff check .` clean.
- `RUN_SUPABASE_TESTS=1 pytest -q tests/test_supabase_integration.py` → 3 passed: CRUD with cascade, the blob round trip and the signed-URL fetch, and a signed upload (`PUT` of a small MP4 → `blob_exists` true; a `text/plain` upload is refused by the bucket). Each run cleans up after itself.
- `STORAGE=supabase python scripts/seed.py --publish --replace` succeeded twice in a row. Without `--replace` it exits 1. It uses the same recipe id and step ids as the memory seed.
- A server with `STORAGE=supabase` ran on `:8001` (`:8000` was busy with the owner's memory server). `/health` → `storage: supabase`. Smoke exit 0. Afterwards the tables held 1 recipe, 6 steps, 1 session and 7 events; the `frames` bucket held 8 frames and `media` held 6 stills.
- **API flow checked on Supabase:**
  - `POST /recipes` returns a signed upload URL.
  - `/process` before the upload → `409 upload_missing`.
  - `PUT` to the URL → `200`.
  - `/process` → `202`, and the recipe then ends as `failed`. This is expected until BE-06.
  - `DELETE` → `204`, and a `GET` afterwards → `404`.

- **Security review** (security-tester): two low findings, both fixed and re-verified with a clean pass.
  - `signed_url` on a missing object now returns null instead of a 500.
  - `purge_recipe` now deletes blobs before rows.
  - The HTTP/2 thread-safety fix was also checked, including 40 concurrent calls with no errors.

Design notes:
- **`SupabaseStore`** (`app/store/supabase_store.py`):
  - Uses the sync supabase-py 2.34.1 client through `asyncio.to_thread`.
  - Gives the client its own HTTP/1.1 `httpx.Client`. supabase-py's default HTTP/2 connection failed under concurrent threaded calls (`RemoteProtocolError`, seen here).
  - Supabase errors become `500 internal`. Log lines carry the error type and code with tokens redacted, never the key.
- **Signed URLs** are cached in memory for half their TTL. A missing object yields `null` rather than a 500.
- **Signed upload URLs** last 2 hours (Supabase docs, checked 2026-11-14; the API has no expiry parameter).
- **`replace_steps`** deletes and then inserts, so it is not one transaction.
- **An event with an unknown `step_id`** is stored with `step_id = null`.
- **Deleting a recipe** (route and seed `--replace`) goes through `app/store/ops.purge_recipe`: blobs first, then rows (cascade), so a failed Storage call can be retried.
- **Memory mode** keeps its startup seed. Supabase mode is seeded only by `scripts/seed.py`.
- **Re-seeding:** run `STORAGE=supabase python scripts/seed.py --publish --replace` again whenever AI announces a new fixture (real stills after AI-03.5).

Not verified / known limits:
- TUS resumable upload is untested; only the simple `PUT` was run.
- On the free plan the global upload limit may be below the bucket's 500 MB. A large-video upload has not been tried.
- **Signed URLs in a browser:** the smoke script and the tests fetched them with httpx (200 `image/jpeg`). They were not opened in a browser by hand.
- **Rows in the table editor:** rows and frames were confirmed by SQL counts, not looked at in the dashboard UI.

## Needs from other tracks

- —
