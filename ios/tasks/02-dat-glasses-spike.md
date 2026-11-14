# IOS-02 — DAT glasses spike: prove the device path

| | |
|---|---|
| **Track** | `ios/` (Mac) |
| **Gate** | G1 — this is the project's highest-risk unknown. Start as soon as IOS-01 builds; start on MockDeviceKit if no glasses are available yet. |
| **Depends on** | IOS-01. A pair of glasses for the "real" column. |
| **Unblocks** | IOS-06; the display / input / audio decisions for the whole product |
| **Size** | Medium, with waiting time for hardware |
| **Model** | Opus 5.5, with Meta's `mwdat-ios` plugin and docs MCP installed (see [../README.md](../README.md#metas-agent-tooling-for-the-dat-sdk-install-before-ios-02)) |
| **Needs a human for** | Getting glasses from the Meta booth, pairing, Developer Mode, wearing them, asking the booth questions |

## Goal

Seven small proofs on the actual borrowed device, each recorded as PASS / FAIL / NOT TESTED with what was observed. Throwaway UI is fine; the knowledge is the deliverable. At the end, four decisions are written down: lens layout, input mapping, audio route, frame capture.

**Do not build product features here.** One screen, `GlassesLabView`, with a button per proof and a log.

## Read first

- [../../docs/ARCHITECTURE.md §5.1](../../docs/ARCHITECTURE.md#51-meta-glasses-and-dat) — assumptions A1–A13 and what documentation did and did not confirm
- [../../docs/TECH-SPEC.md](../../docs/TECH-SPEC.md) "Display spec", "Inputs", "Confirmed with Meta", "Open risks"
- The SDK's own material, through the plugin / docs MCP / repository: getting started, permissions and registration, camera streaming, display, inputs, MockDevice testing, session lifecycle, and the sample apps under `samples/`. **Read the sample that is closest to each proof before writing code.**

Facts read in the changelog on 2026-11-13 (names may differ in detail; verify): Swift Package `https://github.com/facebook/meta-wearables-dat-ios`, latest tag `1.0.1`; registration through `Wearables.handleUrl(_:onRegistrationRequest:)`; device management through `DeviceSession`; camera `Stream` with `StreamingResolution` (medium 504×896, high 720×1280) and `VideoCodec` (`raw`, `hvc1`); `VideoFrame` exposes a raw `CMSampleBuffer`; display through `MWDATDisplay` (`DeviceSession.addDisplay(...)`, `FlexBox`, `Text`, `Image`, `Icon`, `Button`, `ButtonGroup`, `VideoPlayer`, `Display.clearDisplay()`); `DeviceType.supportsDisplay`; experimental `MWDATInputs` reporting `InputEvent` values; `MockDeviceKit` with `pairGlasses(model:)`, a phone-camera mock feed, captouch simulation, and a mock display preview.

## Before coding *(human, at the Meta booth — do this tonight)*

Ask, and write the answers in `STATUS.md` → "Hardware access":

1. Can we borrow a **Display** pair? When, for how long, can we reserve one for our demo slot?
2. Who here knows the **iOS** DAT SDK? (The listed mentor is an Android DAT mentor.)
3. Is there a shared Wearables Developer Center project / app id for the event, or do we register our own? Anything special for loan devices (accounts, Developer Mode, region)?
4. Do **Neural Band** gestures reach a third-party DAT app on iOS, or only display buttons / captouch / voice?
5. Is "camera stream + display UI + Bluetooth audio at the same time" known to work on iOS? Any limits (resolution, frame rate, thermal)?

## Tasks

### IOS-02.1 Add the SDK

**Do**
- Install the agent tooling (README). Add the Swift Package to `project.yml`, **pinned to exact version 1.0.1** (or the newest tag if the booth says to use another; record which).
- Add the products the proofs need (core, camera, display, inputs, mock device — take the exact product names from the package manifest).
- Add whatever the SDK documentation requires in Info.plist: the `MWDAT` dictionary, app identifiers, URL scheme for the registration callback, background modes, Bluetooth / external-accessory entries. Opt out of SDK analytics if the team prefers (`MWDAT > Analytics > OptOut`).
- Create `GhostChef/Glasses/GlassesManager.swift` (owns SDK setup, registration, device state) and `GlassesLabView.swift` (reachable from Settings → "Glasses Lab").

**Acceptance:** the app builds with the package; the Lab screen opens.

### IOS-02.2 Proofs on MockDeviceKit (no hardware needed)

Do each proof first against the mock device, to learn the API shape:

| # | Proof | Lab button does | PASS when |
|---|---|---|---|
| a | Registration and device discovery | Enables the mock kit, pairs mock Display glasses, lists devices and their state | A mock device appears with `supportsDisplay` true |
| b | Camera frame | Requests camera permission, starts a stream with the phone-camera mock feed, converts one frame to JPEG | A JPEG is shown in the Lab with its size |
| c | Display card | Sends one view: an image (a bundled reference still) plus two lines of text, bright on black | The mock display preview shows it |
| d | Camera + display together | Runs (b) and (c) at once for 60 s, updating the card text every 5 s | Both keep working |
| e | Input | Subscribes to inputs; shows a `ButtonGroup` with two buttons; simulates captouch tap | The Lab log prints each event |

**Acceptance:** `STATUS.md` → Device facts, MockDeviceKit column filled for a–e.

### IOS-02.3 Proofs on the real glasses *(human wears them)*

Pair through the Meta AI app, enable Developer Mode, register the app. Repeat a–e on the device, then:

| # | Proof | How | Record |
|---|---|---|---|
| c′ | Layout limits | Try: image + 2 text lines; image size and aspect that looks right; longest readable line; amber vs green text; what black looks like (should be transparent) | A photo through the lens if possible; the limits found |
| e′ | Real inputs | Try every input the device offers: Neural Band pinch / double pinch / swipe, captouch tap / hold, display button selection | Which ones produce an event in our app, and what the event looks like |
| f | Audio route | With the camera stream running, play a spoken sentence (`AVSpeechSynthesizer`) and record 3 s from the microphone with `AVAudioSession` category `playAndRecord`, mode `voiceChat`, option `allowBluetooth` | Does speech come out of the glasses? Is the active input the glasses' mic (print `currentRoute`)? Does the video stream survive? |
| g | Measurements | Log for 30 s: frames per second received, frame resolution, time from "want a frame" to JPEG bytes; note heat or battery warnings | Numbers |
| h | Record for Chef mode | With the camera stream running, write 60 s of frames plus microphone audio to an MP4 with `AVAssetWriter`; play it back on the phone | Does it play, is the sound in sync, which mic was used, file size, any dropped frames or heat. De-risks IOS-08 (risk R-19) |
| — | Framing | Look down at a board at arm's length with two slices of bread on it. Grab frames standing and sitting | Is the whole board (both slices) in frame? Save 3 frames for the AI owner |

**Acceptance:** `STATUS.md` → Device facts, real-glasses column filled for a–h with observed detail, glasses model, firmware, SDK version, date; "Environment actually used" complete. Send the saved frames to the AI owner (they answer risk R-02 for the real camera).

### IOS-02.4 Decide

Write the four decisions in `STATUS.md` → "Decisions taken from the spike", choosing from these ladders (top = as specified):

| Topic | Options, best first |
|---|---|
| **Lens layout** | (1) reference image + title + key line in one view → (2) text card, image shown only on "show me" / on a fix → (3) no display: audio-only, lens mirrored on the demo monitor |
| **Inputs** | (1) Neural Band pinch = check/next, swipe = prev/next, double pinch = show me → (2) display `ButtonGroup` ("Check" / "Next") selected with whatever the device supports → (3) captouch tap = check, hold = next → (4) voice commands only, plus the phone as an operator remote |
| **Audio** | (1) glasses mic + speakers for Live and results → (2) glasses speakers, phone mic → (3) phone speaker and mic |
| **Frames** | (1) continuous stream, latest frame on demand → (2) photo capture per check if the stream is unreliable (watcher then runs slower or is cut) |

Tell the team the result at the next sync. If lens layout or inputs land on a fallback, the pitch wording changes: tell the `web/` owner.

**Acceptance:** four decisions with reasons, plus the Chef-mode row (which input marks a step while recording, which mic records); the team has been told.

### IOS-02.5 Leave the Lab in place

Keep `GlassesLabView` working. It is the fastest way to diagnose the device on demo day.

## Verification

```bash
cd ios && xcodegen generate
xcodebuild -project GhostChef.xcodeproj -scheme GhostChef -destination 'generic/platform=iOS' build
```

Everything else is verified by hand on the device and written in `STATUS.md`.

## Out of scope

Wiring the real cook-along to the glasses (IOS-06). Gemini Live (IOS-05).

## When done

Commit `[ios] IOS-02 DAT spike and device facts`, push. Status is `DONE` only if the real-glasses column is filled; with mock results only it is `PARTIAL (mock only)`.
