# AI-02 — Gemini access, model selection, limits, latency baseline

| | |
|---|---|
| **Track** | `ai/` |
| **Gate** | Start for G0 (one real call succeeds), finish for G1 |
| **Depends on** | AI-01; a Gemini API key |
| **Unblocks** | AI-04, AI-05, AI-06; answers risk R-07 and assumptions G1–G5 in [ARCHITECTURE §5.2](../../docs/ARCHITECTURE.md#52-gemini) |
| **Size** | Small–medium |
| **Model** | Opus 5.5 |
| **Needs a human for** | Obtaining the key; reading rate limits and data settings in AI Studio; asking the Google booth |

## Goal

Know, from our own account and not from documentation, **which model does each of the four jobs, how fast it answers from this venue, and how many calls per minute we are allowed.** Write those facts where the other tracks read them.

## Read first

- [../README.md](../README.md)
- [../../docs/EVENT-CONTEXT.md §5](../../docs/EVENT-CONTEXT.md#5-technical-facts-checked-on-2026-11-13) — model IDs seen publicly on 2026-11-13 (candidates only)
- Current Gemini API documentation at `https://aistudio.google.com/docs/` — models, structured output, image understanding, video understanding, Live API, rate limits. **Read the pages; SDK parameter names have changed between Gemini generations.**

## Tasks

### AI-02.1 Get a key *(human)*

- Ask the Google DeepMind booth how event credits are issued (reported: up to 400 teams, participants 18+). If credits are tied to a provided account or project, use that.
- Otherwise create a key in AI Studio on a team member's own project.
- Put it in `ai/.env` as `GEMINI_API_KEY`. Never commit it. Share it with the backend owner through a private channel, not the repository or a public chat.

**Acceptance:** `ai/STATUS.md` records the key source and project tier.

### AI-02.2 Client wrapper

**Do** — `src/ghostchef_ai/client.py`:
- A lazily created `google.genai.Client` (async calls through `client.aio`). A second client configured for API version `v1beta` for token minting (AI-05).
- `async def call_with_budget(coro, timeout_s)`: wraps `asyncio.wait_for`; on timeout raises `AITimeout`.
- `map_error(exc) -> AIError`: HTTP 429 / resource-exhausted → `AIQuotaError`; other API errors → `AIUnavailable`; JSON / schema validation failures → `AIInvalidOutput`. Inspect the SDK's actual exception classes rather than guessing their names.
- No retries here except one immediate retry on `AIInvalidOutput`, done by callers.

**Acceptance:** unit tests with a stubbed client prove each mapping and the timeout.

### AI-02.3 Discover what the key can call

**Do** — `ai/scripts/smoke_models.py`:
1. List the models visible to the key (`client.models.list()` or the current equivalent) and print name plus supported actions.
2. For each candidate ID below, try one minimal request and print success or the error:
   - **watch candidates** (fastest tier): `gemini-3.5-flash-lite`, `gemini-3.1-flash-lite`
   - **check candidates**: `gemini-3.8-flash`, `gemini-3.6-flash`, `gemini-4-hydrogen`
   - **video candidates**: `gemini-3.8-flash`, `gemini-4-argon`, `gemini-4-carbon`
   - **live candidates**: `gemini-3.8-live`
   Treat this list as a starting point. Replace it with what the models page and the list call actually show today.

**Acceptance:** the script's output is pasted (trimmed) into the batch notes in `STATUS.md`.

### AI-02.4 Capability smoke tests

Each is a small function in `scripts/smoke_models.py`, run 5 times, printing per-call latency.

| Test | Input | Passes when |
|---|---|---|
| Image + structured output | `fixtures/images/step-3.jpg` + "Return JSON `{\"has_text\": bool}`" with a JSON schema | Valid JSON matching the schema, 5 of 5 |
| Two images in one request | Two fixture images + "Are these the same image?" structured | Valid answer |
| Video with timestamps | Any 10–30 s phone clip (film the table) uploaded through the Files API + "List 2 moments with timestamps" structured | Timestamps are inside the clip's length |
| Live text → audio | Open a Live session with the SDK, send the text "Say hello", receive audio bytes | Audio received |
| Live function call | Declare one function `ping()`, send "please ping", receive a tool call | Tool call received |
| Ephemeral token | Mint a token with `client.auth_tokens.create` on `v1beta`, open a Live session using the token as the API key | Session opens |

While doing this, find and write down the current way to:
- request **structured output** (schema parameter name; whether pydantic models are accepted directly);
- **minimise latency** on the flash tier (thinking level or budget, max output tokens, temperature);
- lower **image resolution / token cost** per image (media-resolution setting), for the watcher.

**Acceptance:** each row has a PASS or a FAIL-with-error in `STATUS.md`; the three "how to" findings are written there in one line each.

### AI-02.5 Rate limits and data settings *(human, in AI Studio)*

- Open the project's rate-limit page. Record RPM, TPM, and RPD for the chosen watch, check, and video models, and any concurrent-session limit for Live.
- Compare with our need: one watch call per 2.5 s is **24 requests per minute per active session**; rehearsals may run two sessions at once; plus checks.
- Record the account's data-use / retention setting as shown. Do not paraphrase a policy we have not read.

**Acceptance:** the "Gemini account facts" table in `STATUS.md` is complete. If the watch model's RPM is below ~60, write the consequence under "Needs from other tracks" (slower interval or single session) and tell the team.

### AI-02.6 Choose and pin

**Do**
- Selection rule: **watch** = fastest model that passes the image test; **check** = the model with the best judgment that answers within ~2 s for two images; **video** = the strongest model that accepts video and returns timestamps; **live** = the Live model the docs currently recommend.
- Set these as the defaults in `config.py` (still overridable by env).
- Fill in the latency baseline table in `STATUS.md` (n, p50, max, date, network: venue Wi-Fi or hotspot).

**Acceptance**
- `python -m ghostchef_ai models` (fake mode off) prints the four chosen IDs.
- `STATUS.md` "Gemini account facts" and "Latency baseline" have no dashes left for watch, check, and live.

## Verification

```bash
cd ai
pytest -q
python scripts/smoke_models.py            # needs GEMINI_API_KEY, GHOSTCHEF_AI_FAKE unset or 0
python -m ghostchef_ai models
```

## Out of scope

Writing the real check / watch / extract prompts (AI-04, AI-06). Tuning.

## When done

Update `STATUS.md` (batch 02 → `DONE` or `PARTIAL` with what failed), commit `[ai] AI-02 model selection and limits`, push, and post the four model IDs and the watch RPM in the team chat.
