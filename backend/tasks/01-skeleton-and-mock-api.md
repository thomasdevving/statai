# BE-01 — Skeleton and the full API on the memory store with fake AI

| | |
|---|---|
| **Track** | `backend/` |
| **Gate** | G0 — the iOS and web tracks are waiting for this. **Push after task 5** so they can start, then finish the rest. |
| **Depends on** | AI-01 on `main` (the `ghostchef_ai` package in fake mode and the fixture). If it is not there yet, do tasks 1–3 and check again. |
| **Unblocks** | IOS-01, WEB-01, and every later batch |
| **Size** | Large |
| **Model** | Opus 5.5 |
| **Needs a human for** | Posting the LAN URL and the dev key in the team chat |

## Goal

A running FastAPI server that implements **every endpoint in the contract with real logic**, backed by an in-memory store and the fake AI. Nothing is stubbed with canned JSON: later batches swap the store and the AI mode without touching the routers.

## Read first

- [../../docs/API-CONTRACT.md](../../docs/API-CONTRACT.md) — all of it; you implement §1–§5 and consume §7–§8
- [../README.md](../README.md) — layout, configuration table, rules
- `ai/src/ghostchef_ai/__init__.py` and `ai/fixtures/` once AI-01 is on `main`

## Tasks

### BE-01.1 Project scaffold

**Do**
- `backend/pyproject.toml`: project `ghostchef-backend`, `requires-python = ">=3.11"`. Dependencies: `fastapi`, `uvicorn[standard]`, `pydantic>=2`, `pydantic-settings`, `python-multipart`, `httpx`, `pillow`. Dev group: `pytest`, `pytest-asyncio`, `ruff`. Do **not** list `ghostchef-ai` as a dependency; it is installed with `pip install -e ../ai` (documented in the README).
- pytest config: `asyncio_mode = "auto"`. ruff line length 100.
- `backend/.env.example` with every variable from the README's configuration table.
- `app/config.py`: a `Settings` class reading those variables, cached with `lru_cache`.

**Acceptance:** `pip install -e ../ai && pip install -e ".[dev]"` works in a fresh virtualenv.

### BE-01.2 App factory, auth, errors, health

**Do**
- `app/main.py::create_app()`: CORS from settings (allow headers `X-Demo-Key`, `Content-Type`); include routers; mount `WEB_DIR` at `/app` with `StaticFiles(html=True)` **only if the directory exists**.
- `app/auth.py`: dependency that compares `X-Demo-Key` with the setting using `hmac.compare_digest`; applied to every router except health.
- `app/errors.py`: `ApiError(status, code, message, retryable=False, request_id=None)`; exception handlers that render the envelope from API-CONTRACT §1.1 for `ApiError`, for FastAPI's `RequestValidationError` (→ `422 validation_error`), for `ghostchef_ai` errors (`AITimeout → 504`, `AIQuotaError → 429`, `AIUnavailable` / `AIInvalidOutput → 503`), and a catch-all (→ `500 internal`, message without internals).
- `GET /health` → `{status, contract_version: "1.0", ai_mode, storage}`. `ai_mode` comes from `ghostchef_ai.config.is_fake()`.

**Acceptance:** tests for 401 on a missing key, the envelope shape for 404 and 422, and the health body.

### BE-01.3 Store protocol and MemoryStore

**Do**
- `app/store/base.py`: plain dataclasses or pydantic records for `Recipe`, `Step`, `Session`, `Event`, mirroring API-CONTRACT §6, and a `Store` protocol with async methods for: list / get / create / update / delete recipe; get / list / replace / update steps; create / get / list sessions; append / list events; put / get / delete a blob (`bucket`, `path`, `bytes`, `content_type`); `signed_url(bucket, path, ttl_s) -> str`.
- `app/store/memory.py`: dict-backed implementation. Blobs are written under `DATA_DIR/<bucket>/<path>`. `signed_url` returns `<PUBLIC_BASE_URL or request base>/local-files/<bucket>/<path>`; add an unauthenticated `GET /local-files/{bucket}/{path:path}` route that serves those files **only when `STORAGE=memory`** (reject `..` in paths).
- `app/deps.py::get_store()` returns a process-wide singleton chosen by `STORAGE` (`supabase` raises a clear "not implemented until BE-02" error for now).
- **Startup seed (memory mode only):** load `ghostchef_ai.config.fixture_dir()/sushi_recipe.json`, create one recipe with status `published`, its steps, and copy `images/step-<idx>.jpg` into the `media` bucket at `media/<recipe_id>/steps/<idx>/ref.jpg`. Use a **fixed UUID** for the seeded recipe (e.g. `00000000-0000-4000-8000-000000000001`) and deterministic step UUIDs (`uuid5` of recipe id + idx) so clients can hard-code them in tests.

**Acceptance:** store unit tests (CRUD, cascade delete, blob round trip); after startup `GET /recipes` shows the seeded recipe.

### BE-01.4 Recipes and steps (read) + response models

**Do**
- `app/schemas.py`: pydantic response models for `Step`, recipe list item, recipe detail, exactly as in API-CONTRACT §2. Build `ref_image_url` / `clip_url` / `video_url` through `store.signed_url`.
- `GET /recipes` (optional `status` filter), `GET /recipes/{id}`.

