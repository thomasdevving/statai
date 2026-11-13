# WEB-01 — Web foundation and the cook-along simulator

| | |
|---|---|
| **Track** | `web/` |
| **Gate** | G0 (talks to the mock API) → G1 (first real verdict through a webcam) |
| **Depends on** | BE-01 reachable. Until it is, build against a copy of the fixture. |
| **Unblocks** | End-to-end testing for `backend/` and `ai/` without the Mac; WEB-02 and WEB-03 reuse the shared modules |
| **Size** | Medium |
| **Model** | Opus 5.5 for tasks 2–5; Sonnet 5.5 is enough for the landing page and styling |
| **Needs a human for** | Granting camera permission; holding things in front of a webcam |

## Goal

A no-build static web app with shared API, lens, and debounce modules, and a simulator page that runs the complete cook-along loop — step cards, on-demand check, proactive watcher, spoken results — from a laptop webcam or uploaded photos, following exactly the same client rules as the iOS app.

## Read first

- [../README.md](../README.md) — layout, design rules, the camera note
- [../../docs/API-CONTRACT.md](../../docs/API-CONTRACT.md) §1 (conventions, errors), §2 (`Step`), §3 (check, watch, **client rules §3.3, stale rule §3.4**), §4 (sessions and events)
- [../../docs/TECH-SPEC.md](../../docs/TECH-SPEC.md) "Display spec"

## Tasks

### WEB-01.1 Shared configuration and API module

**Do**
- `shared/config.js`: `getConfig()` / `setConfig()` backed by `localStorage` (`gc.apiBase`, `gc.demoKey`, `gc.watchThreshold`, `gc.watchIntervalMs`). Default API base: the page's own origin when the path starts with `/app/`, otherwise `http://localhost:8000`.
- `shared/api.js`: `api.get(path)`, `api.postJson(path, body)`, `api.patchJson`, `api.del`, `api.postForm(path, formData)`; adds `X-Demo-Key`; parses the error envelope into `ApiError { status, code, message, retryable }`; network failures become `ApiError { code: "network" }`; per-call timeout through `AbortController` (**10 s check, 4 s watch**, 10 s default). Named helpers for each endpoint used here: `health`, `listRecipes`, `getRecipe`, `createSession`, `postEvent`, `check`, `watch`, `getSession`.
- A settings dialog component (gear icon) to edit base URL, key, threshold, interval; and the footer status strip from the README (API base, `ai_mode`, `storage`; red when fake; "unreachable" when `/health` fails).
- `shared/ui.css`: a small, clean base style (system font, dark theme, large tap targets).
- `index.html`: landing page with three large links (Simulator, Review, Monitor) and the status strip.

**Acceptance:** opening the landing page against a running backend shows `ai_mode` and `storage`; a wrong key shows a clear "unauthorized" state, not a blank page.

### WEB-01.2 Lens renderer

**Do** — `shared/lens.js` + `shared/lens.css`: `renderLens(el, screen)` where `screen` is a plain object with a `kind` field mirroring the iOS `LensScreen`:

```js
{ kind: "step",     card }                                 // card: { idx, total, title, keyLine, refImageUrl, watching: "active"|"paused"|"offline"|"off" }
{ kind: "checking", card }
{ kind: "pass",     headline }
{ kind: "fix",      card, headline, fix, proactive }
{ kind: "unsure",   headline, hint }
{ kind: "notice",   text }
{ kind: "done",     summary }
{ kind: "recipePick", titles, selected }
```

Fixed aspect-ratio black panel; bright text; counter + title on top, reference image, one line below, the watching dot; amber for fix, green for pass; never more than two text lines besides the title row. Scales with its container (it is small in the simulator and large in the monitor).

**Acceptance:** a hidden `?gallery=1` mode on the simulator page renders every kind side by side for visual review.

### WEB-01.3 Watcher debounce (pure) with tests

