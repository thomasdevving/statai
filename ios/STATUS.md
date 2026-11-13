# `ios/` status

> Updated by the track owner after every batch. The pitch and the docs take device claims **only** from this file. Write only what was run and observed.

## Batches

| # | Batch | Status | Date / commit | Notes |
|---|---|---|---|---|
| 01 | Project foundation | PARTIAL | 2026-11-14, commit `[ios] IOS-01 project foundation` | **Pass (simulator, run 2026-11-14):** IOS-01.1 build; IOS-01.3 decoding tests (contract **v2.0** examples + error envelope + fixture); IOS-01.4 `URLProtocol` stub tests (header, multipart, 429, 504, timeouts); frame encoding at 1280/0.8 and 512/0.6 within limits on the **still test image**; 44/44 tests green (rerun 2026-11-14 after the fixture sync). **Not yet run (needs a human with the iPhone):** permission prompts (01.2), "Grab frame" on the real camera (01.5), recipe list + health panel against a running backend (01.6). Recipe list seen in the simulator against the **bundled fixture only**; backend mode seen showing its "Couldn't load recipes" state (no backend running). Bundled fixture and its 6 placeholder reference images are synced from `ai/fixtures` (AI-01) with `ios/scripts/sync-fixture.sh`; a test checks every step's image resolves. UI follows the apple-design guidance (system type, press feedback on touch-down, critically damped springs, Reduce Motion fallbacks). |
| 02 | DAT glasses spike | PARTIAL (mock only) | 2026-11-14 | **Done:** 02.1 SDK `meta-wearables-dat-ios` pinned **exact 1.0.1** (products MWDATCore, MWDATCamera, MWDATDisplay, MWDATInputs, MWDATMockDevice), Info.plist per the SDK getting-started guide (URL scheme `ghostchef`, `MWDAT` dict in Developer Mode, background modes incl. `external-accessory`, accessory protocol, Bonjour), `GlassesManager` + Settings → Glasses Lab (02.5 kept). 02.2 proofs **a–e PASS on MockDeviceKit** (see Device facts). Device build + 46/46 unit tests green. **Not done (need hardware / a human):** booth questions, 02.3 real-glasses proofs a–h + framing, 02.4 the four decisions. Mock run on the iPhone itself not done (phone was unreachable). Analytics opt-out not set (team to decide). |
| 03 | Cook-along core | NOT STARTED | | |
| 04 | Proactive watcher | NOT STARTED | | |
| 05 | Gemini Live voice | NOT STARTED | | |
| 06 | Glasses integration | NOT STARTED | | |
| 07 | Resilience and demo mode | NOT STARTED | | |
| 08 | Chef mode recording | NOT STARTED | | |

Status words: `DONE`, `DONE (fake)`, `PARTIAL`, `BLOCKED`, `NOT STARTED` (defined in docs/PLAN.md §8).

## Hardware access (answers from the Meta booth)

| Question | Answer | Asked when / who answered |
|---|---|---|
| Which glasses can we use (Display / Gen 2)? | — | |
| For how long, and can we hold a pair for the demo slot? | — | |
| Who supports the iOS DAT SDK on site? | — | |
| Is a Wearables Developer Center project provided, or do we register our own? | — | |
| Do Neural Band gestures reach a DAT app? | — | |

## Environment actually used

| Item | Value |
|---|---|
| Mac / Xcode version | Mac17,9, macOS 26.6.2 / **Xcode 27.3 beta (27C5020n)** at `~/Downloads/Xcode-beta.app`, used via `export DEVELOPER_DIR=~/Downloads/Xcode-beta.app/Contents/Developer` (the active developer dir is still Command Line Tools). XcodeGen 2.46.0. Simulator: iPhone 18 Pro, iOS 27.3 |
| iPhone model / iOS version | iPhone 18 Pro ("iPhone van Thomas"), iOS 27.0.1. Free Personal Team signing works; local bundle id `com.thomasnguyen.ghostchef` (set in untracked Secrets.xcconfig; `com.ghostchef.app` was taken). App installed and launched 2026-11-14 |
| Glasses model / firmware | — |
| DAT SDK version pinned | `meta-wearables-dat-ios` **1.0.1** (exactVersion in `project.yml`, resolved 2026-11-14) |
| Meta AI app version; Developer Mode on? | — |
| Backend URL the app points at | None yet. Build default `http://localhost:8000`; set the real one in `Config/Secrets.xcconfig` or in the app's Settings |

## Device facts (IOS-02)

`PASS`, `FAIL`, or `NOT TESTED`, each with what was observed. Tested on MockDeviceKit and tested on real glasses are different columns.

