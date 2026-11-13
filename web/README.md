# Track: `web/` — simulator, chef studio, demo monitor, pitch and submission

**Owner: Türker**

You own three small browser apps and everything that faces people outside the team: user conversations, the pitch pack, demo operations, and the submission. The code here is the lightest of the four tracks; the non-code work (users, deck, rehearsal, forms) is what usually gets forgotten at hackathons, so it has an owner: you.

New here? Read [../README.md](../README.md), [../docs/PRODUCT.md](../docs/PRODUCT.md), [../docs/API-CONTRACT.md](../docs/API-CONTRACT.md) §1–§4, [../docs/DEMO-AND-SUBMISSION.md](../docs/DEMO-AND-SUBMISSION.md), then this file.

## What you deliver

| Deliverable | Why it exists |
|---|---|
| **Simulator** (`sim/`) — the cook-along loop in a browser with a webcam or uploaded photos | Lets `backend/` and `ai/` be tested end to end without the Mac or the glasses; last-resort demo fallback |
| **Chef studio** (`studio/`) — upload, review, edit, publish | A Must in the spec; shows the ingestion story |
| **Demo monitor** (`monitor/`) — live view of a running session | The audience cannot see inside a lens |
| **Pitch pack** (`pitch/`) — one-liners, deck, evidence, Q&A, user notes | Judging |
| Demo kit, run sheet, backup recording, **submission** | Deadlines |

The simulator is a development tool and a fallback. It is never presented as the Meta deliverable.

## Setup

No build step, no framework, no package install. Plain HTML, CSS, and ES modules.

```bash
# Option A — served by the backend (same origin, no CORS, works on phones over HTTPS in production)
#   start the backend (see ../backend/README.md), then open  http://localhost:8000/app/

# Option B — standalone static server, talking to any backend
python -m http.server 5173 --directory web
#   open http://localhost:5173/  and set the API base URL + demo key in Settings (gear icon)
```

Optional: Node 18+ only to run the one unit-test file (`node --test web/tests/`).

**Camera note:** browsers allow camera access only on `https://` or `localhost`. The simulator's webcam works on your own laptop at `localhost` and on the deployed HTTPS URL, but not when another device opens `http://<LAN-IP>:…`. Use "Upload a photo" there.

## Target layout

```
web/
  index.html              landing page: Simulator · Studio · Monitor · Settings
  shared/
    config.js             API base + demo key (localStorage; defaults to same origin under /app/)
    api.js                fetch wrapper: X-Demo-Key, error envelope → ApiError, multipart helpers
    lens.js  lens.css     renderLens(element, lensScreen) — the lens card, shared by sim and monitor
    debounce.js           watcher debounce (same rules as the iOS app) — pure, unit-tested
    ui.css                shared page styling
  sim/       index.html  sim.js
  studio/    index.html  studio.js
  monitor/   index.html  monitor.js
  tests/     debounce.test.mjs
  pitch/     one-liners.md  deck-outline.md  evidence.md  qa.md  user-notes.md  run-sheet.md  architecture.svg  deck.pdf
  README.md  STATUS.md  tasks/
```

## Design rules for the three apps

- **The lens card looks the same everywhere.** `shared/lens.js` renders the display spec from [../docs/TECH-SPEC.md](../docs/TECH-SPEC.md): black background, bright elements, at most two short text lines, amber for fix, green for pass. The simulator and the monitor both use it.
- **Client rules are the contract's rules.** The simulator implements the stale-result rule (§3.4) and the watcher rules (§3.3) exactly as the iOS app does.
- **Always show what you are connected to.** Every page has a footer strip with the API base, `ai_mode`, and `storage` from `/health`, turning red when `ai_mode` is `fake`.
- **Readable from three metres.** The monitor is shown on a laptop to people standing at a table: large type, high contrast, no clutter.
- **Label recordings.** Anything not live carries a visible `REPLAY` badge.
- Everything works with the keyboard; images have alt text; no information by colour alone.

## Batches

One Claude session per batch. Kickoff prompt: [../docs/PLAN.md §7](../docs/PLAN.md#7-working-with-claude-on-each-laptop).

| # | Batch | Gate | Needs | A human must |
|---|---|---|---|---|
| 01 | [Foundation and simulator](tasks/01-foundation-and-simulator.md) | G0→G1 | BE-01 reachable | Point a webcam at things |
| 02 | [Chef studio](tasks/02-chef-studio.md) | G3 | BE-01 (fake ingestion) to build; BE-06 for real | Review a real ingested recipe |
| 03 | [Demo monitor](tasks/03-demo-monitor.md) | G2 | BE-01 to build; BE-03.5 + BE-05 for the full feed | Check it from across a table |
| 04 | [User evidence and pitch pack](tasks/04-user-evidence-and-pitch-pack.md) | G3→G4 | A working loop to show people; AI-07 numbers; IOS-06 device facts | Talk to people; build the deck |
| 05 | [Demo ops and submission](tasks/05-demo-ops-and-submission.md) | **Starts tonight** (preliminary submission), ends G5 | — | Shop, rehearse, submit |

**Do WEB-05 task 1 (preliminary submission) immediately**, before any code. Then 01. Build 03 before 02: the monitor is needed for G2, the studio for G3.

## Rules for this track

- Deck and spoken claims use **only** measured values from `ai/STATUS.md`, `backend/STATUS.md`, `ios/STATUS.md`, and [../docs/EVALUATION.md](../docs/EVALUATION.md). The allowed-claims table is in [../docs/PRODUCT.md §10](../docs/PRODUCT.md#10-what-we-can-and-cannot-claim).
- No names, faces, or quotes of people outside the team in the repository without their permission. The repository is public.
- Submitting forms, publishing videos, and messaging organizers or partners are done by **you, the human owner**. Claude drafts; you send.
- Do not edit other tracks' folders. API problems go in [STATUS.md](STATUS.md) → "Needs from other tracks" and to the backend owner.
- The demo key is typed into Settings and kept in the browser's localStorage. It is never written into a file in this folder.