**Do** — `shared/debounce.js` exporting `createDebouncer({ threshold, requiredConsecutive = 2, muteMs = 20000 })` with `ingest(response, nowMs) -> response | null`, `dismissed(mistakeId, nowMs)`, `reset()`, `recordError() -> boolean` (true on the third consecutive error). Same rules as [API-CONTRACT §3.3](../../docs/API-CONTRACT.md#33-client-rules-for-the-watcher-ios-and-web-implement-these-identically): only `warn` with the same `mistake_id` and `confidence ≥ threshold` builds a streak; anything else breaks it; a muted id is silent for 20 s.

`tests/debounce.test.mjs` (Node's built-in test runner): warn+warn same id alerts on the second; different ids do not; warn-ok-warn does not; below threshold does not; mute and expiry; three errors.

**Acceptance:** `node --test web/tests/` passes.

### WEB-01.4 Simulator: session and on-demand check

**Do** — `sim/index.html`, `sim/sim.js`:
- **Frame sources**, switchable: *Webcam* (`getUserMedia`, prefer the rear camera on phones; show the live preview) and *Photo* (file picker or drag-and-drop; the chosen image is "what the camera sees" until replaced — ideal for running the AI owner's eval frames by hand).
- `grabFrame(maxLongEdge, quality) -> Blob` through a canvas (1280 / 0.8 for check, 512 / 0.6 for watch).
- Flow: recipe picker (published recipes) → create a session (`client: "web-sim"`, a device label such as "laptop webcam") → preload reference images → step card.
- A small state machine mirroring the iOS one: `primary` on a step → `checking` → result:
  - `pass` → green card, speak `spoken`, auto-advance after 2 s (or `primary` to advance now);
  - `fix` → amber card with the reference, speak; `primary` re-checks, `dismiss` returns;
  - `unsure` → card for 4 s, speak, return;
  - error → `notice` for 3 s ("Can't check right now" / "No connection"); one automatic retry after 1 s for 503/504.
- **Stale-result rule:** apply a response only if its `request_id` is the latest sent and its `step_id` is the current step.
- Post `step_change` events (`via: "tap"`), `session_end` on finishing; show the Done card with the summary from `GET /sessions/{id}`.
- Controls: buttons and keys — `Space` primary, `←` / `→` previous / next, `Esc` dismiss, `R` restart session.
- Speech with the browser's `speechSynthesis` (toggle to mute). A new result cancels an older utterance.
- A debug panel: last response JSON, `latency_ms`, model, request id.

**Acceptance:** against the backend in fake mode: first check on "Spread rice" shows the fix, second passes and advances; a nearly black photo (tiny JPEG) gives "Can't tell"; changing step during a slow check discards the result (test by throttling the network in dev tools).

### WEB-01.5 Simulator: proactive watcher

**Do**
- Loop: send a watch frame, wait for the answer, then wait the interval (default 2500 ms) **from the end of the call**; never overlap; fresh `request_id` each time; stale-result rule applies.
- Feed the debouncer; on an alert show the amber card with `proactive: true`, speak, post `warning_shown`. `primary` → check; `dismiss` → back to the step, post `warning_dismissed`, mute that id for 20 s. **A warning with no input for 12 s dismisses itself.**
- Paused while: not on a step card, a check is in flight, a result card is showing, the tab is hidden, no frame is available. Three consecutive errors → pause 15 s and grey dot. A `429` skips a tick.
- The dot on the card shows active / paused / offline. Steps without `watch_fors` make no calls.
- Debug panel additions: the last ten watch results (status, id, confidence, latency).

**Acceptance:** in fake mode the warning appears after the fake's 4th and 5th calls (two consecutive warns) and not before; dismissing mutes it; the call log shows no overlapping requests.

### WEB-01.6 First real loop

Once the backend runs with real Gemini (BE-03.1): use Photo mode with a correct frame and a mistake frame from the AI owner, then the webcam on real rice if available.

**Acceptance:** `STATUS.md` records what was tried and what came back, with latencies. This is gate G1's evidence if the iOS app is not there yet: tell the team.

## Verification

```bash
node --test web/tests/
python -m http.server 5173 --directory web      # then open http://localhost:5173/sim/
```

Walk through WEB-01.4 and WEB-01.5's acceptance by hand in a current Chrome or Safari.

## Out of scope

Gemini Live voice in the browser. Review page and monitor (next batches). Any build tooling or framework.

## When done

Update `STATUS.md`, commit `[web] WEB-01 foundation and simulator`, push, and post the simulator URL for the backend and AI owners.
