# `backend/` status

> Updated by the track owner after every batch. Clients read this file for the base URLs. Write only what was run and observed.

## Batches

| # | Batch | Status | Date / commit | Notes |
|---|---|---|---|---|
| 01 | Skeleton and full API on memory + fake AI | DONE (fake) | 2026-11-14 | Every §2–§5 endpoint on the memory store + fake AI (AI-01 `815f2a2`). See below. |
| 02 | Supabase schema, storage, seed | DONE (fake) | 2026-11-14 | `STORAGE=supabase` works: migration applied, `SupabaseStore`, `scripts/seed.py`, smoke exit 0 against Supabase. AI still fake. See BE-02 notes. |
| 03 | Check and watch, production-grade | DONE | 2026-11-14 | Real Gemini through `/check` and `/watch` (AI-04 `429b19a`). JPEG validation + downscale, ref-image cache, budgets, `/watch` in-flight guard, background frame/event persistence, latest-frame route, JSON call logs. Real-photo verdicts were checked by reading them only: no labelled mistake frame exists yet (AI-03). See BE-03 notes. |
| 04 | Deploy to Railway + emergency mode | DONE | 2026-11-14 / `b72ce2d` | Production runs on Railway with `gemini` + `supabase`; smoke against production passed. Emergency laptop mode is **NOT REHEARSED** on a hotspot. Automatic deploys are off (owner). See BE-04 notes. |
| 05 | Live token, monitor, session summary | PARTIAL | 2026-11-14 / `ab84dc8` | Monitor, sessions list, summary, smoke: done and tested (fake, memory). `/live-token` handler is real (409, config cache, 3 s guard, safe logging) but **no real token yet**: AI-05 is not on `main`, so with real AI it returns 503. Deployed to production (`c151ee6`), production smoke exit 0 (with `--allow-live-errors`). See BE-05 notes. |
| 06 | Ingestion pipeline with ffmpeg | NOT STARTED | | |
| 07 | Hardening and end-to-end | NOT STARTED | | |

Status words: `DONE`, `DONE (fake)`, `PARTIAL`, `BLOCKED`, `NOT STARTED` (defined in docs/PLAN.md §8).

## Where the API is

| Environment | Base URL | `ai_mode` | `storage` | Since |
|---|---|---|---|---|
| Owner's laptop on the LAN | `http://192.168.200.152:8000` (when the owner runs it; IP may change) | `fake` | `memory` | 2026-11-14 |
| Owner's laptop, Supabase store (local test only) | `http://localhost:8001` (started for BE-02 verification, then stopped) | `fake` | `supabase` | 2026-11-14 |
| Production (Railway) | `https://statai-production.up.railway.app` | `gemini` | `supabase` | 2026-11-14 |
| Emergency laptop (hotspot) | `scripts/emergency.sh` prints `http://<lan-ip>:8000`. **NOT REHEARSED** on a hotspot with a phone | `gemini` | `memory` | — |

The demo key is shared privately, never written here.

## Contract conformance

| Endpoint group | Implemented | Tested | Notes |
|---|---|---|---|
| `/health` | yes | yes | Without `ghostchef_ai` installed `ai_mode` would be `unavailable` (not a contract value; broken setup only) |
| Recipes and steps (§2) | yes | yes | Supabase mode: signed upload URL + `resumable_endpoint` (`https://trfaijfrgfyrjvhocqif.storage.supabase.co/storage/v1/upload/resumable`); a simple `PUT` to it was run and worked (TUS not tested). `/process` in Supabase mode marks the recipe `failed` until BE-06 downloads the video. Memory mode: upload via `PUT /local-upload` (`resumable_endpoint: null`). `/process` uses fixture images as reference stills (no ffmpeg until BE-06); a changed `timestamp_s` is stored but not re-extracted. Publishing an already-published recipe returns 200 |
| `/check`, `/watch` (§3) | yes | yes | BE-03 complete: 413/415/422 validation, downscaling, 504 budget, `/watch` one in flight per session → 429. Guard-level 401/413 and framework-level 422s carry `request_id: null` (the body is not parsed yet at that point) |
| Sessions, events, monitor (§4) | yes | yes | BE-05: `active=true` = unfinished **and** started in the last 3 h. `session_end` is idempotent (a repeat returns the first event id). `steps_passed_first_try` ignores `check_unsure`. The monitor's last frame, result and latency live in process memory and are lost on restart. Session, title and steps are cached for 3 s |
| `/live-token` (§5) | yes | yes (fake) | Unpublished recipe → `409 recipe_not_ready`. One token per `session_id` every 3 s → `429 quota_exhausted` (retryable); a failed mint does not hold the window. The config is cached per recipe + content hash; the token is never cached. Real token: **blocked on AI-05** (503) |

