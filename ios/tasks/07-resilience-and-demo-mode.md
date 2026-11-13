# IOS-07 — Resilience, audio-only mode, demo mode

| | |
|---|---|
| **Track** | `ios/` (Mac) |
| **Gate** | G4. No new features after G3; this batch makes the existing ones survive a stage. |
| **Depends on** | IOS-03 at minimum; IOS-04, 05, 06 as far as they exist |
| **Unblocks** | Demo readiness; the "UX, accessibility, and trust" quarter of the Meta rubric |
| **Size** | Medium |
| **Model** | Opus 5.5; Sonnet 5.5 is enough for copy and status edits |
| **Needs a human for** | Triggering every failure by hand; rehearsing |

## Goal

Every failure in [ARCHITECTURE §6](../../docs/ARCHITECTURE.md#6-failure-behaviour) behaves as documented on the real device; the experience works with no display and with no audio; and the person running the demo can reset and recover in seconds.

## Read first

- [../../docs/ARCHITECTURE.md §6](../../docs/ARCHITECTURE.md#6-failure-behaviour) — the specification for this batch
- [../../docs/PRODUCT.md §8](../../docs/PRODUCT.md#8-trust-consent-accessibility)
- [../../docs/DEMO-AND-SUBMISSION.md](../../docs/DEMO-AND-SUBMISSION.md) §2, §4, §5
- `ios/STATUS.md` → "Recovery tests" table (you fill it in)

## Tasks

### IOS-07.1 Audio-only mode

**Do**
- A third consumer of `CookSession.lens`: `SpokenLens`. When the display is unavailable (`supportsDisplay` false, display failed, or "Audio-only" forced in Settings) it speaks each screen's `spokenText` on change: step title + key line on a step change, results as before, "Checking" as a short tone rather than words.
- Results are spoken in every mode already; this adds the step cards and notices.
- The mode is chosen automatically and shown in Settings and on the phone.

**Acceptance:** with the display forced off, a complete session can be followed with eyes closed. This is also how the app runs on displayless (Gen 2) glasses.

### IOS-07.2 Display-only mode

**Do** — a "Mute speech" setting and automatic behaviour when no audio route is usable: every result already shows headline + fix; make sure nothing is conveyed by sound alone (the pass chime has the green ✓; a warning has the amber card). Voice Q&A shows "Voice unavailable".

**Acceptance:** a complete session with the phone and glasses muted loses no information.

### IOS-07.3 Connectivity and server failures

**Do** — verify and fix against the table:
- Network offline: grey dot, cards and images from cache, check → "No connection", automatic recovery when back (use `NWPathMonitor`).
- Backend unreachable: Settings Health panel shows it; the session screen shows a one-line banner on the phone; the lens shows only the grey dot.
- `429`: watcher backs off 10 s; check shows "Can't check right now".
- Base URL switchable mid-session for the emergency laptop: Settings keeps a short list of saved servers ("Production", "Laptop") and switching re-checks `/health`.

**Acceptance:** rows 3–4 of the recovery table.

### IOS-07.4 Device and permission failures

**Do**
- Camera or microphone permission denied: a clear phone screen with a button to Settings; the lens says "Camera off". The app keeps working for what it can.
- Glasses disconnect mid-session: speak "Glasses disconnected" (phone speaker), keep the session state, offer "Continue with phone camera" on the phone; when the glasses return, resume on the same step with the glasses' camera and re-send the current lens card.
- Frame source returns no frame: watcher pauses; check says "Camera not ready".
- App backgrounded: watcher pauses; on return, state is intact.
- App killed: on relaunch, a clean recipe list (no half-restored session); the old session simply has no `session_end`.

**Acceptance:** rows 1, 2, 7, 8 of the recovery table.

### IOS-07.5 Input robustness

**Do** — verify with tests where possible: five rapid `primary` inputs → one check; step change during a pending check → result discarded; inputs during `.pass` and `.notice` behave as specified; no input can leave the lens on a stale screen (every timed screen has a path back to `.step`).

**Acceptance:** rows 5 and 6 of the recovery table; unit tests exist for both.

### IOS-07.6 Demo mode

**Do** — a "Demo" section in Settings:
- **Restart session** (also on the Done screen): one tap, back to step 1 of the same recipe, new session id, watcher and voice reset.
- **Start at step** picker (so the demo can begin at "Spread rice").
- **Keep awake**, brightness hint, Do Not Disturb reminder.
- **Operator overlay** on the phone's `CookView` (toggle): last watch results, last check latency, Live state, glasses state, frame age. This is for the operator, never mirrored to the lens.
- Saved servers (from IOS-07.3) and the tuned watch threshold from `ai/STATUS.md` preset.
- A visible build label (git short hash + date) so the team knows which build is on the phone.

**Acceptance:** from a finished run to the first card of a new run in under 15 seconds, by someone other than the developer.

### IOS-07.7 Recovery tests and rehearsal *(human)*

- Run every row of `STATUS.md` → "Recovery tests" on the real setup. Write what happened and the date.
- Three consecutive clean demo runs operated by a teammate who did not write the app (gate G4).
- Install the final build on the phone, note the build label, and **do not reinstall after this** unless a fix is agreed at a sync (a free Apple developer profile also expires after seven days — irrelevant for the weekend, but do not switch signing teams now).

**Acceptance:** the table has no dashes; the three runs are noted with their date and who operated.

## Verification

```bash
cd ios && xcodegen generate
xcodebuild -project GhostChef.xcodeproj -scheme GhostChef -destination 'platform=iOS Simulator,name=<an available iPhone>' test
```

## Out of scope

New features. Anything in the cut order that was already cut.

## When done

Update `STATUS.md` (all tables), commit `[ios] IOS-07 resilience and demo mode`, push, and give the `web/` owner the final, exact list of what runs on the glasses.
