# Track: `backend/` — API, storage, media, deployment, integration

**Owner: Stelios**

You own the FastAPI service every client talks to, the database and file storage, ffmpeg, deployment, and the end-to-end smoke test. You are also the **integration hub**: when two tracks disagree about an interface, [../docs/API-CONTRACT.md](../docs/API-CONTRACT.md) decides and you implement it. After `ios/`, this is the largest track.

New here? Read [../README.md](../README.md), then the whole of [../docs/API-CONTRACT.md](../docs/API-CONTRACT.md), then this file.

## What you deliver

| Deliverable | Consumer |
|---|---|
| Every endpoint in API-CONTRACT §2–§5, exactly as specified | `ios/`, `web/` |
| A server reachable on the LAN from the first hours (memory store + fake AI) | `ios/`, `web/` |
| Supabase schema, private buckets, seed of the demo recipe | everyone |
| A deployed HTTPS URL | the demo |
| `scripts/smoke.py` — one command that exercises the whole API and prints latency | everyone, after every push |
| An emergency way to run the same server from a laptop on a hotspot | the demo |

You do **not** write prompts or call Gemini directly: that is the `ghostchef_ai` package in `ai/`, which you import. You do not write client UI: `web/` is served by you as static files but owned by its track.

## Setup

Requires Python 3.11+, and `ffmpeg` + `ffprobe` on the PATH from BE-06 onward (`winget install ffmpeg`, `brew install ffmpeg`, `apt install ffmpeg`).

```bash
cd backend
python -m venv .venv
source .venv/bin/activate            # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -e ../ai                 # the ghostchef_ai package (needs AI-01 on main)
pip install -e ".[dev]"
cp .env.example .env
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

`--host 0.0.0.0` matters: the iPhone and the other laptops reach you over the LAN. Find your address with `ipconfig` (Windows) or `ipconfig getifaddr en0` (macOS) and post `http://<ip>:8000` in the team chat. On Windows, allow Python through the firewall for private networks when prompted.

These commands work after BE-01 has created `pyproject.toml` and `.env.example`.

## Target layout

```
backend/
  pyproject.toml   .env.example   Dockerfile   Dockerfile.dockerignore   railway.json
  README.md  STATUS.md
  app/
    main.py          create_app(): routers, CORS, error handlers, static mount of ../web
    config.py        Settings (pydantic-settings), one place for every env var
    auth.py          X-Demo-Key dependency
    errors.py        ApiError, the error envelope, AIError → HTTP mapping
    schemas.py       request / response models (API-CONTRACT §2–§5)
    deps.py          get_store(), get_settings()
    metrics.py       per-session latency ring buffers
    routers/         health.py recipes.py steps.py check.py watch.py sessions.py live.py
                     local.py (memory mode only: /local-files, /local-upload)
    store/
      base.py        Store protocol + record types
      memory.py      MemoryStore (+ local files under DATA_DIR)
      supabase_store.py   SupabaseStore                               (BE-02)
    media/
      images.py      JPEG validation and downscaling                   (BE-03)
      ffmpeg.py      probe, still, clip (asyncio subprocess)           (BE-06)
      videocache.py  10-minute local copy of a source video for re-picks (BE-06)
    jobs/ingest.py   ingestion job: download, probe, Gemini, stills, clips (BE-06)
  migrations/001_init.sql                                              (BE-02)
  scripts/seed.py  scripts/smoke.py
  tests/
```

### Ingestion (BE-06)

`POST /recipes/{id}/process` starts one background job (one at a time; the others wait as `processing`): download `videos/<id>/source.mp4` in chunks (`video larger than <N> MB` past `MAX_VIDEO_MB`), `ffprobe` it (`not a readable MP4`), call `extract_recipe`, clamp timestamps and clip windows into the video's duration, then ffmpeg cuts a 1280-px JPEG still (`media/<id>/steps/<idx>/ref.jpg`) and an optional 720-px clip of at most 6 s (`clip.mp4`) per step. Stills and clips are never upscaled. A failed still leaves the step without a reference image (publish answers `409` until the chef re-picks the frame); a failed clip is skipped. On startup, `processing` recipes older than 15 minutes become `failed` and `uploading` ones older than 2 hours become `failed` (also checked on every `GET /recipes`).

`PATCH /steps/{id}` with a changed `timestamp_s` re-extracts the still from the source video (cached on local disk for 10 minutes, at most 2 videos), allowed in `review` and `published`. A recipe with no source video (the seeded demo) just stores the value. `timestamp_s` beyond the video's end is `422`. `DELETE /recipes/{id}` on the seeded demo recipe is `409` unless `?force=true`.