## Last smoke run

| Date | Target | Result | check p50 / max ms | watch p50 / max ms |
|---|---|---|---|---|
| 2026-11-14 | `http://localhost:8000` (fake, memory) | exit 0, every status as expected | 751 / 751 (n=2) | 301 / 301 (n=6) |
| 2026-11-14 | `http://localhost:8001` (fake, **supabase**) | exit 0, all 6 signed ref-image URLs returned 200 `image/jpeg` | 751 / 751 (n=2) | 300 / 301 (n=6) |
| 2026-11-14 | `http://localhost:8000` (**gemini**, memory), real photo A, `--watch-n 10` | every check/watch 200; only failure `/live-token` 503 (AI-05 not done, see Needs) | 1724 / 2157 (n=2) | 800 / 928 (n=10) |
| 2026-11-14 | same, real photo B, `--watch-n 10` | as above | 1699 / 2080 (n=2) | 943 / 1472 (n=10) |
| 2026-11-14 | same, BE-03.7 run: photo A to check, B to watch, `--watch-n 36`, real 2.5 s spacing, 2 min 8 s | 38 calls, **0 errors**; `/live-token` 503 as above | 1170 / 1316 (n=2) | 900 / 1526 (n=36) |
| 2026-11-14 | same, after the review fixes, `--watch-n 4 --fast` | every check/watch 200 | 1775 / 2093 (n=2) | 1000 / 1110 (n=4) |
| 2026-11-14 | Docker image on `localhost:8010` (fake, memory), `--fast` | exit 0, every status as expected | 750 / 751 (n=2) | 300 / 301 (n=6) |
| 2026-11-14 | Docker image on `localhost:8011` with **production config** (`STORAGE=supabase`, `GHOSTCHEF_AI_FAKE=0`), default fixture frame, `--fast` | every check/watch 200; only failure `/live-token` 503 (AI-05, see Needs) | 1562 / 1969 (n=2) | 1000 / 1426 (n=6) |
| 2026-11-14 | `scripts/emergency.sh` on this laptop, reached via its LAN address `http://192.168.1.244:8020` from the same laptop (gemini, memory), `--fast` | every check/watch 200; `/live-token` 503 as above | 1662 / 1748 (n=2) | 932 / 1065 (n=6) |
| 2026-11-14 | `https://statai-production.up.railway.app` (**gemini, supabase**), default fixture frame `ai/fixtures/images/step-3.jpg`, `--watch-n 10` | every check/watch 200; only failure `/live-token` 503 (AI-05, see Needs) | 1217 / 1238 (n=2) | 712 / 868 (n=10) |
| 2026-11-14 | `http://localhost:8000` (fake, memory), BE-05 smoke (question, monitor follows step change, `last_frame_url` → 200 `image/jpeg`, double `session_end`), `--fast`, run after the review fixes | exit 0, every status as expected | 750 / 750 (n=2) | 301 / 301 (n=6) |
| 2026-11-14 | `https://statai-production.up.railway.app` (**gemini, supabase**), BE-05 code `c151ee6`, default fixture frame, `--watch-n 6 --fast --allow-live-errors` | exit 0. Every check/watch 200 (check `unsure` ×2, watch `ok` ×6). Monitor followed both step changes. `last_frame_url` → 200 `image/jpeg`. Repeated `session_end` returned the same id. Signed ref URLs 200. Only error: `/live-token` 503 `model_unavailable` (AI-05) | 1085 / 1287 (n=2) | 717 / 852 (n=6) |

Fake-mode latencies: they measure `GHOSTCHEF_AI_FAKE_DELAY` (0.3 s default), not Gemini.

## Accounts (who holds them; no secrets here)

| Service | Project name | Owner | Region / plan |
|---|---|---|---|
| Supabase | Echo (`trfaijfrgfyrjvhocqif`) | Stelios | eu-north-1, created 2026-11-14; `migrations/001_init.sql` applied 2026-11-14 |
| Railway | `gracious-miracle`, service `statai` | Stelios | EU West (`europe-west4-drams3a`), 1 replica, 2 vCPU / 1 GB limit; created 2026-11-14. A second, unused project `zestful-passion` (only failed deploys) also exists |

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

