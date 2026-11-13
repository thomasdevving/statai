# BE-02 — Supabase schema, private storage, seed

| | |
|---|---|
| **Track** | `backend/` |
| **Gate** | G1 → G2 |
| **Depends on** | BE-01 |
| **Unblocks** | BE-04 (deployment needs persistent storage), BE-06 |
| **Size** | Medium |
| **Model** | Opus 5.5 |
| **Needs a human for** | Creating the Supabase project, running the SQL, copying the URL and service key into `.env` |

## Goal

`STORAGE=supabase` works as a drop-in replacement for the memory store: same routers, same tests, data and files persisted in Supabase, the demo recipe seeded with one command.

## Read first

- [../../docs/API-CONTRACT.md §6](../../docs/API-CONTRACT.md#6-data-model-supabase-postgres) — tables, buckets, RLS
- `backend/app/store/base.py` — the protocol you are implementing
- Current Supabase Python client documentation (`supabase` package) for table queries, storage upload, and `create_signed_url`

## Tasks

### BE-02.1 Create the project *(human)*

- Create a Supabase project (free tier is enough). Pick the region closest to Finland.
- Copy the project URL and the **service role** key into `backend/.env` as `SUPABASE_URL` and `SUPABASE_SERVICE_KEY`. The service key bypasses Row Level Security: it never goes into a client, the repository, or a chat.
- Record the project name, owner, and region in `STATUS.md` → Accounts.

### BE-02.2 Migration

**Do** — `backend/migrations/001_init.sql`:
- The four `create table` statements from API-CONTRACT §6, verbatim, plus indexes: `steps(recipe_id, idx)`, `sessions(recipe_id)`, `sessions(started_at desc)`, `session_events(session_id, created_at)`.
- `alter table … enable row level security;` on all four, with **no policies** (so `anon` and `authenticated` can do nothing; the service role bypasses RLS).
- Storage buckets `videos`, `media`, `frames`, all private: `insert into storage.buckets (id, name, public) values (…, false) on conflict do nothing;`
- The file is idempotent (`create table if not exists`, `create index if not exists`).

The human runs it once in the Supabase SQL editor.

**Acceptance:** tables and buckets exist; a request with the **anon** key to `rest/v1/recipes` returns no rows or is refused (verify with one `curl` and write the result in `STATUS.md`).

### BE-02.3 SupabaseStore

**Do** — `app/store/supabase_store.py` implementing the full `Store` protocol:
- Add `supabase` to the dependencies. Create one client at startup from the settings. The client's calls are blocking: run them with `asyncio.to_thread` (or use the async client if the installed version provides a stable one) so a slow query never blocks the event loop.
- Recipes / steps / sessions / events: straightforward table operations. `replace_steps(recipe_id, steps)` deletes then inserts in order. `delete_recipe` relies on `on delete cascade`, then removes blobs under `videos/<recipe_id>/`, `media/<recipe_id>/`, and `frames/<session_id>/` for each deleted session.
- Blobs: `put_blob` uploads with upsert; `get_blob` downloads; `signed_url` uses `create_signed_url(path, ttl)`. Cache signed URLs in memory for half their lifetime to avoid one network call per step on every `GET /recipes/{id}`.
- Map Supabase failures to `ApiError(500, "internal", …)` with a log line that does not include the key.
- `deps.get_store()` returns it when `STORAGE=supabase`; missing URL or key → fail at startup with a clear message.

**Acceptance**
- The existing test suite still passes on memory.
- An opt-in integration test module (`tests/test_supabase_integration.py`, skipped unless `SUPABASE_URL` is set and `RUN_SUPABASE_TESTS=1`) runs the store CRUD and blob round trip against the real project using a throwaway recipe, and cleans up.

### BE-02.4 Seed script

**Do** — `backend/scripts/seed.py`:
- `python scripts/seed.py [--fixture ../ai/fixtures] [--publish] [--replace]`
- Works against whichever store `STORAGE` selects.
- Reads `sushi_recipe.json` (validate it with `ghostchef_ai.schemas.RecipeDraft`), creates the recipe with the **same fixed UUIDs** as the BE-01 startup seed, uploads `images/step-<idx>.jpg` to `media/<recipe_id>/steps/<idx>/ref.jpg`, inserts the steps, sets status `review` or `published`.
- `--replace` deletes an existing recipe with that id first. Without it, an existing recipe makes the script exit with a message (no accidental duplicates).
- Prints the recipe id and step ids.
- Memory mode keeps its automatic startup seed from BE-01; Supabase mode is seeded **only** by this script.

**Acceptance:** `STORAGE=supabase python scripts/seed.py --publish --replace` succeeds twice in a row; `GET /recipes/<fixed id>` returns steps with signed URLs that load in a browser.

### BE-02.5 Run everything on Supabase

**Do**
- Start the server with `STORAGE=supabase` and run the smoke script.
- Re-seed whenever the AI owner announces a new fixture (real reference stills after AI-03.5).

**Acceptance:** smoke run exits 0; `GET /health` reports `storage: supabase`; rows are visible in the Supabase table editor; frames appear in the `frames` bucket.

## Verification

```bash
cd backend
pytest -q
STORAGE=supabase python scripts/seed.py --publish --replace
STORAGE=supabase uvicorn app.main:app --port 8000 &
python scripts/smoke.py --base http://localhost:8000 --key dev-key --fast
RUN_SUPABASE_TESTS=1 pytest -q tests/test_supabase_integration.py
```

## Out of scope

ffmpeg-derived stills from an uploaded video (BE-06). Deployment (BE-04).

## When done

Update `STATUS.md` (batch 02, Accounts), commit `[backend] BE-02 Supabase store, migration, seed`, push.
