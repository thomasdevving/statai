# IOS-04 — Proactive watcher: loop, debounce, warning

| | |
|---|---|
| **Track** | `ios/` (Mac) |
| **Gate** | G2 |
| **Depends on** | IOS-03 |
| **Unblocks** | The demo's "it spoke first" moment |
| **Size** | Medium |
| **Model** | Opus 5.5 |
| **Needs a human for** | Trying it over real rice; judging whether it is annoying |

## Goal

While a step card is showing, the app quietly sends a low-res frame every 2.5 seconds and raises an amber warning **only** when the same known mistake is reported twice in a row with enough confidence. It never nags, never overlaps calls, and always shows whether it is watching.

## Read first

- [../../docs/API-CONTRACT.md §3.2–§3.4](../../docs/API-CONTRACT.md#32-post-watch-multipart--proactive-low-resolution) — **the rules in §3.3 are the specification for this batch.** The web simulator implements the same rules; behaviour must match.
- [../../docs/TECH-SPEC.md](../../docs/TECH-SPEC.md) "Cook-along" and display screen 5
- `ai/STATUS.md` → "Tuned values the clients need" (threshold, frame size) if already filled

## Tasks

### IOS-04.1 `WatchDebouncer` (pure logic)

**Do** — `GhostChef/Watcher/WatchDebouncer.swift`, a value type with no I/O and no clock of its own:

```swift
struct WatchDebouncer {
    var threshold: Double = 0.7
    var requiredConsecutive = 2
    var muteSeconds: TimeInterval = 20
    mutating func ingest(_ r: WatchResponse, at now: Date) -> WatchResponse?   // returns the response to alert on, or nil
    mutating func dismissed(mistakeID: String, at now: Date)                   // starts the mute window
    mutating func reset()                                                       // on step change
    mutating func recordError() -> Bool                                         // true when 3 errors in a row → caller pauses 15 s
}
```

Rules: a streak counts only `warn` responses with the **same** `mistake_id` and `confidence ≥ threshold`; an `ok`, a different id, a low confidence, or an error breaks the streak; a muted id never alerts; a success resets the error count.

**Acceptance — unit tests:** warn+warn (same id) alerts on the second; warn(a)+warn(b) does not; warn+ok+warn does not; a below-threshold warn does not count; after `dismissed`, the same id is silent for 20 s and alerts again afterwards; three errors return `true`; `reset` clears everything.

### IOS-04.2 `WatcherLoop`

**Do** — `GhostChef/Watcher/WatcherLoop.swift`, an actor or main-actor class driven by `CookSession`:
- While **active**: grab a frame (`maxLongEdge` 512, quality 0.6 — or the tuned values), send `/watch` with a fresh `request_id`, wait for the answer, then wait until **2.5 s after the answer** before the next tick. Never two calls in flight.
- Apply the stale-result rule to every response.
- Feed responses and errors to the debouncer. On an alert, call back into `CookSession`.
- Client timeout 4 s (already set in `APIClient`). A `429` with `retryable` → skip a tick, not an error streak.
- Three consecutive errors → pause 15 s, indicator `.offline`.
- Injected clock; cancellable; no retain cycles; stops completely when the session ends.

**Pause conditions** (indicator `.paused`): lens is not `.step`; a check is in flight; a pass / fix / warning / unsure / notice is showing; the user is talking to Live (`talking`); the app is in the background; the frame source is unavailable.

**Acceptance — unit tests with `MockAPI` and a test clock:** calls never overlap; the interval is measured from the end of the previous call; the loop is paused in each listed condition and resumes afterwards; a step change resets the debouncer and drops the in-flight response.

### IOS-04.3 Warning behaviour in `CookSession`

**Do**
- On an alert: lens = `.fix(card, headline, fix, proactive: true)`; speak `spoken` (`.result` priority); post `warning_shown` with the `mistake_id`.
- In a proactive warning: `primary` → run a check (the natural "I fixed it, look now"); `dismiss` → back to `.step`, post `warning_dismissed`, start the 20 s mute for that id.
- A proactive warning clears itself when a check passes.
- Auto-dismiss after 12 s without input (back to `.step`, counts as dismissed) so a wearer who simply fixes the problem is not stuck behind a card.

**Acceptance:** unit tests for each path; events are posted once each.

### IOS-04.4 Indicator and settings

**Do**
- The step card's dot: green `● watching`, grey when paused or offline (IOS-03's `WatchIndicator`).
- Settings: watcher on/off, threshold slider (0.5–0.95), interval (2.0–5.0 s), a small live readout of the last ten watch results (status, id, confidence, latency) for tuning at the table.
- A recipe step with no `watch_fors` shows the dot as off and makes no calls.

**Acceptance:** toggling and changing values takes effect without restarting the session.

### IOS-04.5 Try it on real rice *(human)*

With real Gemini: spread a correct layer (expect silence for at least a minute), then pile on rice (expect a warning). Then fix it (expect silence, and a pass on check).

**Acceptance:** `STATUS.md` records: time from mistake to warning, any false warnings during the correct phase, the threshold used. If it is too jumpy or too slow, tell the AI owner with the readout values; do not hand-tune the prompt side yourself.

## Verification

```bash
cd ios && xcodegen generate
xcodebuild -project GhostChef.xcodeproj -scheme GhostChef -destination 'platform=iOS Simulator,name=<an available iPhone>' test
```

## Out of scope

Changing the watch prompt or model (`ai/`). Server-side in-flight guard (`backend/`).

## When done

Commit `[ios] IOS-04 proactive watcher`, push.