## BE-03 notes (2026-11-14)

Run in this session and seen:
- **Verification:** `ruff check .` is clean. `pytest -q` gives 108 passed, 3 skipped (fake AI, memory store, no network). 37 of the passing tests are new, in `tests/test_be03_check_watch.py`.
- **Real Gemini (BE-03.1):** `GHOSTCHEF_AI_FAKE=0`, `GET /health` → `ai_mode: gemini`. Models reported: `gemini-3.5-flash-lite` for both check and watch. The server ran on `127.0.0.1:8000` with the memory store. `.env` still says `GHOSTCHEF_AI_FAKE=1`; the real runs set the variable on the command line.
- **Frames used.** The AI owner has no dev frames: AI-03 is not filmed, and AI-04's private stock clip is not on this laptop. Two real photos from Wikimedia Commons were used instead. They are kept outside the repo and never committed.
  - **A:** "Roll sushi making.jpg", CC BY-SA 2.0. Hands rolling a maki with a bamboo mat, side view.
  - **B:** "Uramaki1.jpg", CC BY-SA 4.0. A plate of cut uramaki, top view.
  - Neither photo shows a labelled mistake, so these runs show that real verdicts flow through the API. They are **not** accuracy results.
- **Verdicts seen through `/check`:**

  | Photo | Step | Verdict | Headline |
  |---|---|---|---|
  | A | 5 "Roll" | `pass` | "Looks great" |
  | A | 3 "Spread rice" | `unsure` | "Can't see the rice" |
  | A | 1 "Place nori" | `fix`, then `pass` on the identical frame (later run: `pass`, `pass`) | — |
  | B | 6 "Slice" | `pass` | — |
  | B | 3 | `unsure` | "Show unfinished rice sheet" |
  | B | 1 | `unsure` ×2 | — |

  - Watch returned `ok` for all 60 real calls.
  - The verdict changing on an identical frame is the same instability `ai/STATUS.md` reports (R-02).
- **BE-03.7, two-minute run:** 38 calls (2 check, 36 watch), error counts by code: none. Check p50/max 1170/1316 ms. Watch p50/max 900/1526 ms. One JSON line per call appeared in the server log. Nothing surprising, so nothing to report to AI.
- **Live checks on the real server:**
  - A 404 KB watch photo was downscaled to a 36 KB, 512 px frame.
  - The monitor's `last_frame_url` loaded without `X-Demo-Key`: 200 `image/jpeg`, `Cache-Control: no-store`. Without the token it returned 404.
  - The uvicorn access log shows `?t=***`.

Design:
- **`app/media/images.py`:**
  - Each frame is opened and decoded once, in a thread.
  - Limits: check 1.5 MB / 1280 px; watch 1.5 MB hard, 200 KB soft (over the soft limit: downscaled with a warning) / 512 px; 16 MP pixel cap → 413. Not a JPEG or not decodable → 415. MPO (camera JPEG with depth data) is accepted.
  - Frames are re-encoded at quality 80 when the upright image is over the long edge, or when the frame carries **any EXIF**. Re-encoding bakes in the orientation and drops all metadata (EXIF, XMP, comments, ICC). Only a plain single-frame JPEG with no metadata and nothing after its end marker is passed through untouched.
  - The guard's frame body cap dropped from 8 MB to 2 MB.
- **`app/refcache.py`:**
  - LRU of 64 entries keyed by `(step_id, ref_image_path)`, with a 5 min TTL. The TTL covers `scripts/seed.py --replace` run from another process.
  - Invalidated on `PATCH /steps`, recipe delete or purge, the seed, and ingestion.
- **Budgets:**
  - `timeout_s` from settings goes to the package, plus `asyncio.wait_for(budget + 0.5 s)` around the AI call.
  - Decision: JPEG work, step/session loads and the ref fetch are **outside** the budget, as the task specifies. A cold Supabase ref fetch adds to the total.
