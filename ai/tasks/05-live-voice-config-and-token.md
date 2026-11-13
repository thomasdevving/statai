# AI-05 — Gemini Live: system instruction, function declarations, ephemeral token

| | |
|---|---|
| **Track** | `ai/` |
| **Gate** | G2 → G3 |
| **Depends on** | AI-02 (Live model verified, token smoke test passed) |
| **Unblocks** | BE-05 (serves the token and config), IOS-05 (opens the session) |
| **Size** | Medium |
| **Model** | Opus 5.5 |
| **Needs a human for** | Listening to the answers and judging tone and grounding |

## Goal

Everything the phone needs to hold a grounded voice conversation, produced server-side: the system instruction built from the recipe, the five voice-command functions, a locked ephemeral token, and a written description of the wire protocol for the iOS owner.

## Read first

- [../../docs/API-CONTRACT.md §5](../../docs/API-CONTRACT.md#5-gemini-live-voice) — the response shape, `[CONTEXT]` messages, the function table, who speaks what
- [../../docs/API-CONTRACT.md §7](../../docs/API-CONTRACT.md#7-internal-interface-backend--ai) — `build_live_config`, `mint_live_token`, `LiveConfig`, `LiveToken`
- Current Live API documentation and ephemeral-token documentation at `https://aistudio.google.com/docs/` (Live API section). Facts read on 2026-11-13 are in [EVENT-CONTEXT §5](../../docs/EVENT-CONTEXT.md#5-technical-facts-checked-on-2026-11-13); the WebSocket endpoint and message format were **not** verified then.

## Tasks

### AI-05.1 System instruction

**Do** — `src/ghostchef_ai/prompts/live_system.md` and `src/ghostchef_ai/live.py::build_live_config`.

The instruction is assembled from a fixed part plus the recipe. The fixed part must say:

- **Who you are:** a calm cooking assistant speaking for this chef's lesson to someone whose hands are busy. You speak through smart glasses.
- **Length:** one or two short sentences. Never a list. Never read a whole step unless asked.
- **Grounding:** answer from the lesson material below (steps and the chef's transcript). When the chef said it, say so naturally ("The chef wets their hands so…"). If the lesson does not cover the question, say "The chef doesn't cover that in this lesson" and, only if helpful, add one clearly general tip beginning "In general…". Never invent what the chef said.
- **What you cannot do:** you do **not** see the camera. Never say whether the food looks right. If asked "is this right?" or "check", call `check_my_work`.
- **Commands:** when the cook asks to check, go to the next step, go back, see the chef do it, or hear the step again, call the matching function immediately and say nothing before the tool response. After `check_my_work`, `next_step`, `previous_step`, and `show_me`, stay silent (the app speaks). After `repeat_instruction`, read the returned instruction aloud.
- **Context lines:** messages starting with `[CONTEXT]` are state updates from the app. Never reply to them. Use them to know the current step.
- **Safety:** no medical or food-safety assurances; suggest caution with knives and raw ingredients only if asked.
- **Language:** English, unless the cook speaks another language first.

Then append: recipe title, chef name if any, each step as `Step <idx>: <title> — <instruction>` with its success criteria, and the transcript. If the transcript exceeds ~6,000 words, keep the beginning and end and note the omission.

Function declarations (exact names, no parameters): `check_my_work`, `next_step`, `previous_step`, `show_me`, `repeat_instruction`, each with a one-line description written so the model triggers on natural phrasing ("is this okay?", "what's next", "go back", "show me how", "say that again").

`build_live_config` returns a `LiveConfig` with `model = model_ids()["live"]`, `response_modalities = ["AUDIO"]`, a `voice` chosen from the currently available voices (or `None` for the default), the tools, and `session_resumption = True`. It is a pure function: no network.

**Acceptance**
- Unit test: the returned instruction contains every step title, the transcript text, and the string `[CONTEXT]`; `tools` declares exactly the five names.
- `python -m ghostchef_ai live-config` prints it.

### AI-05.2 Ephemeral token

**Do** — `src/ghostchef_ai/live.py::mint_live_token(live_config)`:
- Use the `v1beta` client. Create a token with: 1 use, `expire_time` = now + 30 minutes, `new_session_expire_time` = now + 2 minutes.
- Try to **lock** the token to the model and configuration (`live_connect_constraints` in the SDK): model, response modalities, session resumption, and — **if the API accepts them** — the system instruction and tools. Check the current SDK reference for which fields can be constrained.
  - If everything locks: `locked = True`. The phone sends no config.
  - If the system instruction or tools cannot be locked: lock what can be, return `locked = False`, and the phone sends `config` from the `/live-token` response in its setup message. Record which case applies in `STATUS.md`.
- Return `LiveToken`. Map errors as elsewhere.

**Acceptance**
- Real call returns a token whose name starts with the documented prefix.
- A stubbed-client unit test covers both the fully locked and partially locked paths.

### AI-05.3 Prove it end to end from Python

**Do** — `ai/scripts/live_smoke.py`: build the config from the fixture, mint a token, open a Live session **using the token as the credential** (not the real key), then run these exchanges and print transcripts or events:

| Send (as text) | Expect |
|---|---|
| `[CONTEXT] Cook is now on step 2 of 6: "Wet hands". Do not reply to this message.` | No audio, no text reply |
| "Why do I wet my hands?" | A short spoken answer using the chef's reason |
| "Is this right?" | A `check_my_work` function call. Reply with the tool response from the contract; expect silence afterwards |
| "What's next?" | A `next_step` call |
| "Say that again" | A `repeat_instruction` call; reply `{ "instruction": "…" }`; expect it read aloud |
| "How long do I boil an egg?" | "The chef doesn't cover that…" (optionally a general tip) |

Save any returned audio to `ai/footage/live-smoke/` (gitignored) so a person can listen.

**Acceptance:** each row's outcome is recorded as PASS / FAIL in `STATUS.md`. Adjust the instruction until the `[CONTEXT]` row and the two "stay silent" rules hold in at least 4 of 5 attempts; record the real ratio.

### AI-05.4 Protocol notes for iOS

The iOS app will not use the Python SDK; it speaks the WebSocket protocol directly. Fill in the **"Live facts for `ios/`"** table in `STATUS.md` from the current API reference and from what the SDK actually sent in AI-05.3 (enable the SDK's debug logging or inspect its source):

- the WebSocket URL to use with an ephemeral token, and how the token is attached;
- the exact first (setup) message in both the locked and unlocked cases;
- how to send microphone audio (message shape, MIME type, sample rate, chunk size guidance) and a text turn;
- the shape of incoming audio, transcriptions if available, interruption signals, and tool calls, and the shape of a tool response;
- session duration limits, the going-away signal, and how session resumption handles are received and used.

**Acceptance:** the table has no dashes. The iOS owner confirms in chat that it is enough to start IOS-05.

### AI-05.5 Voice Q&A cases

**Do** — `ai/eval/qa.csv` with columns `id,question,kind,expected` where `kind` is `in_lesson` or `out_of_lesson`:
- 10 `in_lesson` questions answerable from the real transcript (after AI-03.5), with the expected gist.
- 5 `out_of_lesson` questions.
- Mark the one question the demo will use (see [DEMO-AND-SUBMISSION §2](../../docs/DEMO-AND-SUBMISSION.md#2-the-demo-beat-by-beat), beat 6).

**Acceptance:** file exists and is consistent with the current fixture transcript. Scoring happens in AI-07.

## Verification

```bash
cd ai
GHOSTCHEF_AI_FAKE=1 GHOSTCHEF_AI_FAKE_DELAY=0 pytest -q
python -m ghostchef_ai live-config
python scripts/live_smoke.py           # real key required
```

## Out of scope

Audio capture and playback, WebSocket client code (IOS-05). The HTTP endpoint (BE-05).

## When done

Update `STATUS.md`, commit `[ai] AI-05 live config, token, protocol notes`, push, and tell the backend and iOS owners.
