# Track: `ios/` — the app on the iPhone and the glasses

**Owner: Thomas**

You own everything the wearer experiences: frames from the glasses, the cards in the lens, gestures and voice, the watcher loop, and how the app behaves when something drops. This track **must run on the Mac** (Xcode) with a physical iPhone, and it carries the project's highest risk: integration with borrowed glasses. Prove the device path early (IOS-02), before polishing anything.

New here? Read [../README.md](../README.md), then [../docs/API-CONTRACT.md](../docs/API-CONTRACT.md) §1–§5 (the API you call and the client rules you must implement), [../docs/TECH-SPEC.md](../docs/TECH-SPEC.md) "Display spec", then this file.

## What you deliver

| Deliverable | Notes |
|---|---|
| iOS app `GhostChef` (SwiftUI, iOS 17.2+) | Recipe pick → cook-along → done |
| A swappable **frame source** | iPhone camera now, glasses stream later; everything downstream sees "a JPEG" |
| A **lens model** rendered two ways | On the phone screen (preview) and on the glasses display |
| Watcher loop with the contract's debounce and pause rules | Identical behaviour to the web simulator |
| Voice: Gemini Live over WebSocket with an ephemeral token; on-device speech for results | |
| Device facts written down | What actually works on the borrowed glasses, in [STATUS.md](STATUS.md) |

You do not write prompts, call Gemini's REST API, or talk to Supabase. Everything except the Live WebSocket goes through the backend.

## Prerequisites

| Need | Detail |
|---|---|
| Mac with a current Xcode | The DAT SDK requires **iOS 17.2+** as a deployment target (since SDK 0.9.0). Use the newest Xcode the Mac can run |
| iPhone on iOS 17.2+ with a cable | A real device is required for camera, Bluetooth, and the glasses. The simulator is fine for unit tests and the phone lens preview |
| Apple ID added in Xcode | A free personal team is enough to install on your own phone |
| XcodeGen | `brew install xcodegen`. The `.xcodeproj` is generated from `project.yml` and is **not committed** |
| Meta AI app on the iPhone | Pairs the glasses; **Developer Mode** is enabled through it |
| Wearables Developer Center account | `https://wearables.developer.meta.com/` — register, create a project and a release channel. Ask the Meta booth whether the event provides one |
| The glasses | **Not booked.** Ten Display and ten Gen 2 pairs are shared across teams. Ask the booth first thing |

### Meta's agent tooling for the DAT SDK (install before IOS-02)

Meta publishes a Claude Code plugin with SDK knowledge and a documentation MCP server. Use them instead of trusting remembered API names: the SDK is a developer preview and renamed things in almost every release.

```bash
claude plugin marketplace add facebook/meta-wearables-dat-ios
claude plugin install mwdat-ios@mwdat-ios-marketplace
claude mcp add --transport http dat-docs https://mcp.developer.meta.com/wearables
```

The first two commands are from the SDK README (checked 2026-11-13). The third registers the docs server the README names (`search_dat_docs` tool, no authentication); adjust the syntax to your Claude Code version if it differs. Reference: SDK repository `https://github.com/facebook/meta-wearables-dat-ios` (samples in `samples/`, changes in `CHANGELOG.md`), docs `https://wearables.developer.meta.com/docs/develop/`.

## Setup

```bash
cd ios
cp Config/Secrets.example.xcconfig Config/Secrets.xcconfig     # then edit: backend URL + demo key
xcodegen generate
open GhostChef.xcodeproj
```

Works after IOS-01 has created `project.yml` and `Config/`. The backend URL and key can also be changed at runtime in the app's Settings screen.

## Target layout

```
ios/
  project.yml                      XcodeGen spec (targets, packages, Info.plist keys)
  Config/
    Config.xcconfig                committed; includes Secrets.xcconfig if present
    Secrets.example.xcconfig       committed template
    Secrets.xcconfig               untracked
  GhostChef/
    App/          GhostChefApp.swift, AppEnvironment.swift (dependency container)
    Models/       Codable types mirroring API-CONTRACT (Recipe, Step, WatchFor, CheckResponse, …)
    Networking/   APIClient, APIError, multipart encoding
    Frames/       FrameSource protocol, PhoneCameraFrameSource, DATFrameSource (IOS-06)
    Session/      CookSession (state machine), LensScreen (lens model), CookInput, ImageCache
    Watcher/      WatchDebouncer (pure), WatcherLoop
    Lens/         PhoneLensView (preview renderer), GlassesLensRenderer (IOS-06)
    Voice/        SpeechOutput (on-device TTS), LiveClient (WebSocket), AudioIO
    Glasses/      GlassesManager (DAT), GlassesLabView (IOS-02 spike)
    UI/           RecipeListView, CookView, SettingsView, DoneView
    Resources/    Fixtures/sushi_recipe.json (copy of ai/fixtures), assets, chime
  GhostChefTests/
  README.md  STATUS.md  tasks/
```