- **`/watch` guard:** one call in flight per normalised `session_id`; a second gets `429 quota_exhausted`, `retryable: true`, "watch already in flight". The flag is cleared in `finally` on every path, including cancellation.
- **Frames and events:**
  - The latest frame per session is held in memory and served at `GET /sessions/{id}/latest-frame.jpg?t=<token>`. The random per-session token appears only in the monitor's `last_frame_url`.
  - Decision: the latest frame is updated as soon as the frame is validated, so the monitor also shows frames whose AI call failed.
  - Every check frame and warn-only watch frames go to the `frames` bucket, with the event recorded in a background task after the response. If storage fails, the event is kept without `frame_path`.
  - No event, stored frame or monitor result when the AI call fails or the client has disconnected.
- **Metrics:** ring buffers of 500 latencies per session; error counts by code process-wide (`metrics.errors_total`) and per session, but only for sessions that exist (a made-up `session_id` never creates an entry).
- **Logs (`app/logs.py`):**
  - The `ghostchef` loggers write JSON lines.
  - `ghostchef.calls` writes one line per call: endpoint, session_id, step_idx, request_id, verdict/status, mistake_id, confidence, latency_ms, model, http_status, error code.
  - No frame bytes, keys or tokens are logged.
- **Smoke script:** new `--watch-frame` and `--allow-model-errors` options, plus a table of error responses by code.

Not verified / known limits:
- Error counts are collected but not shown in the monitor response. Adding them changes the contract shape (see Needs).
- Not run against `STORAGE=supabase` with real AI in this batch; the store code paths are unchanged from BE-02.
- Not tried from another device on the LAN (the server was bound to `127.0.0.1`).

## BE-04 notes (2026-11-14)

Run in this session and seen:
- **BE-04.1 Dockerfile.**
  - From the repo root, `docker build -f backend/Dockerfile -t ghostchef-backend .` succeeded (Docker 29.9.3, image 680 MB).
  - `docker run -p 8010:8000 -e DEMO_API_KEY=dev-key ghostchef-backend`: `/health` → `ai_mode: fake`, `storage: memory`; `/app/` → 200; smoke exit 0.
  - Inside the container: process runs as uid 10001 (`app`); `ffmpeg` present; no `.env` file anywhere in the image; command line shows `--workers 1`; with `-e PORT=9123` it answered on 9123.
  - Same image with production-style variables (Supabase + real Gemini, keys passed from a temporary env file that was deleted afterwards): `/health` → `gemini` / `supabase`, smoke as in the table above.
- **BE-04.2.** `railway.json` is valid JSON with the fields from Railway's config-as-code reference (Dockerfile builder, `dockerfilePath`, healthcheck `/health`, `ON_FAILURE`). README → "Deploying (Railway)" has the dashboard steps.
  - **Caveat:** Railway's docs (read 2026-11-14) mark config-as-code as deprecated: it works for legacy services and only until 2026-12-01. The README therefore also has every setting entered in the dashboard, plus `RAILWAY_DOCKERFILE_PATH=backend/Dockerfile`.
  - Railway's successor is IaC (`.railway/railway.ts` at the repo root), which is outside `backend/` and needs a TypeScript SDK. Not done; not needed for the hackathon.
  - Railway only reads a `.dockerignore` at the build-context root; `backend/Dockerfile.dockerignore` applies to local BuildKit builds. Railway builds from git (no `.env`, `.venv` or `.data` there), and the Dockerfile copies only named backend paths, so nothing secret can reach the image either way.
- **BE-04.3 Deploy (2026-11-14), done through the Railway MCP:**
  - **What broke.** The first deploys crashed at startup with `SupabaseException: Invalid URL`: the `SUPABASE_URL` value had been entered wrongly in the dashboard. The values are redacted, so the exact typo is not known.
  - **The fix.** All variables were re-set from the owner's working `backend/.env`. The Dockerfile path, restart policy (on failure, 10 retries) and sleep off were also set on the service. The next deploy went healthy.
  - **The build** used `backend/Dockerfile`: the stack trace paths are `/srv/backend/app/...`. Railway's metadata still shows `builder: RAILPACK`, but the variable takes precedence.
  - **Checks run against the production URL:**
    - `curl /health` → `{"status":"ok","contract_version":"2.0","ai_mode":"gemini","storage":"supabase"}`.
    - `/app/` → 200. That was curl only; it has not been opened on a phone yet.
    - `/recipes` with no key → 401; with `dev-key` → 401.
    - Smoke: see the table above. The frame was the default fixture image, not a newly taken photo.
  - **The demo key** was generated in this session and is in `backend/.env` and the Railway variables. The owner shares it privately.
  - **Still open:**
    - Automatic deploys from `main`: turned off by the owner (confirmed 2026-11-14).
    - Delete the unused `zestful-passion` project, if the owner agrees.