| # | Proof | MockDeviceKit | Real glasses | Observed detail |
|---|---|---|---|---|
| a | App registers with the Meta AI app and sees the device | PASS | NOT TESTED | Mock: kit enabled pre-registered; registration stream `unavailable → registered`; device "Simulated Meta Ray-Ban Display #1", type `metaRayBanDisplay`, link connected, compatible, `supportsDisplay` true. Meta AI registration itself not exercised (mock skips it). |
| b | Camera permission granted; one frame arrives as JPEG | PASS | NOT TESTED | Mock: permission granted by the kit; stream `raw`, `.high`, 24 fps → `waitingForDevice → starting → streaming`; frame 720×1280 → JPEG 720×1280, 125 kB; 1.0–1.6 s from request (includes stream start-up) over 4 runs. |
| c | Display shows an image and two lines of text in one view | PASS | NOT TESTED | Mock display preview shows "3/6  Spread rice" heading + reference image + key line. **Found:** a portrait 720×1280 still with `ImageSize.fill` spans the card width and pushes the key line off; fixed by sending a 16:10 centre crop. Display DSL text colours are only `primary`/`secondary` (no amber/green) in SDK 1.0.1. |
| d | Camera stream and display run at the same time | PASS | NOT TESTED | Mock: 60 s with stream running and card re-sent every 5 s: fps per 5 s window 24.0–24.2 throughout, 12/12 card updates sent, 0 failures. |
| e | An input from the wearer reaches the app (which kinds?) | PASS | NOT TESTED | Mock: `addInputs(InputsConfiguration())` attached; injected `select`, `nav(.right)`, `back` from source `captouch` all arrived as `InputEvent`s. Input card with a Check/Next `ButtonGroup` renders. Display-button clicks not exercised on mock. SDK docs: Inputs is experimental and must be enabled for the app in Wearables Developer Center for real devices — unverified. |
| f | Phone audio in/out routes through the glasses while streaming video | NOT TESTED | NOT TESTED | |
| g | Measured: stream resolution, frames per second, time from request to JPEG | NOT TESTED | NOT TESTED | Mock numbers only (720×1280, 24 fps, ~1–1.6 s to first JPEG) describe the sample-video feed, not glasses; not a measurement of the device. |
| h | 60 s of camera stream + mic recorded to an MP4 on the phone; plays back with sound in sync | NOT TESTED | NOT TESTED | |

Mock runs: MockDeviceKit run 2026-11-14 on the iPhone 18 Pro simulator (iOS 27.3), SDK 1.0.1, mock **Meta Ray-Ban Display**, camera feed = `mock-feed.mp4` (HEVC sample video made from the step-3 placeholder; no real camera).

Looking down at a board: is the work in frame? —

## Decisions taken from the spike

| Topic | Decision | Reason |
|---|---|---|
| Lens layout (image + text, or fallback) | — | |
| Input mapping for check / next / back / show me | — | |
| Audio route for results and voice | — | |
| Frame capture method and size for `/check` and `/watch` | — | |
| Chef mode: step-mark input and recording mic | — | |

## Recovery tests (IOS-07)

| Test | Expected (ARCHITECTURE §6) | Observed | Date |
|---|---|---|---|
| Camera permission denied, then granted | Explanation on phone; recovers | — | — |
| Glasses disconnected mid-step, then back | Spoken notice; resumes on same step | — | — |
| Airplane mode 20 s during a step | Grey dot; cards still work; recovers | — | — |
| Backend stopped during a check | "Can't check right now" | — | — |
| Check pressed five times fast | One verdict shown | — | — |
| Step changed while a check is pending | Pending result discarded | — | — |
| Camera covered, then check | "Can't tell" | — | — |
| App killed and restarted mid-session | Clean restart | — | — |
| Live dropped while asking | Mic unavailable; rest works; reconnects | — | — |
| Display unavailable | Audio-only mode | — | — |

## End-to-end runs on the glasses

| Date | Glasses | What ran (check / watcher / voice / display) | Result | Recorded? |
|---|---|---|---|---|
| — | — | — | — | — |

## Chef mode takes (IOS-08)

| Date | Glasses / firmware | Source (glasses / phone) | Duration | Size | Resolution, fps | Marks | Upload (TUS / PUT), time | Reached `review`? |
|---|---|---|---|---|---|---|---|---|
| — | — | — | — | — | — | — | — | — |

## Needs from other tracks

- **backend/ (BE-01):** no backend was reachable, so the list and health panel are unverified against a server. Need the LAN or Railway URL and the demo key.