**Acceptance:** contract tests assert field names and types for both; an image URL from the response returns `200 image/jpeg`.

### BE-01.5 Check, watch, sessions — then push

**Do**
- `POST /check` and `POST /watch` (multipart per §3.1 / §3.2): load the step and its recipe, load the reference image bytes from the store (check only), convert the step record to `ghostchef_ai.StepSpec`, call `check_frame` / `watch_frame` with the budgets from settings, measure `latency_ms` with `time.perf_counter`, return the response with `request_id` and `step_id` echoed. If `session_id` is given: store the frame at `frames/<session_id>/<request_id>.jpg` and append the server-recorded event (`check_pass` / `check_fix` / `check_unsure`; `watch_warn` only for warns).
- `POST /sessions`, `POST /sessions/{id}/events` (reject server-recorded kinds from clients with `422`; `session_end` sets `finished_at`), `GET /sessions/{id}` with `summary`, `GET /sessions?active=true&limit=`.
- Summary rules: `steps_total` = number of steps; `steps_passed_first_try` = steps whose first check event is `check_pass`; `fixes_caught` = count of `check_fix`; `warnings` = count of `watch_warn`; `questions` = count of `question`.

**Acceptance**
- Tests: in fake mode the first check on step 3 is `fix` with `mistake_id: rice_too_thick`, the second is `pass`; a tiny (< 5 KB) JPEG gives `unsure`; watch calls 1–3 are `ok`, 4–6 `warn`. Call `ghostchef_ai.fake.reset()` in a fixture between tests.
- Events appear in `GET /sessions/{id}`; the summary matches.
- **Commit and push now** (`[backend] BE-01 first slice: recipes, check, watch, sessions`). Post the LAN URL and dev key privately to the team.

### BE-01.6 Remaining endpoints

**Do** — all with real logic on the memory store:
- `GET /sessions/{id}/monitor` in the full contract shape: `current_step` from the latest `step_change` event's `to_idx` (else step 1); `last_frame_url` and `last_frame_at` for the latest stored frame; `last_result`; last 30 events newest first; `latency` from `app/metrics.py` (per-session lists of check and watch latencies; p50, max, n).
- `GET /live-token?recipe_id=&session_id=`: build the config with `ghostchef_ai.build_live_config(...)` from the recipe's steps and transcript, call `mint_live_token`, return the §5 shape with `api_version: "v1beta"`.
- `POST /recipes` (multipart with `consent`): validate, save the upload to the `videos` bucket, create the recipe as `processing`, start a background task that calls `ghostchef_ai.extract_recipe`, inserts the steps, and sets `review`. **No ffmpeg yet:** for now each step's reference image is the fixture image with the same `idx` if one exists, else none. On any exception set `failed` and `error`.
- `PATCH /recipes/{id}`, `PATCH /steps/{id}` (enforce word limits → `422`; a changed `timestamp_s` is stored, re-extraction comes in BE-06), `POST /recipes/{id}/publish` (rules in §2), `DELETE /recipes/{id}` (cascade including blobs).

**Acceptance:** contract tests for each endpoint's success path and its main error (`409` publish while processing, `422` over-long title, `415` non-MP4, `422` missing consent, `404` unknown ids). The fake ingestion moves a recipe `processing → review` within a few seconds in a test.

### BE-01.7 Smoke script

**Do** — `backend/scripts/smoke.py` (plain `httpx`, no test framework), arguments `--base`, `--key`, `--frame` (default: a fixture image), `--watch-n` (default 6):
1. `GET /health` and print `ai_mode` / `storage`.
2. List recipes, pick the first `published` one, fetch it, download step images.
3. Create a session; post a `step_change`.
4. `/check` twice on the first step that has `watch_fors`; `/watch` N times, 2.5 s apart (flag `--fast` skips the sleep).
5. `GET /live-token`; print model and `locked` (never print the token).
6. `GET /sessions/{id}/monitor` and `GET /sessions/{id}`; post `session_end`.
7. Print a table: step, endpoint, HTTP status, `latency_ms`, verdict / status; then p50 and max per endpoint. Exit non-zero on any unexpected status.

**Acceptance:** `python scripts/smoke.py --base http://localhost:8000 --key dev-key --fast` exits 0 against the local server.

### BE-01.8 Wrap up

- `ruff check .` and `pytest -q` clean.
- Export the OpenAPI document once for the client tracks' convenience: `python -c "import json; from app.main import create_app; print(json.dumps(create_app().openapi(), indent=1))" > openapi.json` and commit it. The contract file still wins over it.
- Update `STATUS.md`: batch 01 → `DONE (fake)`, the LAN URL row, the contract conformance table.

## Verification

```bash
cd backend
ruff check .
pytest -q
uvicorn app.main:app --host 0.0.0.0 --port 8000 &
python scripts/smoke.py --base http://localhost:8000 --key dev-key --fast
curl -s http://localhost:8000/health
```

## Out of scope

Supabase (BE-02). Image validation and downscaling, in-flight guard, real-AI tuning (BE-03). ffmpeg (BE-06). Docker (BE-04).

## When done

Commit `[backend] BE-01 full API on memory store + fake AI`, push, and tell the iOS and web owners which endpoints are live and where.