- **BE-04.4 Emergency mode.** `scripts/emergency.sh` ran on this laptop: memory store, real Gemini, fixture seeded at startup, LAN address printed (container bridges filtered out). Smoke through the LAN address passed (table above). With no `GEMINI_API_KEY` anywhere it refuses to start (exit 1). `emergency.ps1` was written but **not run** (no Windows machine here).
  - Emergency laptop: **NOT REHEARSED**. No phone, no hotspot, and the app was not pointed at it.
- **BE-04.5 Decision: manual production deploys.** Automatic deploys on `main` are to be switched off. Four tracks push to `main`, and a broken push from any of them would break everyone's phone testing and the demo. Release = `pytest -q` + local smoke on the commit, then Railway → Cmd/Ctrl+K → "Deploy Latest Commit", then `/health` + smoke against production (README → "Keeping production current").
- **Security review** (security-tester): no high findings and no secret leakage. It confirmed the image contents, the non-root user, and that `--forwarded-allow-ips='*'` is harmless here (no decision depends on the client IP). Three findings were fixed:
  - **Fail-open default key.** The server now refuses to start on Railway (any `RAILWAY_ENVIRONMENT*` variable set) when `DEMO_API_KEY` is empty or `dev-key` (`app/main.py: check_deploy_settings`, tests in `tests/test_deploy_settings.py`). Checked in the container: with the default key, startup failed and uvicorn exited; with a real key, `/health` returned 200. The emergency scripts also refuse `dev-key` with real Gemini (bash run and seen: exit 1).
  - **`emergency.ps1` + `PUBLIC_BASE_URL`.** In PowerShell, assigning `""` deletes the variable, so the value in `.env` could win. The script now sets a single space, which the backend treats as unset.
  - **`.env` parsing in both scripts.** Inline ` # comments` are now stripped, and quoted values are taken from inside the quotes (bash checked on 5 cases).
  - The security-tester re-checked all three fixes: clean pass, no new findings.
- **Owner action:** the local `backend/.env` still has `DEMO_API_KEY=dev-key`, so `emergency.sh` will refuse to start until a private key is set there. That key must be the same one the apps are configured with.
- `ruff check .` clean; `pytest -q` 113 passed, 3 skipped.

To finish BE-04 (owner):
1. Follow README → "Deploying (Railway)".
2. `curl https://<domain>/health` should show `gemini` / `supabase`.
3. Run the smoke script with a real frame.
4. Open `/app/` on a phone.
5. Fill "Where the API is", "Last smoke run" and the Railway account row.
6. Rehearse emergency mode on a hotspot with the phone and fill its row.

## BE-05 notes (2026-11-14)

Run in this session and seen:
- **Verification:**
  - `ruff check .` is clean.
  - `pytest -q`: 143 passed, 3 skipped (fake AI, memory store).
  - 30 of the passing tests are new, in `tests/test_be05_live_monitor.py`.
  - Local smoke `--fast` (fake, memory): exit 0 (table above).
- **BE-05.1 `/live-token` (`app/routers/live.py`):**
  - Checks happen in this order: recipe, then session (404/422), then status `published` (else `409 recipe_not_ready`). Only then come the guard and the mint, so a 404/409/422 never uses up the 3 s window.
  - The config is cached in an LRU of 32. The key is recipe id + sha256 of title, chef, transcript, step specs and the live model id. One entry per recipe: a `PATCH /steps` changes the hash and replaces the entry. The token is never cached. Tests confirm 3 calls give 1 build and 3 mints.
  - The guard allows one token per `session_id` every 3 s; a faster repeat gets `429 quota_exhausted` with `retryable: true`. A failed mint (Gemini error or timeout) clears the stamp, so a retry is a real attempt. Calls without `session_id` are not limited, as the task specifies.
  - The log line `ghostchef.live` carries `recipe_id`, `model`, `locked` and `expires_at` only. The uvicorn log of the local run was checked: it does not contain the token string.
  - Fake mode returns the fake token (`locked: false`, model `fake`).
  - **With real AI** (`GHOSTCHEF_AI_FAKE=0`, local server on `:8001`): `503 model_unavailable`, "mint_live_token is not implemented yet". AI-05 is still NOT STARTED on `main`. So **no real `model` / `locked` value has been observed**, and the BE-05.1 real-AI acceptance is open.
