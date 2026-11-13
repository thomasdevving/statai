# IOS-01 — Project foundation: Xcode project, models, API client, phone camera

| | |
|---|---|
| **Track** | `ios/` (Mac) |
| **Gate** | G0 |
| **Depends on** | The fixture from AI-01 (copy it). BE-01 for live data — until it is up, use the bundled fixture. |
| **Unblocks** | Every other iOS batch |
| **Size** | Medium |
| **Model** | Opus 5.5 |
| **Needs a human for** | Selecting the signing team in Xcode, running on the iPhone, granting camera permission |

## Goal

A SwiftUI app that builds from a generated Xcode project, decodes every contract type, talks to the backend, shows the recipe list, and can grab a JPEG frame from the iPhone camera behind the `FrameSource` protocol. No cook-along logic yet.

## Read first

- [../README.md](../README.md) — layout and the core design section
- [../../docs/API-CONTRACT.md](../../docs/API-CONTRACT.md) §1 (conventions, errors), §2 (recipes, the `Step` object), §3 (check / watch shapes), §4 (sessions), §5 (live token shape)
- `ai/fixtures/sushi_recipe.json`

## Tasks

### IOS-01.1 Generated Xcode project

**Do**
- `ios/project.yml` for XcodeGen: app target `GhostChef` (bundle id `com.ghostchef.app` — change if your team id needs another), deployment target **iOS 17.2**, Swift 5.10 or newer, SwiftUI lifecycle; unit-test target `GhostChefTests`; sources from `GhostChef/` and `GhostChefTests/`; `Config/Config.xcconfig` as the base configuration.
- `Config/Config.xcconfig`: `#include? "Secrets.xcconfig"`, defaults for `API_BASE_URL` and `DEMO_API_KEY`.
- `Config/Secrets.example.xcconfig` with the two keys. Note in a comment that `//` starts a comment in xcconfig files, so a URL is written `http:/$()/192.168.1.20:8000`.
- Expose both values to the app through `Info.plist` entries (`APIBaseURL`, `DemoAPIKey`) defined in `project.yml`.
- Confirm the root `.gitignore` already ignores `*.xcodeproj/` under `ios/` and `Secrets.xcconfig`.

**Acceptance:** `cd ios && xcodegen generate && xcodebuild -project GhostChef.xcodeproj -scheme GhostChef -destination 'generic/platform=iOS Simulator' build` succeeds.

### IOS-01.2 Info.plist keys

**Do** — in `project.yml`:
- `NSCameraUsageDescription`, `NSMicrophoneUsageDescription`, `NSBluetoothAlwaysUsageDescription`, `NSLocalNetworkUsageDescription`, each with an honest one-line reason.
- `NSAppTransportSecurity` → `NSAllowsLocalNetworking = YES`, so the app can reach a teammate's laptop over plain HTTP on the LAN. Production uses HTTPS.
- `UIBackgroundModes`: leave empty for now; IOS-02 adds what the DAT SDK documentation requires.
- Lock orientation to portrait. Keep the screen awake while a session runs (set `isIdleTimerDisabled` in code, IOS-03).

**Acceptance:** the app installs and, on first use of each feature, shows the system permission prompt with the written reason.

### IOS-01.3 Contract models

**Do** — `GhostChef/Models/`:
- `Recipe`, `RecipeSummary`, `Step`, `WatchFor`, `CheckResponse` (with `enum Verdict { pass, fix, unsure }`), `WatchResponse` (with `enum WatchStatus { ok, warn }`), `SessionCreated`, `SessionDetail`, `SessionSummary`, `SessionEvent`, `LiveTokenResponse`, `LiveConfig`, `Health`, `APIErrorBody`.
- `Codable`, `Sendable`, `Equatable`. One shared `JSONDecoder` with `convertFromSnakeCase` and ISO-8601 dates (accept fractional seconds), one `JSONEncoder` with `convertToSnakeCase`.
- **Decode leniently:** unknown fields are ignored (default), unknown enum strings must not crash — decode `Verdict` and `WatchStatus` with a fallback case `unknown`. Optional fields in the contract are optionals here.
- Copy `ai/fixtures/sushi_recipe.json` to `GhostChef/Resources/Fixtures/`. It is a `RecipeDraft` (no ids, no URLs): add a small loader that turns it into a `Recipe` with generated ids and bundle image URLs, for previews and tests.

