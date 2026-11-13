# BE-04 — Deploy to Railway, and the emergency laptop mode

| | |
|---|---|
| **Track** | `backend/` |
| **Gate** | G2 |
| **Depends on** | BE-02 (Supabase), BE-03.1 (real AI works locally) |
| **Unblocks** | Phone testing away from the laptop, the web simulator on phones (needs HTTPS for the camera), AI-07.5, the demo |
| **Size** | Small–medium |
| **Model** | Opus 5.5 for the Dockerfile; Sonnet 5.5 is enough for the README section |
| **Needs a human for** | Creating the Railway project, connecting the repository, setting secrets, pressing deploy |

## Goal

A public HTTPS URL serving the same code with Supabase and real Gemini, plus a rehearsed way to run the identical server from a laptop on a phone hotspot if the venue network or Railway fails.

## Read first

- [../README.md](../README.md) — configuration table
- [../../docs/ARCHITECTURE.md §4](../../docs/ARCHITECTURE.md#4-environments-and-configuration) — the four environments
- Current Railway documentation for Dockerfile deployments, config-as-code, and health checks

## Tasks

### BE-04.1 Dockerfile

The image needs code from three folders (`backend/`, `ai/`, `web/`), so **the build context is the repository root** while the Dockerfile lives in `backend/`.

**Do** — `backend/Dockerfile`:
- Base `python:3.12-slim`. Install `ffmpeg` with apt (needed from BE-06; install it now so the image does not change later).
- Copy `ai/` and install it (`pip install ./ai` is fine in the image; set `GHOSTCHEF_FIXTURE_DIR=/srv/ai/fixtures` so fake mode and seeding can still find the fixture).
- Copy `backend/` and install it. Copy `web/` to `/srv/web` and set `WEB_DIR=/srv/web`.
- Run as a non-root user. `CMD` runs `uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}` with **one worker** (in-memory session state — latest frame, in-flight guard, metrics — assumes a single process).
- `backend/Dockerfile.dockerignore` (BuildKit reads `<Dockerfile name>.dockerignore`): exclude `.git`, `**/.venv`, `**/__pycache__`, `ai/footage`, `ai/eval/frames/raw`, `ios`, `**/.env`, `backend/.data`.

**Acceptance:** from the repository root, `docker build -f backend/Dockerfile -t ghostchef-backend .` succeeds and `docker run -p 8000:8000 -e DEMO_API_KEY=dev-key ghostchef-backend` answers `/health` (memory + fake by default). If Docker is not installed on this laptop, say so in `STATUS.md` and rely on Railway's build log instead.

### BE-04.2 Railway configuration

**Do**
- `backend/railway.json` (config as code): Dockerfile builder with `dockerfilePath: "backend/Dockerfile"`, health check path `/health`, restart on failure. Check the current schema in Railway's docs.
- A "Deploying" section in `backend/README.md` with the exact dashboard steps:
  1. New project → deploy from the GitHub repository; root directory = repository root; config file path = `backend/railway.json`.
  2. Variables: `DEMO_API_KEY` (new long random string), `STORAGE=supabase`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `GHOSTCHEF_AI_FAKE=0`, `GEMINI_API_KEY`, the four `GHOSTCHEF_MODEL_*` values from `ai/STATUS.md`, `CORS_ORIGINS` (the Railway URL itself, plus `http://localhost:5173` for local web work).
  3. Generate a public domain.
  4. Set replicas to 1.

**Acceptance:** files committed; steps are complete enough for someone else to follow.

### BE-04.3 Deploy *(human)*

- Follow the steps. Watch the build log.
- `curl https://<domain>/health` → `ai_mode: gemini`, `storage: supabase`.
- Run the smoke script against production with a real frame.
- Open `https://<domain>/app/` and confirm the web app loads (it may be an early version).

**Acceptance:** `STATUS.md` → "Where the API is" has the production URL; "Last smoke run" has a production row. The URL and the new demo key are shared privately with the team.

### BE-04.4 Emergency laptop mode

**Do** — a "Emergency mode" section in `backend/README.md` and a helper `backend/scripts/emergency.sh` (and `emergency.ps1` for Windows) that:
- starts the server on `0.0.0.0:8000` with `STORAGE=memory`, real Gemini, the fixture auto-seeded;
- prints the laptop's LAN addresses and the URL to type into the app's settings.

Rehearse it once: laptop and phone on a phone hotspot, app pointed at the laptop, one check succeeds.

Limits to write down: plain HTTP on a LAN address means the **web simulator's camera will not work from another device** (browsers require HTTPS or `localhost`); the iOS app needs local-network permission and an App Transport Security exception for HTTP (tell the iOS owner — it is task IOS-01.2).

**Acceptance:** `STATUS.md` → "Emergency laptop" row filled after a real rehearsal, or marked `NOT REHEARSED`.

### BE-04.5 Keep production current

**Do** — decide and document one of: automatic deploy on every push to `main`, or manual deploys. During a hackathon automatic is convenient but a broken push breaks everyone's phone testing; if you choose automatic, the rule is **`pytest` and the local smoke script pass before every push**.

**Acceptance:** the choice is written in `STATUS.md`.

## Verification

```bash
docker build -f backend/Dockerfile -t ghostchef-backend .        # from the repository root
python backend/scripts/smoke.py --base https://<domain> --key <demo key> --frame <real frame>
```

## Out of scope

Custom domains, autoscaling, CI pipelines.

## When done

Update `STATUS.md`, commit `[backend] BE-04 Dockerfile, Railway config, emergency mode`, push, announce the production URL.