- **BE-05.2 monitor:**
  - Tests cover the empty session, a step change (including an unknown `to_idx` falling back to step 1), an `ok` watch (in `last_result`, not in `events`), a `warn`, a check, the last 30 events newest first, and the state after a restart.
  - Session, recipe title and steps are cached for 3 s per session. A warm call makes exactly one store query (`list_events`); a test asserts this.
  - The cache is evicted on `session_end` and on recipe delete. A load that races an eviction is not cached.
  - **60-call loop against the local uvicorn** (memory store, 40 events): p50 3.6 ms, max 4.8 ms. After the review fixes: p50 4.9 ms, max 8.3 ms. The target was under ~50 ms.
- **BE-05.3:**
  - `active=true` is filtered in the router after the store's newest-first limit. That is correct because every in-window row is newer than every stale row. Both stores use tz-aware times.
  - The summary rules are in the `summarize` docstring, with a 5-case table test.
  - `session_end` is idempotent and keyed on the existing event. A retry after a failed `update_session` repairs `finished_at` instead of adding a second event (tested).
- **BE-05.4 smoke:**
  - It now posts a `question` event, checks that `current_step` follows two step changes, fetches `last_frame_url` without the key (it must be `image/jpeg`), prints the summary, and sends `session_end` twice (same id expected).
  - New flag `--allow-live-errors`: a 429/503/504 from `/live-token` is reported instead of failing, for a real-AI server before AI-05.
- **Security review** (security-tester): no high findings. Five were fixed:
  - Recipe delete now evicts the caches.
  - The monitor cache race with `session_end` is closed.
  - `session_end` idempotency no longer depends on `finished_at`.
  - A failed mint releases the guard.
  - The smoke script no longer crashes on a non-JSON `/live-token` body.
  - Not changed: no guard without `session_id` (that matches the spec).
  - Re-verification by security-tester: clean pass, no new findings.

Not done / not verified:
- **BE-05.5 not done.**
  - **Deployed 2026-11-14** through the Railway MCP. The MCP cannot do "Deploy Latest Commit", so the service source was **pinned to commit `c151ee6`** (`connect-service-source` with `commitSha`). This built and deployed immediately (deployment `e3ab9008`). A probe confirmed the new code was live: a repeated `session_end` returned the same event id. `/health` → `gemini` / `supabase`.
  - **Production smoke:** exit 0 (table above).
  - **Monitor on production:** 60 calls from this laptop gave p50 99 ms, max 248 ms. That is the round trip to EU West plus one Supabase query. The ~50 ms target was for the memory store, where it is met locally.
  - **Pinned source:** the service now follows commit `c151ee6`, not the `main` branch. To release later, pin the new commit the same way, or reconnect the source to `main` in the dashboard and then use Deploy Latest Commit. Pushes to `main` do not deploy either way (automatic deploys are off, done by the owner earlier).
  - The iOS and web owners have **not** been told yet.
- `STORAGE=supabase` was not run in this batch. The store code is unchanged; only router logic changed.

To finish BE-05 (owner):
1. When AI-05 is on `main`: deploy it and run the production smoke **without** `--allow-live-errors`. Record `model` / `locked`.
2. Tell web (WEB-03) that the monitor feed is complete. Tell iOS (IOS-05) that `/live-token` is wired, but the real token waits on AI-05.

## Needs from other tracks

- **AI (AI-05), still open after BE-05:** the backend handler is ready and only waits on `mint_live_token`. With `GHOSTCHEF_AI_FAKE=0`, `GET /live-token` returns `503 model_unavailable` ("mint_live_token is not implemented yet"). The fake switch is process-wide, so a backend running real check/watch has no working Live token until AI-05 lands. This affects anyone demoing voice against a real-AI backend.
- **AI (AI-03):** a few labelled dev frames, including at least one mistake, so that `/check` → `fix` with the right `mistake_id` can be shown end to end. BE-03 used two Commons photos without mistakes.
- **Docs (§9, additive, low priority):** proposal to add an optional `errors: {code: count}` to the `/sessions/{id}/monitor` response (BE-05 can expose the per-session counts BE-03 now collects). The backend owner must agree first.
- **iOS (IOS-01.2):** emergency mode serves plain `http://<lan-ip>:8000`. The app needs local-network permission and an App Transport Security exception for HTTP to reach it (see README → "Emergency mode").