`/health` gains `"ffmpeg": true|false`. Tests that need ffmpeg generate a `testsrc` video and are skipped when it is not installed.

## Configuration

Every variable is read in `app/config.py` and listed in `.env.example`.

| Variable | Default | Meaning |
|---|---|---|
| `DEMO_API_KEY` | `dev-key` | Value clients send in `X-Demo-Key`. Use a long random string in production |
| `STORAGE` | `memory` | `memory` or `supabase` |
| `DATA_DIR` | `.data` | Local file root for the memory store |
| `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` | — | Required when `STORAGE=supabase` |
| `GHOSTCHEF_AI_FAKE` | `1` | `1` = fake AI, `0` = real Gemini (read by `ghostchef_ai`) |
| `GEMINI_API_KEY` | — | Required when fake is off (read by `ghostchef_ai`) |
| `CHECK_BUDGET_S` / `WATCH_BUDGET_S` | `8` / `3.5` | Model time budgets from the contract |
| `SIGNED_URL_TTL_S` | `7200` | Signed URL lifetime |
| `MAX_VIDEO_MB` | `500` | Video size limit, enforced by the ingestion job while it downloads the video in chunks (and by the memory-mode upload route); the `videos` bucket carries the same limit |
| `CORS_ORIGINS` | `*` | Comma-separated origins; restrict in production |
| `WEB_DIR` | `../web` | Static web app, mounted at `/app/` when the directory exists |
| `PUBLIC_BASE_URL` | derived from the request | Used to build local file URLs in memory mode |
| `FAULT_INJECT` | empty | `timeout`, `quota` or `unavailable`: the failure to rehearse (see below). Anything else fails at startup |
| `FAULT_INJECT_ENABLED` | empty | Must be exactly `1` for fault injection to do anything. **Never set in production for the demo** |

### Startup refusals

The server refuses to start (`check_deploy_settings`) with `DEMO_API_KEY` unset or `dev-key` on Railway, and also with `STORAGE=supabase` and the real AI (`GHOSTCHEF_AI_FAKE=0`) anywhere.

### Quota cool-down (BE-07.2)

