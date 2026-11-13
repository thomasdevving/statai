# BE-07 — Hardening, load check, recovery tests, end-to-end sign-off

| | |
|---|---|
| **Track** | `backend/` |
| **Gate** | G4 |
| **Depends on** | BE-01 … BE-06 (BE-06 may be partial if ingestion was cut from the demo) |
| **Unblocks** | Demo readiness |
| **Size** | Medium |
| **Model** | Opus 5.5; Sonnet 5.5 is enough for the README and status edits |
| **Needs a human for** | Running the recovery tests and the rehearsal |

## Goal

Nothing the demo can plausibly do makes the server fall over or lie, and the team has evidence for that. No new features in this batch.

## Read first

- [../../docs/ARCHITECTURE.md §6](../../docs/ARCHITECTURE.md#6-failure-behaviour) and §7
- [../../docs/EVALUATION.md §6](../../docs/EVALUATION.md#6-recovery-tests)
- `backend/STATUS.md` → Recovery tests table

## Tasks

### BE-07.1 Watcher-cadence load check

**Do** — `backend/scripts/load_watch.py`: simulate N sessions (default 2) each sending a `/watch` every 2.5 s for M minutes (default 3) with a real frame, plus one `/check` every 20 s per session. Report per-endpoint counts by status code, p50 / p90 / max latency, and any `429`.

Run it against production with real Gemini **once**, mindful of quota (ask the AI owner for the RPM limit first; do not run it right before the demo).

**Acceptance:** results in `STATUS.md`. If quota errors appear at two sessions, write the consequence ("rehearse with one session at a time") and tell the team.

### BE-07.2 Quota and outage behaviour

**Do**
- On `AIQuotaError` in `/watch`, set a per-process "cool-down until" timestamp (10 s); during it, `/watch` answers `429` immediately without calling the model. `/check` is never blocked by the cool-down (the wearer asked explicitly) but is subject to its own errors.
- A debug switch for rehearsing failures without touching Gemini: env `FAULT_INJECT` with values `timeout`, `quota`, `unavailable`, applied to the next AI call when the request carries header `X-Fault: 1`. Disabled unless `FAULT_INJECT_ENABLED=1`; never enabled in production during the demo.

**Acceptance:** tests for the cool-down and the injected faults.

### BE-07.3 Security pass

Check and fix each:
- [ ] No endpoint except `/health`, `/local-files/*` and `/local-upload/*` (memory mode only, the latter token-checked), `/sessions/{id}/latest-frame.jpg` (token), and `/app/*` (static) is reachable without the key.
- [ ] `DEMO_API_KEY` in production is not `dev-key`; the server refuses to start with `dev-key` when `STORAGE=supabase` and `GHOSTCHEF_AI_FAKE=0`.
- [ ] `CORS_ORIGINS` in production is not `*`.
- [ ] Path traversal impossible in `/local-files`.
- [ ] Logs contain no keys, tokens, or signed-URL signatures (grep a log sample).
- [ ] Video limits enforced: the `videos` bucket has the 500 MB / `video/mp4` limits; the job checks size while downloading and `ffprobe`s before Gemini; the memory-mode `PUT /local-upload` streams with a cap and refuses a reused or wrong token.
- [ ] A signed upload URL only allows writing `videos/<recipe_id>/source.mp4` (try another path with the same token: refused).
- [ ] `git log -p` contains no secret (`git log -p | grep -n -i -E "service_role|AIza|sk-"` returns nothing real).
- [ ] A Supabase request with the anon key still returns nothing.

**Acceptance:** each box ticked in `STATUS.md` with a note of how it was checked.

### BE-07.4 Recovery tests *(human, with the iOS and web owners)*

Fill the "Recovery tests" table in `STATUS.md` by actually triggering each row (fault injection, a wrong key, an oversized file, stopping the server mid-check, turning off Wi-Fi). Expected results are in the table and in ARCHITECTURE §6.

**Acceptance:** every row has an observed result and a date. Mismatches are either fixed or written up as known limits.

### BE-07.5 Data hygiene

**Do**
- `backend/scripts/cleanup.py`: lists and (with `--yes`) deletes sessions older than N hours with their frames, and `failed` recipes. Never touches the seeded recipe.
- Run it before the final rehearsal so the monitor's session list is clean.
- Note in `STATUS.md` what footage and frames exist in storage, for the team's consent and retention answer.

**Acceptance:** script works on both stores.

### BE-07.6 Final smoke and freeze

**Do**
- Full smoke run against production with a real frame; record it.
- Emergency mode rehearsed once more on the hotspot.
- Tag the commit the demo runs on: tell the team the hash; from now on only fixes agreed at a sync are deployed.
- Make sure `backend/README.md` setup, configuration, deployment, and emergency sections match reality.

**Acceptance:** `STATUS.md` shows the frozen commit, the last smoke run, and all seven batches' final status.

## Verification

```bash
cd backend
ruff check .
pytest -q
python scripts/smoke.py --base https://<domain> --key <demo key> --frame <real frame>
python scripts/load_watch.py --base https://<domain> --key <demo key> --sessions 2 --minutes 3 --frame <real frame>
```

## Out of scope

New endpoints or features. Anything that needs a contract change.

## When done

Update `STATUS.md`, commit `[backend] BE-07 hardening and e2e sign-off`, push.
