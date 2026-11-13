# Track: `backend/` — API, storage, media, deployment, integration

You own the FastAPI service every client talks to, the database and file storage, ffmpeg, deployment, and the end-to-end smoke test. You are also the **integration hub**: when two tracks disagree about an interface, [../docs/API-CONTRACT.md](../docs/API-CONTRACT.md) decides and you implement it. This is the heaviest track by design.

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
    store/
      base.py        Store protocol + record types
      memory.py      MemoryStore (+ local files under DATA_DIR)
      supabase_store.py   SupabaseStore                               (BE-02)
    media/
      images.py      JPEG validation and downscaling                   (BE-03)
      ffmpeg.py      probe, still, clip                                (BE-06)
    jobs/ingest.py   background ingestion job                          (BE-06)
  migrations/001_init.sql                                              (BE-02)
  scripts/seed.py  scripts/smoke.py
  tests/
```

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
| `MAX_VIDEO_MB` | `500` | Upload limit |
| `CORS_ORIGINS` | `*` | Comma-separated origins; restrict in production |
| `WEB_DIR` | `../web` | Static web app, mounted at `/app/` when the directory exists |
| `PUBLIC_BASE_URL` | derived from the request | Used to build local file URLs in memory mode |

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