**Acceptance:** unit tests decode literal JSON copied from each example in API-CONTRACT §2–§5 and the error envelope; a test decodes the bundled fixture.

### IOS-01.4 API client

**Do** — `GhostChef/Networking/`:
- `protocol GhostChefAPI` with async methods: `health()`, `recipes(status:)`, `recipe(id:)`, `createSession(recipeID:deviceLabel:)`, `postEvent(sessionID:kind:stepID:requestID:payload:)`, `session(id:)`, `check(frame:stepID:requestID:sessionID:capturedAt:)`, `watch(frame:stepID:requestID:sessionID:capturedAt:)`, `liveToken(recipeID:sessionID:)`.
- Chef-mode calls (`createRecipe`, `processRecipe`, the signed-URL upload) come in IOS-08; leave room for them in the protocol.
- `APIClient: GhostChefAPI` on `URLSession`: adds `X-Demo-Key`; JSON and multipart bodies (`frame` part as `image/jpeg`, filename `frame.jpg`); request timeouts **10 s for check, 4 s for watch**, 10 s otherwise; decodes the error envelope into `APIError(status:code:message:retryable:)`; maps transport failures to `APIError.network`.
- Base URL and key come from a `Settings` object (UserDefaults-backed, defaulting to the Info.plist values) and can change at runtime without restarting the app.
- `MockAPI: GhostChefAPI` backed by the bundled fixture, with scriptable check and watch results, for previews and unit tests.

**Acceptance:** unit tests with a `URLProtocol` stub verify the header, the multipart body structure, error decoding for a `429` and a `504`, and the timeouts being set.

### IOS-01.5 Frame source and the phone camera

**Do** — `GhostChef/Frames/`:
- `FrameSource` protocol exactly as in the README's core design.
- `PhoneCameraFrameSource`: `AVCaptureSession` with the back wide camera, `AVCaptureVideoDataOutput` on a background queue, keeps only the latest pixel buffer. `latestJPEG(maxLongEdge:quality:)` rotates to portrait, scales so the long edge is at most `maxLongEdge`, encodes JPEG. Never blocks the main actor.
- `StillImageFrameSource` returning a fixed image (for tests and the simulator).
- A SwiftUI camera preview view for the debug screen.

**Acceptance:** on the iPhone, a debug button "Grab frame" shows the JPEG's pixel size and byte size for `maxLongEdge` 1280 / quality 0.8 and 512 / 0.6; both are within the contract's limits (≤ 1.5 MB, ≤ 200 KB).

### IOS-01.6 App shell

**Do** — `GhostChef/UI/`:
- `RecipeListView` (the Cook-mode recipe library; every published recipe is visible, no accounts): loads `recipes(status: "published")`, shows title, chef, step count; pull to refresh; error and empty states. Tapping a recipe opens a placeholder `CookView` that just shows the first step's title and reference image.
- `SettingsView`: base URL, demo key (secure field), frame source picker (only "iPhone camera" for now), watch threshold (default 0.7), a **Health panel** showing `/health` (`ai_mode`, `storage`, `contract_version`) with a coloured warning when `ai_mode` is `fake`, and the "Grab frame" debug tool.
- `AppEnvironment`: creates and holds `Settings`, `APIClient`, and the active `FrameSource`; injected through the SwiftUI environment.

**Acceptance (on the iPhone, against a running backend on the LAN or the fixture):** the list shows the seeded recipe; the placeholder shows its first reference image; the Health panel shows the server's mode.

### IOS-01.7 Wrap up

- Tests: `xcodebuild … test` on a simulator (pick one from `xcrun simctl list devices available`).
- Update `STATUS.md`: batch 01, and the "Environment actually used" table (Mac, Xcode, iPhone, iOS, backend URL).

## Verification

```bash
cd ios
xcodegen generate
xcodebuild -project GhostChef.xcodeproj -scheme GhostChef -destination 'generic/platform=iOS Simulator' build
xcodebuild -project GhostChef.xcodeproj -scheme GhostChef -destination 'platform=iOS Simulator,name=<an available iPhone>' test
```

Then run on the physical iPhone from Xcode and walk through IOS-01.5 and IOS-01.6's acceptance by hand.

## Out of scope

The DAT SDK (IOS-02). The cook-along state machine (IOS-03). Any audio.

## When done

Commit `[ios] IOS-01 project foundation`, push. If the backend was not reachable, write that the list was verified against the fixture only (`DONE (fake)`).
