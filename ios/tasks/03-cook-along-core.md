# IOS-03 — Cook-along core: state machine, lens model, on-demand check

| | |
|---|---|
| **Track** | `ios/` (Mac) |
| **Gate** | G2 |
| **Depends on** | IOS-01. BE-01 reachable (fake AI is fine to build against; BE-03 for real verdicts). |
| **Unblocks** | IOS-04, IOS-05, IOS-06 |
| **Size** | Large |
| **Model** | Opus 5.5 |
| **Needs a human for** | Running it on the phone over real rice once real verdicts are available |

## Goal

The core loop on the iPhone, using the phone camera and an on-screen lens preview: pick a recipe → step card with the chef's reference → check → pass / fix / can't tell → fix it → re-check passes → next step → done. Built so the glasses become a second renderer and a second frame source later, with no change to this logic.

## Read first

- [../README.md](../README.md) — "Core design"
- [../../docs/API-CONTRACT.md](../../docs/API-CONTRACT.md) §3.1, §3.4 (stale-result rule), §4 (sessions and which events the client posts), §5.3 (who speaks what)
- [../../docs/TECH-SPEC.md](../../docs/TECH-SPEC.md) "Display spec" — screens 1–5 and 9, the two-line rule, bright-on-black
- [../../docs/ARCHITECTURE.md §6](../../docs/ARCHITECTURE.md#6-failure-behaviour)

## Tasks

### IOS-03.1 Lens model and inputs

**Do** — `GhostChef/Session/LensScreen.swift`, `CookInput.swift`:

```swift
struct StepCard: Equatable { let idx: Int; let total: Int; let title: String; let keyLine: String
                             let refImage: ImageRef?; let watching: WatchIndicator }   // .active .paused .offline .off
enum LensScreen: Equatable {
    case recipePick(titles: [String], selected: Int)
    case step(StepCard)
    case checking(StepCard)
    case pass(headline: String)
    case fix(StepCard, headline: String, fix: String, proactive: Bool)   // proactive = raised by the watcher
    case unsure(headline: String, hint: String)
    case talking(phase: TalkPhase, caption: String)      // .listening .answering   (IOS-05)
    case showMe(StepCard)                                 // clip or still            (nice-to-have)
    case timer(remainingS: Int, StepCard)                 // nice-to-have
    case done(SessionSummary?)
    case notice(String)                                   // "No connection", "Can't check right now"
}
enum CookInput: Equatable { case primary, next, previous, showMe, dismiss, repeatInstruction }
```

- Every case also has a **spoken form** (`var spokenText: String?`) used by the audio-only mode: e.g. `.step` → "Step 3 of 8. Spread rice. Thin layer, leave two centimetres at the top."

**Acceptance:** compiles; unit test for the spoken forms.

### IOS-03.2 `CookSession` state machine

**Do** — `GhostChef/Session/CookSession.swift`, `@MainActor @Observable`, dependencies injected as protocols (`GhostChefAPI`, `FrameSource`, `SpeechOutput`, a `Clock`).

State: recipe, current step index, `lens: LensScreen`, session id, the latest check `request_id`, a pending-check task.

| When | Input / event | Then |
|---|---|---|
| start(recipe) | — | Download and cache all reference images; `POST /sessions`; lens = `.step(1)`; speak the step (short form) |
| `.step` | `primary` | lens = `.checking`; grab a frame (`maxLongEdge` 1280, quality 0.8); new `request_id`; `POST /check` |
| `.checking` | `primary` again | Ignored (one check at a time) |
| check result (not stale) `pass` | — | lens = `.pass`; chime; speak `spoken`; after **2 s** auto-advance (`via: auto`) |
| `.pass` | `primary` | Advance now |
| check result `fix` | — | lens = `.fix(card, headline, fix, proactive: false)`; speak `spoken` |
| `.fix` | `primary` | Re-check (same flow) |
| `.fix` | `dismiss` | Back to `.step` |
| check result `unsure` | — | lens = `.unsure`; speak `spoken`; after 4 s back to `.step` |
| check error | — | `.notice("Can't check right now")` (or "No connection" for a network error) for 3 s, speak it, back to `.step`. For `503`/`504`: one automatic retry after 1 s before showing the notice |
| any step screen | `next` / `previous` | Change step (bounds-checked); cancel any pending check; lens = `.step`; post `step_change` with `via`; speak the new step |
| last step | `next` or auto-advance | `session_end` event; fetch `GET /sessions/{id}`; lens = `.done(summary)` |
| any | `repeatInstruction` | Speak the full `instruction` |

Rules:
- **Stale-result rule (§3.4):** a check response is applied only if its `request_id` equals the latest one sent **and** its `step_id` is the current step. Otherwise it is dropped silently. Changing step invalidates the pending request id.
- Session events are fire-and-forget: a failed event post is logged and never blocks the UI.
- `isIdleTimerDisabled = true` while a session is active.
- All timers go through the injected clock so tests do not sleep.

**Acceptance — unit tests with `MockAPI` and a test clock:**
- fix → re-check → pass → auto-advance after 2 s;
- `primary` during `.pass` advances immediately;
- a slow check response arriving after `next` is ignored (lens stays on the new step);
- two rapid `primary` inputs produce one `/check` call;
- `unsure` returns to the step after 4 s;
- a `504` is retried once, then shows the notice;
- finishing the last step posts `session_end` and shows `.done`.

### IOS-03.3 Phone lens preview

**Do** — `GhostChef/Lens/PhoneLensView.swift`: renders any `LensScreen` in a fixed-aspect black panel that imitates the lens. Follow the Display spec: bright elements on black, at most two short text lines, step counter and title on top, reference image in the middle, key line below, the watching dot. Amber for fix / warning, green for pass. Large type: it must be readable at a glance and on the demo monitor.

`CookView` layout on the phone: the lens preview on top; below it the live camera preview (small) and operator buttons mapped to `CookInput` (`Check / Next` = primary, `◀`, `▶`, `Show me`, `Dismiss`). The buttons stay in the app permanently: they are the operator's remote on demo day.

**Acceptance:** SwiftUI previews for every `LensScreen` case; on the phone the whole loop is drivable with the buttons.

### IOS-03.4 Speech output and chime

**Do** — `GhostChef/Voice/SpeechOutput.swift`:
- `protocol SpeechOutput { func speak(_ text: String, priority: SpeechPriority); func stop(); var isSpeaking: Bool { get } }` with `.result` (interrupts anything) and `.info` (queued, dropped if a result arrives).
- Implementation with `AVSpeechSynthesizer`, an English voice, slightly faster than default. A short chime sound for pass (bundle a small audio file or use a system sound).
- Configure `AVAudioSession` once (`playback` for now; IOS-05 switches to `playAndRecord`).
- A mute toggle in Settings.

**Acceptance:** results are spoken on the phone; a new result cuts off an older sentence; unit tests use a fake `SpeechOutput` to assert what was spoken.

### IOS-03.5 Image cache and offline cards

**Do** — `ImageCache`: on session start download every step's `ref_image_url` to disk (keyed by step id); the lens reads only from the cache. If a download fails the card shows without an image. Step cards, navigation, and `repeatInstruction` must work with the network off.

**Acceptance:** start a session, turn on airplane mode, navigate all steps: images still show; a check shows "No connection".

### IOS-03.6 Done screen

**Do** — `.done(summary)`: "Done ✓" plus two numbers from the summary (steps passed first try, fixes caught). A "Restart session" button that resets everything in one tap (the demo reset).

**Acceptance:** numbers match `GET /sessions/{id}` for a run with one fix.

### IOS-03.7 Run it for real

With the backend on real Gemini (BE-03.1) and real rice: check a correct layer, a clearly wrong layer, and a covered camera. Note the verdicts and the felt latency.

**Acceptance:** `STATUS.md` records the run honestly (which verdicts were right, time from pinch to result as felt and as reported in `latency_ms`). Mark the batch `DONE (fake)` if only fake AI was available.

## Verification

```bash
cd ios && xcodegen generate
xcodebuild -project GhostChef.xcodeproj -scheme GhostChef -destination 'platform=iOS Simulator,name=<an available iPhone>' test
```

Then the manual loop on the iPhone.

## Out of scope

The watcher (IOS-04). Voice input (IOS-05). The glasses (IOS-06). "Show me" clips and the timer are nice-to-have: leave their `LensScreen` cases unrendered beyond a placeholder unless everything else is done.

## When done

Commit `[ios] IOS-03 cook-along core`, push, show the loop at the next sync.
