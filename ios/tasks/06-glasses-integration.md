# IOS-06 — Glasses integration: the real loop on the device

| | |
|---|---|
| **Track** | `ios/` (Mac) |
| **Gate** | G3 — **this is the Meta challenge deliverable.** If glasses are in hand, do this before IOS-05. |
| **Depends on** | IOS-02 (device facts and the four decisions), IOS-03. IOS-04 and IOS-05 plug in if they exist. Glasses in hand for the whole batch. |
| **Unblocks** | Every "works on the glasses" claim; the demo |
| **Size** | Large |
| **Model** | Opus 5.5, with Meta's `mwdat-ios` plugin and docs MCP |
| **Needs a human for** | Wearing the glasses through every acceptance check |

## Goal

The cook-along from IOS-03 runs on the glasses: frames come from the glasses' camera, the lens shows the cards (or the agreed fallback), the wearer acts without touching the phone, and audio comes through the glasses. The phone stays in a pocket once the session has started.

## Read first

- `ios/STATUS.md` → "Device facts" and **"Decisions taken from the spike"**. Build to those decisions, not to the original spec, wherever they differ.
- [../README.md](../README.md) — "Core design": you are adding a frame source, a renderer, and an input adapter. `CookSession` should not need to change.
- [../../docs/TECH-SPEC.md](../../docs/TECH-SPEC.md) "Display spec" and "Inputs"
- The SDK's camera, display, inputs, and session-lifecycle material (plugin / docs MCP / samples)

## Tasks

### IOS-06.1 `GlassesManager`: connection lifecycle

**Do** — grow the spike's `GlassesManager` into the single owner of the SDK:
- Registration state, the selected device, device state changes (connected, disconnected, hinges closed, thermal warnings if exposed), and capability flags (`supportsDisplay`).
- Publishes an observable `GlassesStatus` (`notRegistered`, `noDevice`, `connecting`, `ready(displays: Bool)`, `disconnected(reason)`).
- Starts and stops the camera stream and the display session; survives the app going to the background and returning, as far as the SDK allows.
- A status row at the top of `CookView` on the phone and in Settings.

**Acceptance:** closing the glasses' hinges and opening them again is reflected in the status within a few seconds, and the app recovers without a restart.

### IOS-06.2 `DATFrameSource`

**Do** — implements `FrameSource` on the glasses' camera stream:
- Keeps only the newest frame. `latestJPEG(maxLongEdge:quality:)` converts the frame's sample buffer to an upright JPEG.
- Stream settings from the spike's decision (resolution, codec). If frames are older than 2 s, `latestJPEG` returns `nil` and `isAvailable` is false (the watcher pauses; a check shows "Camera not ready").
- Selectable in Settings as "Glasses camera"; chosen automatically when glasses are `ready` at session start.

**Acceptance:** a check from the Lab or `CookView` sends a frame that visibly comes from the glasses (confirm on the monitor or by saving one). Frame sizes are within the contract's limits.

### IOS-06.3 `GlassesLensRenderer`

**Do** — observes `CookSession.lens` and draws each `LensScreen` with the SDK's display components, following the layout decided in the spike:
- `.step` / `.checking` / `.fix` / `.showMe`: counter + title, reference image, key line or headline + fix. Bright on black; amber for fix, green for pass; at most two text lines.
- `.pass`, `.unsure`, `.notice`, `.talking`, `.done`, `.recipePick`: text-first cards.
- **Send only on change**, and no more often than about twice a second, so the display link is not flooded. Pre-scale reference images to the size the display actually uses and cache them.
- When the session ends or the app loses the device: clear the display.
- If `supportsDisplay` is false or the display fails to start: do nothing here; the audio-only path (IOS-07) takes over. Never crash on a display error.

**Acceptance (wearing the glasses):** each screen is readable at a glance; the phone preview and the lens show the same state; nothing stale is left on the lens after the session ends.

### IOS-06.4 Input adapter

**Do** — translate the device's inputs into `CookInput`, using the mapping decided in the spike. Whatever the mechanism (Neural Band events, display buttons, captouch), the result is the same five inputs: `primary`, `next`, `previous`, `showMe`, `dismiss`.
- If the mapping uses display buttons, the renderer adds them to the relevant cards ("Check" / "Next", "Dismiss").
- Debounce repeated events (ignore the same input within 400 ms).
- The phone's operator buttons keep working in parallel.

**Acceptance (wearing the glasses, phone in pocket):** run a check, advance a step, go back, and dismiss a fix without touching the phone.

### IOS-06.5 Audio through the glasses

**Do** — apply the audio decision from the spike:
- TTS results and the chime come out of the glasses' speakers.
- If IOS-05 exists: Live uses the glasses' microphone and speakers; verify echo behaviour again on this route.
- If the Bluetooth route degrades or breaks the video stream (it shares the radio), fall back as decided (glasses speakers + phone mic, or phone audio) and record it.

**Acceptance:** the wearer hears results in the glasses with the phone in a pocket. The route in use is shown in Settings and written in `STATUS.md`.

### IOS-06.6 The watcher on the glasses

**Do** — nothing new should be needed: confirm the watcher runs on `DATFrameSource` frames, that the lens dot reflects its state, and that battery / heat / stream stability hold for a 10-minute session. If the stream cannot sustain it, lower the cadence or cut the watcher on the glasses (cut order 11) and say so.

**Acceptance:** a 10-minute session on the glasses with the watcher on; note stream drops, heat warnings, battery change.

### IOS-06.7 Full run, recorded

**Do** — the G3 run: on the glasses, with real Gemini and the real seeded recipe, real rice: step card → mistake → (warning) → fix → check passes → next. Record it on a second phone (hands and table only) with the monitor visible.

**Acceptance**
- `STATUS.md` → "End-to-end runs on the glasses" has the row: date, glasses model and firmware, what ran, result, where the recording is.
- State plainly which parts ran on the glasses and which did not (for example: "frames and audio on the glasses; lens cards worked; inputs via display buttons, not Neural Band").
- Tell the `web/` owner exactly what may be claimed.

### IOS-06.8 Nice-to-have, only if everything above is solid

- "Show me": play the step's `clip_url` with the display's video component, or show the reference still full-size.
- Chef recording through the glasses inside the app.

## Verification

```bash
cd ios && xcodegen generate
xcodebuild -project GhostChef.xcodeproj -scheme GhostChef -destination 'generic/platform=iOS' build
```

Device behaviour is verified wearing the glasses and written in `STATUS.md`.

## Out of scope

Failure handling beyond not crashing (IOS-07). Any change to `CookSession`'s rules.

## When done

Commit `[ios] IOS-06 glasses integration`, push. Status is `DONE` only with a recorded run on real glasses; otherwise `PARTIAL` with exactly what is missing.
