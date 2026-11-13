# Ghost Chef — agent guidance

Junction 2026 hackathon project. Four people work in parallel on four laptops, one folder each. Keep this file short; the documents it points to are the sources of truth.

## Read before doing anything

1. [README.md](README.md) — what the project is and where everything lives.
2. [docs/API-CONTRACT.md](docs/API-CONTRACT.md) — every interface between tracks. This wins over any other description.
3. The `README.md` of the track you are working in (`ios/`, `backend/`, `ai/`, or `web/`), then the task batch you were asked to run in `<track>/tasks/`.

[docs/TECH-SPEC.md](docs/TECH-SPEC.md) is the team's product concept. Do not edit it.

## Rules

- **Stay in your track folder.** Create and edit files only under the track you were started in. Never edit another track's folder, even to fix an obvious bug: write the problem in your track's `STATUS.md` under "Needs from other tracks" and tell the user.
- **Shared files** (`README.md`, `CLAUDE.md`, `docs/**`) change only when the user explicitly asks, and contract changes follow `docs/API-CONTRACT.md` §9.
- **One batch at a time.** A batch is done when every acceptance criterion in its file is met and the track's `STATUS.md` is updated. Do not start the next batch on your own.
- **Report honestly.** Never write that hardware is connected, an API works, or a number was measured unless you ran it in this session and saw the output. Targets and measured results are recorded separately. Fake-mode and replayed results are labelled as such.
- **No secrets in the repo.** It is public. Keys live in untracked `.env` / `Secrets.xcconfig` files; commit only the `.example` versions.
- **Model IDs and SDK versions** come from `ai/STATUS.md` and `ios/STATUS.md` once verified there. Do not use identifiers from memory.
- **Settled decisions, do not reopen:** Meta main challenge + Gemini technology challenge; Arduino excluded; native iOS with Meta's Device Access Toolkit; FastAPI backend; Supabase; Gemini Live opened from the phone with an ephemeral token. See [docs/DECISIONS-AND-RISKS.md](docs/DECISIONS-AND-RISKS.md).

## Git

- Trunk-based on `main`. Commit small and often, message prefix = track: `[ios] …`, `[backend] …`, `[ai] …`, `[web] …`, `[docs] …`.
- Before every push: `git pull --rebase origin main`. Never force-push. Never rewrite history.
- A commit touches one track folder only. This is what keeps four laptops free of merge conflicts.
- Commit or push only when the user asks you to.