When the model answers `/watch` with a quota error, the process stops calling the model for `/watch` for 10 s: every `/watch` in that window answers `429 quota_exhausted` (`retryable: true`, the client's `request_id`) immediately, with `"cooldown": true` in its call log line. The check runs after `request_id` / `step_id` parsing (so a malformed request still gets `422`) and before the in-flight claim, the frame and the model. Only a quota error from `/watch` starts it; `/check` is never blocked by it and a quota error from `/check` does not start it. The state is per process (one worker), kept in `app/faults.py` (`WATCH_COOLDOWN_S`).

### Rehearsing failures (fault injection)

With `FAULT_INJECT=timeout|quota|unavailable` **and** `FAULT_INJECT_ENABLED=1`, a `/check`, `/watch` or `/live-token` request that carries the header `X-Fault: 1` fails with that error instead of calling the model: `504 model_timeout`, `429 quota_exhausted` (on `/watch` this also starts the cool-down) or `503 model_unavailable`. Requests without the header are untouched. Without `FAULT_INJECT_ENABLED=1` the header is ignored. The server logs a WARNING at startup when it is enabled. `X-Fault` is in the CORS allowed headers so the web app can send it. It is deliberately **not** blocked on Railway (the recovery tests in BE-07.4 are run against the deployed server): switch it on for the test, remove both variables afterwards, and never during the demo.

```bash
FAULT_INJECT=quota FAULT_INJECT_ENABLED=1 uvicorn app.main:app
curl -H 'X-Demo-Key: dev-key' -H 'X-Fault: 1' -F step_id=... -F request_id=$(uuidgen) -F frame=@f.jpg localhost:8000/watch
```

## Scripts

| Script | Purpose |
|---|---|
| `scripts/seed.py` | Seed the demo recipe (see above) |
| `scripts/smoke.py` | End-to-end smoke test of every endpoint |
| `scripts/load_watch.py` | Watcher-cadence load check (BE-07.1): `--sessions 2 --minutes 3 --frame x.jpg`. Per session: a `/watch` on a fixed 2.5 s grid (a tick is skipped and counted if the previous `/watch` of that session is still running), a `/check` every 20 s, then `session_end`. Prints status counts, error codes, p50 / p90 / max client latency, 429s and skipped ticks; exits 1 on any 5xx or transport error. It sends real frames: against production with real Gemini it spends quota, run it once and not right before the demo |
| `scripts/cleanup.py` | Data hygiene (BE-07.5): `--hours 6` (default), dry run unless `--yes`. Deletes sessions older than N hours with their events and `frames/<session>/` blobs, and `failed` recipes (blobs first). Never deletes the seeded recipe; its old sessions are cleaned. With `STORAGE=supabase` it works on the real project (put the service key in `backend/.env`). With `STORAGE=memory` the rows live only inside the running server, so the script can only remove stale `DATA_DIR/frames/<session>` folders and says so |

## Docker image

The image needs `backend/`, `ai/` and `web/`, so the **build context is the repository root**:

```bash
docker build -f backend/Dockerfile -t ghostchef-backend .                 # from the repo root
docker run -p 8000:8000 -e DEMO_API_KEY=dev-key ghostchef-backend         # memory + fake AI
```

`python:3.12-slim` + `ffmpeg`, runs as a non-root user with **one** uvicorn worker (session state is in process memory, so never scale it out), listens on `$PORT` (default 8000). Inside the image: `GHOSTCHEF_FIXTURE_DIR=/srv/ai/fixtures`, `WEB_DIR=/srv/web`, `DATA_DIR=/srv/data`. `backend/Dockerfile.dockerignore` keeps `.env`, `.venv`, `.git`, `ios/`, footage and `backend/.data` out of a local build context; the Dockerfile also copies only the backend paths it needs.

## Deploying (Railway)

**Note on `railway.json`.** Railway now calls config-as-code files deprecated. Its docs (read 2026-11-14) say they keep working only for *legacy* services, and only until **2026-12-01**. A service created today may ignore `backend/railway.json`, so step 2 sets the same values in the dashboard as well. Setting them in both places does no harm.

1. **Create the service.** In Railway: New Project → Deploy from GitHub repo → this repository, branch `main`.
   - Root directory: leave empty, so the repository root is used. The image needs `ai/` and `web/`.
   - Settings → Config-as-code / Railway config file: `backend/railway.json`, if the field is offered.
2. **Set the build and deploy settings in the dashboard.** These match `railway.json`.
   - Variable `RAILWAY_DOCKERFILE_PATH=backend/Dockerfile`. This is Railway's documented way to use a Dockerfile that is not at the root.
   - Settings → Deploy:
     - Healthcheck path `/health`
     - Healthcheck timeout 120
     - Restart policy "On failure", max retries 10
   - Leave the start command empty. The Dockerfile's `CMD` starts uvicorn on `$PORT`.
3. **Set the variables** (Variables tab). Never commit them.

   | Variable | Value |
   |---|---|
   | `DEMO_API_KEY` | required: the server refuses to start on Railway with an empty key or `dev-key`. A new long random string: `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
   | `STORAGE` | `supabase` |
   | `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` | from the Supabase project (service role key) |
   | `GHOSTCHEF_AI_FAKE` | `0` |
   | `GEMINI_API_KEY` | the event key |
   | `GHOSTCHEF_MODEL_VIDEO` / `_CHECK` / `_WATCH` / `_LIVE` | from `ai/STATUS.md` → "Gemini account facts". On 2026-11-14 these were `gemini-3.5-flash` / `gemini-3.5-flash-lite` / `gemini-3.5-flash-lite` / `gemini-3.8-live`. Re-check before you deploy |
   | `CORS_ORIGINS` | `https://<your-domain>.up.railway.app,http://localhost:5173` (fill in after step 4) |
   | `RAILWAY_DOCKERFILE_PATH` | `backend/Dockerfile` (step 2) |

4. **Get a public URL.** Settings → Networking → Generate Domain. If Railway asks for a target port, enter the port the app logs. It listens on Railway's `PORT`, so normally you accept the default. Then go back and finish `CORS_ORIGINS`.
5. **Keep it at one replica.** Settings → Deploy → Replicas = 1, and no multi-region setup.
6. **Deploy and watch the build log.** The build should print that it uses `backend/Dockerfile`. If it says Railpack instead, `RAILWAY_DOCKERFILE_PATH` was not picked up, so fix it and redeploy. Then verify:

   ```bash
   curl https://<domain>/health        # expect "ai_mode":"gemini","storage":"supabase"
   python scripts/smoke.py --base https://<domain> --key <demo key> --frame <real frame.jpg>
   ```

   Then open `https://<domain>/app/` on a phone.
7. **Share the URL and the new demo key privately** with the team, never in the repo. Record the URL and the smoke run in `STATUS.md`.

Supabase needs no seeding for production if `scripts/seed.py --publish --replace` has already run against the same project (BE-02). Run it again whenever AI announces a new fixture.

### Keeping production current

Production deploys are **manual** (decided in BE-04.5, see `STATUS.md`). After step 1, turn off automatic deploys for `main` in the service settings ("Disable"). To release:

1. Run `pytest -q` and the local smoke script on the commit.
2. In the Railway dashboard, press `Cmd/Ctrl + K` → **Deploy Latest Commit**.
3. Run `curl /health` and the smoke script against production.

If a deploy breaks, use Railway's redeploy on the previous deployment to roll back.

## Emergency mode (laptop on a phone hotspot)

Use this when the venue Wi-Fi or Railway fails. It runs the same server on a laptop, with `STORAGE=memory`, real Gemini, and the fixture recipe seeded at startup.

```bash
backend/scripts/emergency.sh            # macOS / Linux   (--fake to rehearse without Gemini)
backend\scripts\emergency.ps1           # Windows         (-Fake, -Port 8001)
```

**Before you run it**, check the laptop is ready:
- The backend venv is set up, as in [Setup](#setup).
- `backend/.env` holds `GEMINI_API_KEY` and a private `DEMO_API_KEY`. With real Gemini the script refuses the public default `dev-key`. The `GHOSTCHEF_MODEL_*` values are optional.
- Values in `.env` are plain `KEY=value` lines. Quotes and trailing ` # comments` are handled.

**What the script does:**
- Binds to `0.0.0.0:8000`.
- Prints the laptop's LAN addresses (`http://<ip>:8000`). Type one of them into the app's server setting, with the same demo key.
- Never prints a key.

**Steps:**
1. Turn on the phone's hotspot.
2. Join it from the laptop.
3. Run the script.
4. Point the app at the printed address.
5. Run one check.

**Limits:**
- **Plain HTTP on a LAN address.** Browsers allow the camera only on HTTPS or `localhost`. The web simulator's camera therefore works only on the laptop itself (`http://localhost:8000/app/`), not from a phone or another laptop. Photo upload still works.
- **The iOS app** needs local-network permission and an App Transport Security exception to reach an `http://` address (task IOS-01.2, iOS owner).
- **Memory store.** Recipes recorded in production are not here, only the seeded fixture recipe. Everything is lost when the process stops.
- On Windows, allow Python through the firewall for private networks.

## Batches

Run in order. One Claude session per batch. Kickoff prompt: [../docs/PLAN.md §7](../docs/PLAN.md#7-working-with-claude-on-each-laptop).

| # | Batch | Gate | Needs | Unblocks | A human must |
|---|---|---|---|---|---|
| 01 | [Skeleton and full API on memory + fake AI](tasks/01-skeleton-and-mock-api.md) | G0 | AI-01 | IOS-01, WEB-01, everything | Share the LAN URL |
| 02 | [Supabase schema, storage, seed](tasks/02-supabase-data-and-seed.md) | G1→G2 | 01 | 04 | Create the Supabase project |
| 03 | [Check and watch, production-grade](tasks/03-check-and-watch.md) | G1 | 01, AI-04 | G1, IOS-03/04 | — |
| 04 | [Deploy to Railway + emergency mode](tasks/04-deploy-railway.md) | G2 | 02, 03 | The demo, AI-07.5 | Create the Railway project, set secrets |
| 05 | [Live token, monitor, session summary](tasks/05-live-token-and-monitor.md) | G2→G3 | 01, AI-05 | IOS-05, WEB-03 | — |
| 06 | [Ingestion pipeline with ffmpeg](tasks/06-ingestion-pipeline.md) | G3 | 02, AI-06 | WEB-02 | — |
| 07 | [Hardening and end-to-end](tasks/07-hardening-and-e2e.md) | G4 | all above | Demo readiness | Run the recovery tests |

G1 only needs one thing from you beyond BE-01: run with `GHOSTCHEF_AI_FAKE=0` as soon as AI-04 is on `main`.

## Rules for this track

- **The contract is the spec.** Field names, status codes, and error codes come from API-CONTRACT. If something is missing or wrong there, change the contract through its §9 protocol first, then the code.
- **Both stores always work.** `STORAGE=memory` is the test default and the emergency fallback; never let it rot.
- **Tests run with fake AI and the memory store**, need no network, and pass before every push: `pytest -q`.
- **Run the smoke script after every push** against whatever the clients are using: `python scripts/smoke.py --base http://localhost:8000 --key dev-key`.
- **Secrets** live in `.env` (untracked) and in Railway's variables. Never log a key, a token, or a signed URL's signature.
- **Measure, don't guess.** `latency_ms` is measured around the AI call with a monotonic clock and reported in every response.
- Do not edit `ai/` or `web/`. If `ghostchef_ai` misbehaves, write it in [STATUS.md](STATUS.md) under "Needs from other tracks" and tell the AI owner.
- Deploying, creating cloud projects, and setting secrets are done by **you, the human owner**, in the provider's dashboard or CLI. Claude prepares the files and tells you the exact steps.
