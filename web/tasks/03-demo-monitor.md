# WEB-03 — Demo monitor: what the audience sees

| | |
|---|---|
| **Track** | `web/` |
| **Gate** | G2. Build this **before** the review page. |
| **Depends on** | WEB-01 (shared modules). BE-01 gives the feed's shape; BE-03.5 and BE-05 make it complete (latest frame, `ok` watch results, latency). |
| **Unblocks** | Peer review and partner judging: people who are not wearing the glasses can see it work |
| **Size** | Medium |
| **Model** | Opus 5.5 for the logic; Sonnet 5.5 is enough for layout polish |
| **Needs a human for** | Looking at it from three metres away |

## Goal

A single full-screen page that attaches itself to the running session and shows, live: the chef's reference, what the wearer's camera sees, the card in the lens, and a timeline of what the system decided and how fast. It makes the cause-and-effect chain visible, and it is honest about what is live.

## Read first

- [../../docs/API-CONTRACT.md §4](../../docs/API-CONTRACT.md#4-sessions-and-events) — `GET /sessions?active=true`, `GET /sessions/{id}/monitor`, event kinds and payloads
- [../../docs/DEMO-AND-SUBMISSION.md](../../docs/DEMO-AND-SUBMISSION.md) §2 (the beats) and §3 (what the audience sees, the LIVE / REPLAY rule)
- [../README.md](../README.md) — design rules

## Tasks

### WEB-03.1 Attach and poll

**Do** — `monitor/index.html`, `monitor/monitor.js`; add `listSessions`, `getMonitor` to `shared/api.js`.
- On load, and every 5 s while idle: `GET /sessions?active=true&limit=5`; attach to the newest. A small picker lets the operator choose another. `?session=<id>` in the URL pins one.
- While attached: `GET /sessions/{id}/monitor` every **1 s**. Never overlap polls; skip a tick if the previous call is still running. Stop polling when the tab is hidden.
- When a newer active session appears (the wearer restarted), switch to it automatically unless pinned.
- Connection problems show a small "reconnecting" state; the last good data stays on screen, and the LIVE badge drops (WEB-03.4).

**Acceptance:** start a session in the simulator in another tab: the monitor attaches within 5 s without being touched; restarting the simulator's session moves the monitor to the new one.

### WEB-03.2 Layout

**Do** — one screen, no scrolling, 16:9, readable from three metres:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ Ghost Chef · Maki roll · Step 3 of 6: Spread rice              ● LIVE    │
├───────────────────────┬───────────────────────┬──────────────────────────┤
│  CHEF'S REFERENCE     │  WEARER'S VIEW        │  IN THE LENS             │
│  [ref image]          │  [latest frame]       │  [lens card]             │
│                       │  frame age 0.8 s      │                          │
├───────────────────────┴───────────────────────┴──────────────────────────┤
│ TIMELINE (newest first)                         │ check 1.4 s · watch 0.6 s│
│ 12:04:31  ⚠ Watcher: Too much rice (0.91)       │ device: Display · ios    │
│ 12:04:40  ✓ Check: Looks right (0.88) 1.3 s     │ ai: gemini · supabase    │
└──────────────────────────────────────────────────────────────────────────┘
```

- Reference image from `current_step.ref_image_url`; wearer's frame from `last_frame_url`. **Reload the frame image only when `last_frame_at` changes** (append it as a cache-busting query) to avoid flicker and needless traffic.
- Portrait frames are shown uncropped (`object-fit: contain`) on black.
- Header: recipe title, step counter and title, the badge.

**Acceptance:** at 1920×1080 and at a 13-inch laptop's resolution nothing overflows; text is legible from across a room.

### WEB-03.3 The lens card and the timeline

**Do**
- **Lens card:** the monitor does not receive the phone's lens state directly; derive it from the feed and render it with `shared/lens.js`:
  - latest event is `check_fix` or `watch_warn` newer than the latest `check_pass` / `step_change` / `warning_dismissed` → `fix` card (proactive for `watch_warn`) with that payload's headline and fix;
  - latest event is `check_pass` within the last 3 s → `pass`;
  - `check_unsure` within the last 4 s → `unsure`;
  - otherwise → `step` card for `current_step`, with the dot active when `last_result.source` is `watch` and under 6 s old.
  Label the panel "In the lens (reconstructed from session events)" in small type: it is a faithful reconstruction, not a screen capture.
- **Timeline:** one line per event, newest first, with a time, an icon, and plain words: step changes, watcher warnings (mistake headline, confidence), checks (verdict, headline, confidence, `latency_ms`), questions (caption), dismissals, errors. `ok` watch results are not events; show them as a quiet "watching… ok (0.6 s)" ticker line from `last_result`.
- **Side panel:** check and watch p50 and max from `latency`, counts, device label and client, `ai_mode` and `storage` (red if `fake`).

**Acceptance:** run the simulator through mistake → warning → fix → pass while watching the monitor: each beat of the demo script is visible on the monitor within about a second.

### WEB-03.4 LIVE / REPLAY honesty

**Do**
- **LIVE** (green) when the last successful poll is under 3 s old **and** the session has activity under 30 s old. **IDLE** (grey) when attached but quiet. **OFFLINE** (red) when polls fail.
- A **Backup** mode (key `B`, or a button): plays a local video file chosen with a file picker, full-screen in the page, under a large permanent **REPLAY — recorded <label>** badge. Nothing in this mode can display "LIVE".
- If `/health` reports `ai_mode: fake`, a permanent banner says **FAKE AI — development mode**.

**Acceptance:** stopping the backend turns the badge to OFFLINE within 3 s; Backup mode shows the REPLAY badge throughout.

### WEB-03.5 Operator comforts

**Do** — keyboard: `F` full-screen, `B` backup, `S` session picker, `H` hide/show the side panel. Prevent the display from sleeping where the browser supports the Screen Wake Lock API. A `?clean=1` URL mode hides the debug-ish side panel for the stage.

**Acceptance:** the operator can run the whole demo without the mouse.

### WEB-03.6 With the real app

When the iOS app runs a session (phone camera or glasses), attach the monitor and watch one full loop.

**Acceptance:** `STATUS.md` records that the monitor followed an iOS session, the typical delay between an action and its appearance, and any mismatch between the reconstructed lens card and what the phone preview showed (report mismatches to the iOS and backend owners).

## Verification

```bash
python -m http.server 5173 --directory web      # http://localhost:5173/monitor/  +  http://localhost:5173/sim/ in a second tab
```

## Out of scope

Server-sent events or WebSockets (polling is sufficient and simpler). Recording the session in the browser. Showing audio.

## When done

Update `STATUS.md`, commit `[web] WEB-03 demo monitor`, push, show it at the next sync.