## Core design (decided; build to this)

- **`FrameSource`** — `protocol FrameSource { var isAvailable: Bool { get }; func start() async throws; func stop(); func latestJPEG(maxLongEdge: Int, quality: CGFloat) async -> Data? }`. The phone camera and the glasses stream both implement it. The active source is chosen in Settings and can be switched at runtime.
- **`LensScreen`** — one enum value describes exactly what the lens shows (`recipePick`, `step`, `checking`, `pass`, `fix`, `unsure`, `talking`, `showMe`, `timer`, `done`, `notice`). `CookSession` produces it; **renderers only draw it**. The phone preview and the glasses display can never disagree, and the audio-only mode is a third "renderer" that speaks it.
- **`CookInput`** — one enum for every way the user acts (`primary`, `next`, `previous`, `showMe`, `dismiss`, `repeatInstruction`). Phone buttons, glasses inputs, and Gemini Live function calls all produce the same values. (Named `CookInput` to avoid clashing with the SDK's own `InputEvent`.)
- **`CookSession`** — a `@MainActor @Observable` state machine. All dependencies (`APIClient`, `FrameSource`, `SpeechOutput`, a clock) are injected as protocols so it is unit-testable without a device.
- **Contract rules are code, with tests:** stale-result rule (§3.4), watcher interval / debounce / pause / mute (§3.3), who-speaks-what (§5.3).

## Batches

One Claude session per batch. Kickoff prompt: [../docs/PLAN.md §7](../docs/PLAN.md#7-working-with-claude-on-each-laptop).

| # | Batch | Gate | Needs | A human must |
|---|---|---|---|---|
| 01 | [Project foundation](tasks/01-project-foundation.md) | G0 | Fixture from AI-01; BE-01 for live data | Sign the app, run on the phone |
| 02 | [DAT glasses spike](tasks/02-dat-glasses-spike.md) | G1 | 01; a pair of glasses (or MockDeviceKit to start) | Get glasses, pair, test, ask the booth |
| 03 | [Cook-along core](tasks/03-cook-along-core.md) | G2 | 01; BE-01 (BE-03 for real verdicts) | Try it on real rice |
| 04 | [Proactive watcher](tasks/04-proactive-watcher.md) | G2 | 03 | Try it on real rice |
| 05 | [Gemini Live voice](tasks/05-gemini-live-voice.md) | G3 | 03; BE-05; AI-05 protocol notes | Talk to it |
| 06 | [Glasses integration](tasks/06-glasses-integration.md) | G3 | 02 result, 03 (04 if done); glasses in hand | Wear them |
| 07 | [Resilience and demo mode](tasks/07-resilience-and-demo-mode.md) | G4 | 03–06 | Run the recovery tests, rehearse |

**Order is flexible after 04:** if glasses are in hand, do 06 before 05. The Meta challenge is the main one; a working loop on the glasses outranks voice.

**IOS-02 runs as early as hardware allows**, in parallel with 03 if a second person can sit at the Mac. Its result decides the display and input mapping for 06.

## Rules for this track

- **Never claim a device capability from documentation.** A row in `STATUS.md` → "Device facts" is `PASS` only after you saw it on the borrowed glasses, with the glasses model, firmware, SDK version, and date.
- **The phone path always works.** Every feature must run with the iPhone camera and the on-screen lens preview. This is the development path and the fallback; it is never presented as the Meta deliverable.
- **Pin the DAT SDK version** in `project.yml` (exact version) and record it. Do not float.
- **Unit-test the pure logic** (models decoding, debouncer, state machine, stale rule). UI and device code are verified by hand and written up.
- Build must stay green: `xcodegen generate && xcodebuild … build` before every push.
- Do not edit other tracks' folders. API problems go in `STATUS.md` → "Needs from other tracks" and to the backend owner.
