# IOS-05 — Gemini Live voice: questions, answers, voice commands

| | |
|---|---|
| **Track** | `ios/` (Mac) |
| **Gate** | G3. **Timebox: if it is not answering a question after ~4 focused hours, apply the cut order** (drop function calls first, then Live). |
| **Depends on** | IOS-03. BE-05 (`/live-token` real). AI-05's protocol notes in `ai/STATUS.md` → "Live facts for `ios/`". |
| **Unblocks** | The demo's question beat; voice commands |
| **Size** | Large |
| **Model** | Opus 5.5 |
| **Needs a human for** | Talking to it, listening, testing in a noisy place |

## Goal

The wearer asks a question out loud and hears a short answer grounded in the chef's lesson. Saying "check", "next", "go back", "show me", or "say that again" does the same thing as the gesture. Results from checks and warnings are still spoken by on-device TTS, and the two voices never overlap.

The phone opens the Live WebSocket **directly** to Gemini using an ephemeral token from the backend. The real API key is never on the phone.

## Read first

- [../../docs/API-CONTRACT.md §5](../../docs/API-CONTRACT.md#5-gemini-live-voice) — token response, `[CONTEXT]` message format, the function table and tool responses, who speaks what
- `ai/STATUS.md` → **"Live facts for `ios/`"**: the WebSocket URL, how the token is attached, the setup message for locked and unlocked tokens, audio formats, tool-call shapes, session limits and resumption. **If that table still has dashes, stop and ask the AI owner; do not guess the protocol.**
- The current Live API reference at `https://aistudio.google.com/docs/` for anything the notes leave out
- [../../docs/ARCHITECTURE.md §6](../../docs/ARCHITECTURE.md#6-failure-behaviour) — Live rows

What was read in the documentation on 2026-11-13: ephemeral tokens are Live-only, need API version `v1beta`, are passed by a non-SDK client as an `access_token` query parameter or an `Authorization: Token <token>` header, allow one session start within about a minute of minting, and need session resumption for reconnects about every ten minutes. Message shapes were **not** verified then.

## Tasks

### IOS-05.1 Wire types and a text-only session

**Do** — `GhostChef/Voice/LiveClient.swift` on `URLSessionWebSocketTask`:
- Codable types for exactly the messages in the protocol notes: setup, setup-complete, realtime audio input, client text turn, server content (audio chunks, transcriptions if enabled, turn-complete, interrupted), tool call, tool response, session-resumption update, go-away.
- `connect(token: LiveTokenResponse)`: open the socket with the token; send the setup message (no config when `locked` is true; `config` from the token response when false); wait for setup-complete.
- `sendText(_:)`, an `AsyncStream` of decoded server events, `close()`.
- A debug panel in Settings → "Voice Lab": connect, type a question, show the event log and any text or transcript.

**Acceptance:** from the Voice Lab, with a real token, a typed question produces server events that include audio data and a turn-complete. A typed `[CONTEXT] …` line produces no audible reply.

### IOS-05.2 Audio out

**Do** — `GhostChef/Voice/AudioIO.swift`:
- `AVAudioEngine` with a player node; schedule incoming PCM chunks (format from the protocol notes) as buffers, converting to the engine's output format.
- On an `interrupted` server event: stop the player and drop queued buffers immediately (barge-in).
- Expose `isPlayingLiveAudio`.

**Acceptance:** the typed question from the Voice Lab is heard clearly, with no gaps or chipmunk speed (a wrong sample rate is the usual cause).

### IOS-05.3 Audio in

**Do**
- Switch the audio session to `playAndRecord`, mode `voiceChat`, options `allowBluetooth` and (when no headset is connected) `defaultToSpeaker`. Enable voice processing on the input node for echo cancellation.
- Tap the input node, convert to the input format in the protocol notes, send as realtime audio messages in small chunks (20–100 ms).
- Request microphone permission with a clear reason; handle denial (voice disabled, everything else works).
- Two modes, switchable in Settings: **open mic** (default; the server's voice-activity detection decides turns) and **push-to-talk** (audio is sent only while a button is held — for the stage).
- Handle route changes and interruptions (phone call, glasses disconnect): rebuild the engine, keep the socket.

**Acceptance:** a spoken question gets a spoken answer on the phone speaker without the model hearing itself and looping. Push-to-talk works.

### IOS-05.4 Integrate with `CookSession`

**Do**
- On session start (after the first step card is up): fetch `/live-token` and connect in the background. Failure → voice unavailable, a small crossed-mic indicator, **no error dialog**; retry on the next step change (new token each time).
- On every step change send the context line exactly as in the contract:
  `[CONTEXT] Cook is now on step 4 of 6: "Add fillings". Do not reply to this message.`
- Lens: when the user starts speaking → `.talking(.listening, caption: "")`; while the answer plays → `.talking(.answering, caption:)` with a 3–5 word caption (the first words of the output transcription if the API provides one; otherwise "Answering…"); when the turn completes → back to the previous screen.
- The watcher pauses during `.talking` (IOS-04 already checks the lens).
- Post a `question` event per answered turn (caption, transcript if available).

**Acceptance:** during a real session, asking the demo question (see `ai/eval/qa.csv`) shows the mic state, plays the answer, returns to the step card, and the watcher resumes.

### IOS-05.5 Voice commands (function calls)

**Do** — when a tool call arrives, map it to the same paths the gestures use and answer with the tool response from the contract's table:

| Function | Do | Respond |
|---|---|---|
| `check_my_work` | `handle(.primary)` from a step / fix screen | `{"status":"done","note":"The app has shown and spoken the result. Say nothing more."}` — send it **immediately**, do not wait for the check result |
| `next_step` / `previous_step` | `handle(.next)` / `handle(.previous)`, `via: voice` | `{"status":"done","now_on":"5 of 6: Close"}` |
| `show_me` | `handle(.showMe)` | `{"status":"done"}` |
| `repeat_instruction` | nothing in the UI | `{"instruction":"<full instruction text>"}` |

Unknown function → respond with an error object; never leave a tool call unanswered (the model stalls).

**Acceptance:** saying "check", "next", "go back", and "say that again" each do the right thing in at least 4 of 5 tries in a quiet room; record the real ratio.

### IOS-05.6 Two voices, never at once

**Do** — a small arbiter between `SpeechOutput` (TTS) and Live audio:
- TTS `.result` (check verdicts, warnings) has priority: while it speaks, Live playback is paused/ducked and resumes or is dropped after.
- If Live is mid-answer when a result arrives, stop Live playback and speak the result.
- Step read-outs on step change (`.info`) are skipped while Live is answering.
- When TTS plays through the speaker, the open mic must not feed it back to Live as a user turn: stop sending mic audio while TTS is speaking (or rely on echo cancellation if it proves sufficient — test it).

**Acceptance:** trigger a check while the model is answering: the verdict is heard, not a mix. The model does not respond to the app's own TTS.

### IOS-05.7 Reconnect

**Do**
- Store the latest session-resumption handle. On socket close or a go-away message: reconnect with the handle if the token is still valid; otherwise fetch a new token and start a fresh Live session, then resend the current step's context line.
- Back off 1 s, 2 s, 5 s; give up after three tries until the next step change. Post a `client_error` event with `where: "live"`.

**Acceptance:** toggling Wi-Fi off and on during a session restores voice within ~10 s without touching the app; the rest of the app never froze.

## Verification

```bash
cd ios && xcodegen generate
xcodebuild -project GhostChef.xcodeproj -scheme GhostChef -destination 'platform=iOS Simulator,name=<an available iPhone>' test
```

Unit-test the message encoding/decoding against literal JSON from the protocol notes, the tool-call mapping, and the arbiter's decisions. Audio is verified by ear on the device.

## Out of scope

Routing audio through the glasses (IOS-06 uses the route decision from IOS-02). The system prompt and tool declarations (`ai/`). The token endpoint (`backend/`).

## When done

Update `STATUS.md` with what works (questions; which commands; open mic vs push-to-talk; measured rough time from end of question to first audio), commit `[ios] IOS-05 Gemini Live voice`, push.
