# `ai/` status

> Updated by the track owner after every batch. Other tracks read this file for model IDs, limits, and Live protocol facts. Write only what was run and observed.

## Batches

| # | Batch | Status | Date / commit | Notes |
|---|---|---|---|---|
| 01 | Package skeleton, fake mode, fixture | DONE (fake) | 2026-11-14 · `273fadb` | Fake mode only: no Gemini call exists yet. 38 tests pass, ruff clean, all verification commands run (Windows, Python 3.13). Fixture recipe and the six reference images are **placeholders**, not chef footage. Model IDs in `config.py` are unverified placeholders until AI-02. |
| 02 | Gemini access and model selection | DONE | 2026-11-14 · `19091c3`, `efcedc6` | On the **event key** (project "Hack Junction 2026-7638", Tier 3, paid): image, two-image, video, Live audio, Live function call and fully locked ephemeral token all **PASS**; limits read in AI Studio; models pinned. Earlier tests ran on a different key (see account facts). `check` stays provisionally on the lite model; AI-04 decides with real frames. The account's data-use wording was not found on the pages read. The OpenAI stand-in is no longer used. |
| 03 | Chef footage and evaluation set | PARTIAL — lesson is now the sandwich (D-19); fixture text rewritten, footage not filmed; see "Footage and evaluation set" | 2026-11-14 · `3491963` | **Tooling done, physical work not started.** Done: `scripts/extract_frames.py` (03.3), `scripts/check_cases.py` (validates `eval/cases.csv`, prints split × label counts, `--scaffold` adds unlabelled rows), `scripts/side_by_side.py` (for 03.6), `eval/` layout, empty `eval/cases.csv`, `eval/README.md` template; 18 new tests; 74 pass. ffmpeg 9.0.2 installed on the owner's laptop (winget `Gyan.FFmpeg`); extraction verified on a generated 6 s test video (frame names, 720×1280 size, `--at`), **not yet on real footage**. **Not done (human):** 03.1 chef take, 03.2 mistake clips, 03.4 labelling, 03.5 real stills + fixture v1, 03.6 the "can a person tell?" check. |
| 04 | Check and watch | PARTIAL — code done; the two data-dependent criteria are blocked by having no labelled footage | 2026-11-14 · `429b19a` | **Done:** prompts in `src/ghostchef_ai/prompts/check.md`, `watch.md` (recipe-agnostic, tested); real `check.py` / `watch.py` on `client.image_json`; `__init__.py` dispatches to them when fake mode is off; new unit tests with a stubbed model call (every post-processing rule, retry, timeout → `AITimeout`, quota → `AIQuotaError`), 120 tests pass, ruff clean; CLI runs against the real API on real frames (below); `scripts/dev_eval.py` (AI-04.5 runner, dev rows only); both frame sizes tried for each call. **Not met:** AI-04.3 "a mistake frame returns `warn` with the right id": no frame of a mistake exists. AI-04.5 confusion tables: `eval/cases.csv` has 0 rows, so there is nothing to count. **False approvals remain** on clearly unfinished work with the pinned check model: risk R-02, see "Check and watch on private dev material". |
| 05 | Live voice config and token | PARTIAL — all code and measurements done; only the iOS owner's confirmation (AI-05.4) is missing | 2026-11-14 · `96e105e` | **Done:** `prompts/live_system.md` + refined `build_live_config` (five functions, the four app-handled ones `NON_BLOCKING`); real `mint_live_token` (v1beta, 1 use, 30 min / 2 min, **fully locked**: model, modalities, system instruction, tools, transcription, context compression; resumption left to the client); `scripts/live_smoke.py` speaks the raw WebSocket protocol with the token only: **every AI-05.3 row PASS 5/5** (5 sessions, 5 tokens), plus spoken 16 kHz audio, resumption and both ways of passing the token (below); `eval/qa.csv` (10 + 5, **built on the placeholder narration**); the "Live facts for `ios/`" table filled from the SDK 3.3.0 source, the docs and these runs. 132 tests pass, ruff clean. **Open:** the iOS owner has not yet confirmed the table is enough for IOS-05. Two protocol rules the phone must follow are new (context lines with `turnComplete: false`, `scheduling: "SILENT"` on four tool responses): see "Needs from other tracks". |
| 06 | Recipe extraction from video | PARTIAL — code done; no chef video exists (team decided not to cook) | 2026-11-14 · `cbbfcdb` | **Done:** recipe-agnostic prompt `src/ghostchef_ai/prompts/extract.md` (06.1); `src/ghostchef_ai/ingest.py` (06.2): Files API upload, wait for ACTIVE (5 min limit), one structured generate call (180 s, thinking MINIMAL → LOW → none), every repair rule from the task, one retry on invalid output, uploaded file always deleted, Gemini-only; dispatched from `__init__.py` (06.5); CLI `extract --verbose` prints model and timings; 23 new tests (155 pass, ruff clean); one real run (see "Recipe extraction runs"). **Not met:** 06.3 needs the real chef video and a human review of it; none exists. **06.4: option (a)**, keep the hand-written fixture: there is no chef take to extract from. |
| 07 | Evaluation and tuning | NOT STARTED | | |

Status words: `DONE`, `DONE (fake)`, `PARTIAL`, `BLOCKED`, `NOT STARTED` (defined in docs/PLAN.md §8).

## Gemini account facts (AI-02 fills this in)

| Fact | Value | How verified |
|---|---|---|
| Key source (event credits / own project) | Event key "Workshop API key" (`…SarI`), project "Hack Junction 2026-7638" (`junction26hel-7638`), now in the owner's untracked `ai/.env`. The first round of tests on 2026-11-14 ran on a different key from an unknown project; everything in the "event key re-check" table below ran on the event key | AI Studio API keys page; last-4 check done locally, key never printed |
| Project tier | **Tier 3**, key marked **paid**, billing account `…7F15` | AI Studio API keys page |
| Data-use / retention setting of this account | Not stated on the pages read. AI Studio labels the event key "paid"; check the terms for paid use before quoting any policy | AI Studio API keys page |
| Model for `video` (extract_recipe) | `gemini-3.5-flash` | Video test PASS (below) |
| Model for `check` | `gemini-3.5-flash-lite` (kept by AI-04; **open team decision**, see R-02 note below) | Meets the 2 s p50 target (~0.9–1.0 s warm). `gemini-3.8-flash` judged the dev material better but took 2.0–7.2 s with one 8 s timeout in 27 calls (AI-04). Switch without code changes: `GHOSTCHEF_MODEL_CHECK=gemini-3.8-flash` |
| Model for `watch` | `gemini-3.5-flash-lite` | Image tests PASS, ~0.9 s |
| Model for `live` | `gemini-3.8-live` | Live audio + function call + locked token PASS |
| Rate limits for the watch model (RPM / TPM / RPD) | Event project, Gemini 3.5 Flash Lite: 30K / 30M / unlimited | AI Studio rate-limit page, 2026-11-14 |
| Rate limits for the check model | Same model as watch (30K / 30M / unlimited); Gemini 3.8 Flash 20K / 20M / unlimited if AI-04 switches | |
| Rate limits for the video model | Gemini 3.5 Flash: **not listed** on the page; the page shows 3 Flash, 3.6 Flash, 3.8 Flash (each 20K / 20M / unlimited) | |
| Rate limits for the Live model | Gemini 3.8 Live: RPM unlimited, TPM 10M, RPD unlimited (no concurrent-session figure shown) | |

All the limits above are for the **event project**. The page showed 0 usage on every model over 28 days, which fits our tests having run on the other key. The watcher's ~24 requests a minute per session is far below 30K RPM.

`models.list` on 2026-11-14 showed 28 models, including `gemini-3.5-flash`, `gemini-3.5-flash-lite`, `gemini-3.1-flash-lite`, `gemini-3.6-flash`, `gemini-3.7-flash`, `gemini-3.8-flash`, `gemini-4-argon`, `gemini-4-carbon`, `gemini-4-hydrogen`. **No Live model appears in the list**, but `gemini-3.8-live` and `gemini-3.1-flash-live-preview` both connect.

### Gemini smoke tests, 2026-11-14 (owner's laptop, Windows; network not recorded)

Image tests used the placeholder `step-3.jpg` at low media resolution: "correct" = read the heading text; two-image = same / different picture. These are capability checks, **not** cooking-judgement results. The first run without a thinking setting was discarded (see the "Findings" list); this is the second run, 3 repeats per model.

| Model | image + JSON | latency p50 / max ms | two images | 512 px frame | Notes |
|---|---|---|---|---|---|
| `gemini-3.5-flash-lite` | 3/3 | 906 / 1842 | 2/2 | 860 ms | Most reliable and fastest |
| `gemini-3.1-flash-lite` | 1/3 (2 timeouts) | 1022 (n=1) | 2/2 | 6438 ms | Flaky |
| `gemini-3.6-flash` | 3/3 | 10837 / 12102 | 1/2 (1 timeout) | 12184 ms | Too slow for a 2 s check |
| `gemini-4-hydrogen` | 0/3 | — | 0/2 | — | Output cut off at 60 tokens even at minimal thinking; also 503s and one 429 |
| `gemini-3.8-flash` | 0/3 | — | 0/2 | — | Only 503 "high demand" and timeouts; **unverified, not rejected** |

| Gemini-only test | Model | Result |
|---|---|---|
| Video with timestamps (12 s generated counter clip, Files API) | `gemini-3.5-flash-lite` | PASS: moments at 0 s and 10 s, both correct; upload + processing 6.1 s, generate 1.2 s |
| | `gemini-3.5-flash` | PASS: 3 s and 8 s, correct; upload 4.9 s, generate 7.3 s, thinking MINIMAL |
| | `gemini-3.8-flash` | Not tested: rejects MINIMAL thinking, then 503 high demand |
| Live text → audio | `gemini-3.8-live` | PASS: 95,520 bytes of `audio/pcm;rate=24000`, first audio 411 ms, transcript "Hello, how can I help you today?" |
| | `gemini-3.1-flash-live-preview` | PASS: first audio 565 ms |
| Live function call | `gemini-3.8-live`, `gemini-3.1-flash-live-preview` | PASS: `ping` arrived as a tool call; tool response accepted |
| Ephemeral token, model + modalities + **system instruction + tools locked** | `gemini-3.8-live` | PASS: minted (`auth_tokens/…`), a session opened with only the token (API version `v1beta`), audio returned, first audio 407 ms |

Total paid generate calls: 70 image calls across both runs plus 5 video calls and a few Live turns; token counts are in the script output, cost not measured.

### Event key re-check, 2026-11-14 (the key now in use)

| Test | Model | Result |
|---|---|---|
| image + JSON, 5 repeats | `gemini-3.5-flash-lite` | 5/5, p50 827 ms, max 2356 ms; two images 2/2; 512 px frame 633 ms |
| image + JSON, 5 repeats | `gemini-3.8-flash` | 2/5: reachable (no 503s now), p50 2361 ms, but thinking level LOW still overruns a 60-token answer; needs a larger output limit if AI-04 tries it for `check` |
| Video with timestamps | `gemini-3.5-flash` | PASS: 0 s and 10 s, correct; upload 4.9 s, generate 2.1 s |
| Live text → audio + function call | `gemini-3.8-live` | PASS: first audio 446 ms, `audio/pcm;rate=24000`, `ping` tool call |
| Ephemeral token, fully locked | `gemini-3.8-live` | PASS: first audio 515 ms |

### Findings that change how we call Gemini

- **Thinking tokens count against `max_output_tokens`.** With a small limit, thinking models return empty or cut-off JSON. `client.py` now asks for thinking level MINIMAL, steps down to LOW for models that reject MINIMAL (`gemini-3.8-flash` does), and reports cut-off output as `AIInvalidOutput`.
- **Gemini pretty-prints JSON**, so it needs more output tokens than OpenAI for the same answer (two-image check: 20 tokens too few, 60 enough).
- **Live needs an explicit API version.** The SDK's default answered HTTP 404 on every Live model; `v1beta` and `v1alpha` both connect.
- **Ephemeral tokens:** the SDK warns they are "v1alpha only", yet a `v1beta` session opened with a fully locked token. Record which version IOS-05 uses.
- **High-demand 503s** happened repeatedly on `gemini-3.8-flash` and `gemini-4-hydrogen` during the test window. Plan for one retry on 503 in `/check`, which the contract already specifies.

## Interim OpenAI stand-in (NOT Gemini — development only)

Used while Gemini access was pending. **No longer used** since the Gemini key arrived (2026-11-14); the code path stays for emergencies only, and the default provider is Gemini. **Nothing measured here may be reported as a Gemini result or used in the deck.**

- Switch: `GHOSTCHEF_PROVIDER=openai` in `ai/.env` (default `gemini`). Needs `OPENAI_API_KEY` and `pip install -e ".[openai]"`. Only `check` and `watch` exist on this path; `video` and `live` report `unsupported-on-openai`.
- Cost guard: at most 300 paid calls per process on OpenAI (`GHOSTCHEF_MAX_CALLS`; the smoke script uses 40). Low image detail, small outputs. Owner has $21 of credit; a hard spend limit in the OpenAI dashboard is the owner's job.
- Key: the owner's personal OpenAI key, in the untracked `ai/.env` only. Free listing on 2026-11-14 showed 96 models.

Smoke test, 2026-11-14, owner's laptop on Windows (network not recorded), fixture placeholder image `step-3.jpg` with low image detail. "Correct" = read the heading text; two-image = same / different picture. These are capability checks, **not** cooking-judgement results.

| Model (resolved) | image + JSON | latency p50 / max ms (n=5) | two images | 512 px frame |
|---|---|---|---|---|
| `gpt-5.4-nano` (`gpt-5.4-nano-2026-03-17`) | 5/5 | 923 / 4055 | 2/2 | 920 ms, read |
| `gpt-5.4-mini` (`gpt-5.4-mini-2026-03-17`) | 5/5 | 920 / 1945 | 2/2 | 808 ms, read |
| `gpt-4.1-mini` (`gpt-4.1-mini-2025-04-14`) | 5/5 | 890 / 1266 | 2/2 | 772 ms, read |

Run cost: 24 calls, 35,189 input tokens, 382 output tokens. The dollar charge was not measured; check the OpenAI usage page.

**Pinned interim models:** `check` = `gpt-5.4-mini` (stronger model for the judgement), `watch` = `gpt-5.4-nano` (cheapest tier; one 4 s outlier in five calls). All three passed, so this is a cost choice, not a quality finding. OpenAI rate limits for these models were **not read**: the owner can check them on the dashboard's Limits page.

## Latency baseline (measured from a laptop at the venue)

| Call | Model | n | p50 ms | max ms | Date | Network |
|---|---|---|---|---|---|---|
| check_frame, 1280 px, warm process (final prompt) | `gemini-3.5-flash-lite` | 9 | 1017 | 1931 | 2026-11-14 | not recorded (owner's laptop) |
| check_frame, 768 px, warm process (final prompt) | `gemini-3.5-flash-lite` | 9 | 883 | 949 | 2026-11-14 | not recorded |
| check_frame, 768 px, warm process (final prompt) | `gemini-3.8-flash` (LOW thinking) | 9 | 2505 | 6003 | 2026-11-14 | not recorded |
| check_frame, single CLI call (cold process: client + TLS setup) | `gemini-3.5-flash-lite` | 2 | 2073 / 2131 | — | 2026-11-14 | not recorded |
| watch_frame, 512 px, warm process | `gemini-3.5-flash-lite` | 9 | 902 | 1518 | 2026-11-14 | not recorded |
| watch_frame, 384 px, warm process | `gemini-3.5-flash-lite` | 9 | 865 | 1339 | 2026-11-14 | not recorded |
| watch_frame, single CLI call (cold process) | `gemini-3.5-flash-lite` | 2 | 1874 / 1690 | — | 2026-11-14 | not recorded |
| One-image JSON call (smoke test, proxy for watch) | `gemini-3.5-flash-lite` | 3 | 906 | 1842 | 2026-11-14 | not recorded |
| Live: mint token (`mint_live_token`), warm process | `gemini-3.8-live` | 4 | 295 | 636 | 2026-11-14 | not recorded |
| Live: first audio after a text question (raw WebSocket, token) | `gemini-3.8-live` | 5 | 594 | 697 | 2026-11-14 | not recorded |
| extract_recipe | — not implemented until AI-06; video smoke on a 12 s clip: 4.9 s upload + 7.3 s generate (`gemini-3.5-flash`) | 1 | — | — | 2026-11-14 | not recorded |

## Tuned values the clients need

| Value | Current | Set by |
|---|---|---|
| `WATCH_THRESHOLD` (client debounce confidence) | 0.7 (contract default, untuned) | AI-07 |
| Watch frame long edge | **512 px** (contract default, kept). AI-04 tried 384 px: median 865 vs 902 ms, 18 vs 28 KB per frame, same answers (9/9 `ok` both) on 9 unlabelled frames. Too small a gain to justify less detail | AI-04 (AI-07 may revisit with labels) |
| Check frame long edge | **1280 px** (contract default, kept). AI-04 tried 768 px: median ~0.1 s faster (883 vs 1017 ms), 53 vs 110 KB per frame, no consistent difference in answers across rounds on 9 unlabelled frames. Kept until labelled frames can show whether detail matters | AI-04 (AI-07 may revisit with labels) |
| Check media resolution | MEDIUM (`check.LOW_DETAIL = False`); watch uses LOW | AI-04 |

## Live facts for `ios/` (AI-05 fills this in)

Sources, in order of trust: what `scripts/live_smoke.py` sent and received over a raw WebSocket on 2026-11-14 (model `gemini-3.8-live`, owner's laptop, Windows); the frames the Python SDK **`google-genai` 3.3.0** puts on the wire (captured offline by replacing its socket, `live.py` `AsyncLive.connect`); the docs at `aistudio.google.com/docs/live-api/` (session management, ephemeral tokens) and `aistudio.google.com/api-reference/live`, read 2026-11-14. "Run" = we did it; "SDK" = the SDK sends it this way; "docs" = only read.

| Fact | Value |
|---|---|
| WebSocket URL used with an ephemeral token | `wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContentConstrained` (**run**). Note the method `…Constrained` (the SDK switches to it whenever the key starts with `auth_tokens/`) and the explicit `v1beta`; the docs say tokens work "only with the v1beta version". The SDK warns "v1alpha only"; ignore that, v1beta ran. (The SDK builds `…googleapis.com//ws/…` with a double slash; the single slash above is what we ran.) The API-key endpoint `…BidiGenerateContent` is for the backend only, never the phone. |
| How the token is passed | Either header `Authorization: Token auth_tokens/…` (**run**, 6 sessions) or query `?access_token=auth_tokens/…` (**run**, token name unescaped, `/` included). Use the header with `URLSessionWebSocketTask` (`URLRequest.setValue(_:forHTTPHeaderField:)`). The token is the `token` field of `GET /live-token`. Never log it. |
| First message (setup) shape when `locked` is true | Send right after the socket opens, then **wait for `{"setupComplete":{}}` before sending anything else** (first server message, 1.1–1.7 s after connect, n=5): `{"setup":{"model":"models/gemini-3.8-live","sessionResumption":{}}}` (**run**). `model` = `"models/" +` the `model` field of `/live-token`. Nothing else: system instruction, tools, response modality, input/output transcription and context-window compression are locked in the token, and a client `systemInstruction` is ignored (**run**: sent a "pirate" instruction, answer stayed grounded). `sessionResumption` is **not** locked on purpose (a locked empty one wiped the client's handle, so resumption silently started a fresh session), so the phone must send `{}` to receive resumption handles. To resume: `{"setup":{"model":"models/gemini-3.8-live","sessionResumption":{"handle":"<last newHandle>"}}}` (**run**). Failure shows as a WebSocket close before `setupComplete`, e.g. code **1011 "Token has been used too many times"** (**run**). |
| First message (setup) shape when `locked` is false (fallback, not expected) | **SDK, not run with a token** (minting always locked fully in this batch): `{"setup":{"model":"models/<model>","generationConfig":{"responseModalities":["AUDIO"]},"systemInstruction":{"parts":[{"text":"<config.system_instruction>"}],"role":"user"},"tools":[{"functionDeclarations":[…]}],"sessionResumption":{},"inputAudioTranscription":{},"outputAudioTranscription":{},"contextWindowCompression":{"slidingWindow":{}}}}`. Rename `config.tools[].function_declarations` → `functionDeclarations` and keep each declaration's `behavior`. |
| Input audio format | **Run:** 16-bit signed little-endian PCM, mono, **16 kHz**, base64, sent as `{"realtimeInput":{"audio":{"data":"<base64>","mimeType":"audio/pcm;rate=16000"}}}` in **100 ms chunks (3,200 bytes)** at real-time pace. Voice activity detection is automatic (the server sent `{"voiceActivity":{"type":"ACTIVITY_START","audioOffset":"0.240s"}}`), and the answer started without any end-of-speech message after ~1.5 s of trailing silence. The SDK also has `{"realtimeInput":{"audioStreamEnd":true}}` for when the mic stops (SDK, not run). Do not resample to other rates without testing. |
| Text turn | `{"clientContent":{"turns":[{"role":"user","parts":[{"text":"…"}]}],"turnComplete":true}}` (**run**). |
| `[CONTEXT]` step updates (API-CONTRACT §5.1) | Same message with **`"turnComplete": false`** (**run**: silent 5/5 in the measured run and 3/3 in earlier tests; nothing at all comes back. The model still used it: asked "which step am I on?" afterwards it named the right step 4/4, including after resumption). With `turnComplete: true` the model must produce a turn: 4/5 silent, the fifth spoke 1.8 s; earlier runs spoke 0.7–3 s with captions like `<no speech>{pause}`. Use `false`. |
| Output audio format | `audio/pcm;rate=24000`: 16-bit LE mono PCM at 24 kHz, base64 (**run**, AI-02 and AI-05). |
| Incoming messages | **Every server frame was a binary WebSocket frame containing UTF-8 JSON** (265 of 265 in one session, **run**): in Swift handle `.data`, not only `.string`. Kinds seen (**run**): `setupComplete`; `serverContent.modelTurn.parts[].inlineData {mimeType, data}` = audio chunks; `serverContent.outputTranscription.text` = caption pieces, concatenate them; `serverContent.inputTranscription.text` = what the cook said; `serverContent.generationComplete: true` then `serverContent.turnComplete: true` (with `usageMetadata`) = end of a turn; empty `serverContent: {}`: ignore; `voiceActivity`; `toolCall`; `sessionResumptionUpdate`. Captions can carry non-speech markers (`<no speech detected>`, `{pause}`): hide text in `<…>` or `{…}`. **Interruption** (docs, not observed): `serverContent.interrupted: true` when the cook talks over the model: stop playback and drop queued audio; a `toolCallCancellation {"ids":[…]}` cancels pending calls. Raw examples: `ai/footage/live-smoke/<run>/messages.jsonl` on the owner's laptop (gitignored; ask for a copy). |
| How a function call arrives and how to answer it | Arrives as `{"toolCall":{"functionCalls":[{"name":"check_my_work","args":{},"id":"call_9877…"}]}}` (**run**, no audio before the call 10/10 for check/next). **The server then immediately sends `generationComplete` + `turnComplete` for that turn: that is not the reply** (our first test mistook it for one). Answer with `{"toolResponse":{"functionResponses":[{"id":"<same id>","name":"<same name>","response":{…API-CONTRACT §5.2…},"scheduling":"SILENT"}]}}` for `check_my_work`, `next_step`, `previous_step`, `show_me` (declared `NON_BLOCKING`; `SILENT` = "add to context, trigger no generation"; **run**: silent 10/10 after check/next in the 5 sessions, 5/5 in an API-key test). For `repeat_instruction` send **no** `scheduling`: the model then reads the instruction aloud as a new turn (**run** 5/5, first audio ~0.5 s). Without `SILENT`, the model talked after check/next despite the instruction (**run**, 2 of 2). |
| Session length limit and resumption | Docs: one WebSocket connection lasts "around 10 minutes"; audio-only sessions end at 15 minutes **without** context compression. Sliding-window compression is locked into the token, which the docs say extends sessions without limit (**not measured**: no session ran > 3 min). The server sends `{"goAway":{"timeLeft":"…"}}` before closing (docs; not seen in our short sessions). Handles arrive as `{"sessionResumptionUpdate":{"newHandle":"…","resumable":true}}` (**run**; one per session, shortly after the first turn); keep the latest `newHandle` where `resumable` is true (docs: valid 2 h after the session ends; not resumable while a function call or generation runs). On `goAway` or a dropped socket: open a new socket and send the resume setup. **Same single-use token + handle works** (**run**, including 160 s after minting, i.e. past `new_session_expires_at`) and the model remembered the step; a **new** token + handle also works (**run**). A spent token **without** a handle is refused (1011). So: reuse the token for resumption until `expires_at` (30 min), then call `/live-token` again and resume with the new token + handle. After an app restart with no handle: new token, fresh session. |
| Can `system_instruction` and `tools` be locked into the token? | **Yes** (**run**): `locked: true`. The token request locks model, `responseModalities`, `systemInstruction`, `tools`, `inputAudioTranscription`, `outputAudioTranscription` and `contextWindowCompression` with `lock_additional_fields=[]` (= exactly those fields, sent as the field mask). Minting took 245–2418 ms (n=5; the first in a process is the slow one). The partially locked fallback (model + modality only, `locked: false`) exists in code and unit tests but never triggered. |
| Latency (owner's laptop, venue network not recorded) | First audio after a text question: median 594 ms, max 697 (n=5, "why wet hands"); out-of-lesson answer 587 / 693; instruction read-back 512 / 513; after spoken audio the answer began before the last silence chunk was sent. Socket open → `setupComplete` 1.1–1.7 s. |

## Live voice smoke test (AI-05.3, 2026-11-14)

`python scripts/live_smoke.py --attempts 5 --question-wav footage/live-smoke/question-wet-hands-16k.wav`: 5 sessions, each with its own freshly minted, fully locked token, raw WebSocket, **token only** (the API key never touched the socket). Lesson = the fixture (**placeholder narration**, no real chef take). Silence = no audio bytes within 8 s. Audio of every reply is in `ai/footage/live-smoke/20261114-052817/attempt-*/` (gitignored); a person still has to listen and judge tone (task: "needs a human"). The spoken question is a Windows text-to-speech recording ("Why do I need to wet my hands?"), not a human voice.

| Send | Expect | Result (5 attempts) | Example of what was said |
|---|---|---|---|
| `[CONTEXT] … step 2 of 6: "Wet hands" …` with `turnComplete: false` | no audio, no text | **PASS 5/5** | nothing |
| "Why do I wet my hands?" | short spoken answer with the chef's reason | **PASS 5/5** | "The chef wets their hands so the rice doesn't stick to your fingers and you can spread it gently." |
| "Is this right?" | `check_my_work`, then silence | **PASS 5/5** call, **5/5** silent | (silent) |
| "What's next?" | `next_step`, then silence | **PASS 5/5** call, **5/5** silent | (silent) |
| `[CONTEXT] … step 3 …` with `turnComplete: true` (not the recommended form) | no audio | 4/5 (one 1.8 s reply) | in another run: "The cook is moving to step 3, … I will wait" as a caption |
| "Which step am I on?" (after the context lines) | names step 3 | **PASS 5/5** | "Step three, spread rice." |
| "Say that again" | `repeat_instruction`; reply `{"instruction": …}`; read aloud | **PASS 5/5** call, **5/5** read | "Spread a small handful of rice in a thin, even layer, leaving about two centimetres of bare nori along the far edge." |
| "How long do I boil an egg?" | "The chef doesn't cover that…" | **PASS 5/5** | "The chef doesn't cover that in this lesson. In general, a soft-boiled egg takes about six minutes, …" (4/5 added a general tip) |
| Spoken question, 16 kHz PCM | heard and answered | **PASS 1/1** | heard "Why do I need to wet my hands?"; answered with the chef's reason |
| Resume: same token + handle; new token + handle | session continues with history | **PASS 1/1** each (+1 late resume at 160 s) | "Step three, spread rice." |
| Spent token, no handle | refused | **PASS 1/1** | close 1011 "Token has been used too many times" |
| Token as `?access_token=` | session opens | **PASS 1/1** | |

The batch's bar ("[CONTEXT] and the two stay-silent rules hold in at least 4 of 5 attempts") is met: **5/5, 5/5, 5/5**. It was not met by prompt wording alone. What changed between the first and the final run:

1. **First run** (1 attempt, prompt v1): `[CONTEXT]` with `turnComplete: true` was answered with 0.7 s of audible audio (caption `<no speech>{pause}`) 0/2, and stronger wording did not fix it (3.0 s next run). The fix is protocol, not prompt: `turnComplete: false` gives no turn at all.
2. The script first reported "silent after check/next PASS" and "repeat not read aloud": both were **artefacts**. The server closes the tool-call turn (`turnComplete`) right after the `toolCall`, and the script stopped there. Measured properly, the model **spoke after check/next** (2/2, e.g. "Spread the rice thinly and leave about two centimetres…") and **did** read the instruction. API-key tests without the instruction's silence rule behaved the same, so the instruction was not the cause.
3. **`NON_BLOCKING` + `scheduling: "SILENT"`** for the four app-handled commands: silent 5/5 in an API-key test, then 10/10 in the measured run.
4. **Resumption**: the first token locked `sessionResumption: {}`, which replaced the client's handle, so "resuming" started a fresh session (the model answered "Step 1"; the same token was then refused as spent). Resumption is now left out of the lock (`lock_additional_fields=[]`).

Paid usage this batch: 18 minted tokens and about 35 Live sessions (9 in the measured run, the rest debugging; 8 of those opened with the API key to try instruction and protocol variants), each a few short turns; no image or video calls. Cost not measured.

## Footage and evaluation set (AI-03 fills this in)

| Item | Value |
|---|---|
| Chef video location (outside git) | — none filmed. **Team decision 2026-11-14: no cooking.** |
| Recorded with (glasses model / phone) | — |
| Who appears; consent given? | — |
| Dev cases / held-out cases | 0 / 0 labelled |

**Interim development material (not the evaluation set).** With no footage of our own, one third-party stock clip is used **privately** for AI-04 prompt work:

- Mixkit clip 46009, "Sushi rice being flattened while making sushi" (`https://mixkit.co/free-stock-video/sushi-rice-being-flattened-while-making-sushi-46009/`), free 720p version, downloaded 2026-11-14 from `assets.mixkit.co`. Licence shown on the page: **"720p Version for Personal Use only", "Mixkit Restricted License"**; the commercial version is a paid Envato licence. The owner chose private development use only.
- Stored in `ai/footage/mixkit/` (gitignored): the clip, 9 frames every 2.5 s (`frames/`), `contact-sheet.jpg`. **Never commit these, never use them in the fixture the backend serves, in the demo, or in the deck.**
- What it shows: 21.6 s, 1280×720 landscape, 25 fps, true top-down over a bamboo mat. The camera is **opposite the chef** (hands enter from the top of the frame), so it is not first-person; rotated 180° it approximates the wearer's view. Every frame is **mid-step**: rice heaped on half the nori while being spread, bare nori on the other half. No finished state, no deliberate mistakes.
- Useful for: checking the prompts treat work in progress as **not** a mistake (watch → `ok`), and that partly covered views give `unsure`. Not useful for: false-approval or detection numbers. Nothing measured on it may be reported as accuracy.
- Not labelled: labels must be set by a person (AI-03.4).

**What AI-03 still cannot do without real footage:** a labelled dev/held-out set with mistakes, real reference stills for the fixture, the "can a person tell?" check, and every number in EVALUATION.md §4. Options that avoid cooking (a team decision, not made here): ready-made rice and assembly only; non-food props; or a non-food task. Until one is chosen, AI-07's evaluation has no data.

## Check and watch on private dev material (AI-04, 2026-11-14)

> **Dev material, unlabelled, used for tuning. These are not accuracy numbers and must not be reported as such.** Input: the 9 private Mixkit frames (see above), rotated 180° to approximate the wearer's view, step 3 "Spread rice", **no reference image** (`--no-ref`; the fixture's `step-3.jpg` is a text placeholder). Every frame is mid-step: a third to half of the sheet still bare, hands on the rice in most frames. So a `pass` on any of them is wrong by construction, while `fix` or `unsure` are both defensible. No frame shows a listed mistake. Runner: `scripts/dev_eval.py frames footage/mixkit/frames --rotate 180 --step 3 --no-ref`. Resized copies and per-row JSON (with `evidence`) are in the gitignored `ai/footage/dev-variants/`.

**check_frame**: counts are pass / fix / unsure over the 9 frames.

| Round | Prompt / fixture change | Model | Size | pass / fix / unsure | p50 / max ms |
|---|---|---|---|---|---|
| 1 | First prompt, free-text `evidence` | `gemini-3.5-flash-lite` | 1280 | 7 / 1 / 1 | 1349 / 4963 |
| 1 | | `gemini-3.5-flash-lite` | 768 | 7 / 1 / 1 | 1082 / 1202 |
| 2 | Per-criterion check first; `evidence` = met / not met / hidden per criterion; "unfinished work is never a pass"; hands covering → unsure | `gemini-3.5-flash-lite` | 1280 | 4 / 5 / 0 | 973 / 1988 |
| 2 | | `gemini-3.5-flash-lite` | 768 | 6 / 3 / 0 | 953 / 1075 |
| 2 | | `gemini-3.8-flash` (LOW thinking) | 768 | 2 / 3 / 4 | 2541 / 6562 |
| 3 | Sizes judged in proportion ("a bare quarter / third / half is not a narrow strip"); step-3 criteria 2 and 3 reworded in the fixture (below) | `gemini-3.5-flash-lite` | 1280 | 2 / 7 / 0 | 1017 / 1931 |
| 3 | | `gemini-3.5-flash-lite` | 768 | 1 / 8 / 0 | 883 / 949 |
| 3 | | `gemini-3.8-flash` (LOW thinking) | 768 | 0 / 7 / 2 | 2505 / 6003 |
| 3 | | `gemini-3.8-flash`, LOW media resolution | 768 | 0 / 7 / 1, plus 1 `AITimeout` at 8 s | 5116 / 7169 |

What the `evidence` showed: the lite model reads the bare half of the sheet as "2 met: bare strip at top" (the 2 cm margin) and passes. `gemini-3.8-flash` says "bare strip much wider than 2cm" / "half of sheet is bare", and marks criteria hidden when hands cover the rice. Both models give confidence 0.85–0.99 on almost every answer, so the < 0.5 → `unsure` rule hardly ever fires and confidence carries little signal. Answers are **not stable at temperature 0**: frame `0010.00` at 1280 px got `fix rice_too_thick` in the round-3 batch and `pass` from a single CLI call with the same prompt.

**R-02 is materialising.** After three prompt rounds, the pinned check model (`gemini-3.5-flash-lite`) still approves 1–2 of 9 clearly unfinished frames. `gemini-3.8-flash` approved none, but its latency (p50 2.5–5.1 s across runs, max 7.2 s, one timeout in 27 calls) misses the `/check` p50 ≤ 2000 ms target in docs/EVALUATION.md. Choosing between them is a team decision for the next sync. Either way it needs labelled frames (AI-03) before anyone can say how often it happens on real use.

**watch_frame** (one prompt version; the model never writes text): 512 px 9/9 `ok` (confidence 0.80–0.95), 384 px 9/9 `ok` (0.80–0.95). So work in progress was never flagged as a mistake. One extra call on step 4's mistake list (wrong step for the frame) also gave `ok`. **Not tested:** whether watch warns on a real mistake, because no mistake frame exists.

**CLI runs against the real API** (`ai/.env`, Gemini, event key):
- `check --step 3 --frame footage/dev-variants/1280-r180/mixkit-0020.00.jpg --ref fixtures/images/step-3.jpg -v` → `fix`, `mistake_id: null`, headline "Spread rice evenly", 2073 ms.
- `check --step 3 --frame …/1280-r180/mixkit-0010.00.jpg --no-ref -v` → `pass` (a false approval, see above), 2131 ms.
- `watch --step 3 --frame …/512-r180/mixkit-0010.00.jpg -v` → `ok`, confidence 0.8, 1874 ms.
- First smoke call, unrotated frame `0000.00` with the placeholder reference and the first prompt → `fix rice_too_thick` (recipe strings copied), 3646 ms.

The verification commands in the task point at `eval/frames/dev/`, which is empty. The private frames were used from `ai/footage/` instead and were not copied into `eval/` or `fixtures/`. Paid calls this batch: about 104 (`gemini-3.5-flash-lite` and `gemini-3.8-flash`), about 128K input tokens (from the runner and CLI usage counters); cost not measured.

**Fixture change (step 3 criteria wording, AI-04.5 allows criteria wording, not labels):** criterion 2 is now "Only a narrow strip of bare nori, about 2 cm (a tenth of the sheet), remains along the far edge"; criterion 3 is now "Rice covers all the rest of the sheet evenly, right to the near and side edges, without bare patches". Ids, watch_fors and display strings are unchanged.

## Recipe extraction runs (AI-06)

Real run, 2026-11-14, event key, owner's laptop: `python -m ghostchef_ai extract footage/mixkit/mixkit-46009-rice-flattened-720p.mp4 --title "Maki roll" --verbose`. The video is the private stock clip (21.6 s, no narration, rice being spread on nori, top-down from opposite the chef; personal-use licence, gitignored). **It is not a chef take**: it proves the pipeline end to end, nothing about extraction quality on a real lesson. Output was written to a scratch folder only, never into the repository.

| Item | Value |
|---|---|
| Model | `gemini-3.5-flash`, 1 attempt, thinking MINIMAL accepted |
| Upload + processing | 9.4 s |
| Generate | 4.5 s |
| Steps found | 1: "Spread sushi rice evenly", key line "Cover top portion evenly leaving bottom exposed" |
| Transcript | Empty, correct: the clip has no speech and the model invented none |
| `timestamp_s` | 21.0 s (clip 15.0–20.0 s). The frame at 21.0 s still has both hands on the rice, but the clip never reaches a finished state, so this near-last moment is the best available; a timestamp error against a "true" finished state cannot be measured here |
| Criteria | "Rice covers top half of nori in an even, thin layer"; "Bottom half of nori is completely clear of rice". Both visible from above, as the prompt requires; they describe what this clip shows (half the sheet covered, seen from the far side), not our recipe's 2 cm margin |
| Watch-for | `uneven_rice_distribution`: "Rice is piled thicker in the center than near the edges". Plausible and visible |
| Hand-editing needed | Not judged: there is no real lesson to compare against |

The prompt asks for 4–10 steps, but a 21 s clip with one action gave 1, which is the honest answer; `repair` does not force a minimum. Judging step splitting, timestamp accuracy and transcript quality needs a narrated multi-step chef video.

## Results (AI-07 fills this in; copy the table into docs/EVALUATION.md §4 through a `[docs]` commit)

Nothing measured yet.

## Switch to the sandwich lesson (D-19), 2026-11-14

The team replaced the sushi lesson with an assembly-only sandwich (`docs/DECISIONS-AND-RISKS.md` D-19). Done in `ai/`, not yet committed:

- `fixtures/sushi_recipe.json` rewritten as the six-step "Ham and cheese sandwich"; step 4 carries `filling_piled_center` with the contract's exact strings. Transcript is **placeholder narration** (215 words) that answers the new demo question "Why spread it to the edges?". Placeholder images regenerated.
- `prompts/check.md` and `prompts/watch.md` had no dish-specific wording and are unchanged. `prompts/live_system.md`: the one sushi example now uses the sandwich. `fake.py`: "mat" → "board".
- `eval/qa.csv` rewritten (10 in-lesson + 5 out-of-lesson sandwich questions; `demo` = "Why spread it to the edges?"). `eval/README.md`, `scripts/check_cases.py` and `scripts/dev_eval.py` now default to step 4.
- Tests moved to the new fixture (demo step 3 → 4, step without mistakes 2 → 3); the prompt-neutrality tests also forbid sandwich words. `test_ingest.py` and `test_schemas.py` keep `rice_too_thick` as synthetic sample data only. 155 tests pass, ruff clean.
- **Still needed:** the filmed expert sandwich take and mistake clips (AI-03.1–03.4), real stills and transcript in the fixture (AI-03.5), then the dev eval (AI-04.5), the Live re-run (AI-05.3) and extraction on the real video (AI-06.3). The stock maki frames from the earlier no-cooking interim are no longer relevant to the lesson.

## For other tracks: using the package (AI-01)

- Install from `backend/`: `pip install -e ../ai`, set `GHOSTCHEF_AI_FAKE=1` (and `GHOSTCHEF_AI_FAKE_DELAY=0` in tests).
- Call `ghostchef_ai.fake.reset()` between tests: the fake check/watch sequences use per-step counters.
- Fake sequences: `check_frame` → frame under 5000 bytes is `unsure`; otherwise odd calls per step are `fix` with the step's first watch-for, even calls `pass`. `watch_frame` → per step, calls 1–3 `ok`, 4–6 `warn`, repeating. Steps without watch-fors always `pass` / `ok`.
- Fixture: `ai/fixtures/sushi_recipe.json` (historical file name) now holds the **six-step ham and cheese sandwich** (D-19): lay out bread → spread → add lettuce → add fillings → close → cut, with placeholder images `ai/fixtures/images/step-1.jpg` … `step-6.jpg` (720×1280). **The demo mistake is step 4, `filling_piled_center`** ("Filling piled up" / "Spread it to the edges", strings as in API-CONTRACT §2); step 2 has `spread_misses_edges`, step 1 `slices_overlapping`, step 5 `top_slice_misaligned`; steps 3 and 6 have none. Fake check on a small frame now says "Look straight down at board".
- **`check_frame` and `watch_frame` are real from AI-04** (fake mode off + `GEMINI_API_KEY`). `extract_recipe` still raises `AIUnavailable("… not implemented yet …")` until AI-06. BE-03 can switch `GHOSTCHEF_AI_FAKE` off once the AI-04 commit is pushed.
- Behaviour the backend sees (AI-04): `check_frame` retries once on `AIInvalidOutput` inside its `timeout_s`; `watch_frame` never retries. A step with no `watch_fors` makes no watch call and returns `ok` with `model: "none"`. An `unsure` never carries a `mistake_id`. The first call in a fresh process takes ~2 s (client + TLS setup), later ones ~0.9 s: keep one long-lived process. Model switch without code changes: `GHOSTCHEF_MODEL_CHECK`.
- Fixture step 3: success criteria 2 and 3 were reworded in AI-04 (ids and strings unchanged); re-seed if the database copies criteria.
- The OpenAI stand-in still works for check/watch through the same code path (`GHOSTCHEF_PROVIDER=openai`) but is not used.
- **`mint_live_token` is real from AI-05** (fake mode off + `GEMINI_API_KEY`): 245–636 ms warm, ~2.4 s as the first call of a process (n=5). It always returns `locked: true` today. For `GET /live-token` (BE-05): `token`, `expires_at`, `new_session_expires_at`, `locked` come from the `LiveToken`; `model` and `config` from the `LiveConfig`; **`api_version` = `ghostchef_ai.live.LIVE_API_VERSION` (`"v1beta"`)**. The token is single-use for *new* sessions but resumes its own session until `expires_at`, so the phone calls `/live-token` again only after 30 min or an app restart.
- `build_live_config(...).tools` now carries `"behavior": "NON_BLOCKING"` on four declarations; pass `tools` through unchanged.
- `eval/qa.csv` (AI-05.5): 10 in-lesson + 5 out-of-lesson questions on the **placeholder** transcript; id `demo` is beat 6 ("Why do I wet my hands?").

## Needs from other tracks

- **iOS owner (Thomas) — AI-05.4 acceptance:** read "Live facts for `ios/`" above and confirm in chat that it is enough to start IOS-05. Two rules there are not in API-CONTRACT §5 yet and the phone must follow them: (1) send `[CONTEXT]` lines with `"turnComplete": false`; (2) reply to `check_my_work`, `next_step`, `previous_step`, `show_me` with `"scheduling": "SILENT"` beside `response` (not for `repeat_instruction`). Also: server frames are **binary** JSON; ignore the `turnComplete` that follows a `toolCall`; send `sessionResumption: {}` in the setup.
- **Contract wording (docs owner, additive, no field changes):** suggest adding those two wire rules to API-CONTRACT §5.1 and §5.2 through §9, so the contract and the iOS client agree. The tool-response *payloads* in §5.2 are unchanged. §5 also says the Gemini default for `new_session_expires_at` is 1 min; ours is 2 min (as AI-05.2 asks), and resumption still worked after it passed.
- **Backend owner (Stelios) — BE-05:** `api_version` comes from `ghostchef_ai.live.LIVE_API_VERSION`; see "For other tracks" for the reconnect rule (same token resumes; new token only after 30 min or a restart).
- **Real chef transcript (team, from the no-cooking decision):** `eval/qa.csv` and the Live smoke tests use the placeholder narration in the fixture. The demo question in beat 6 is answerable from it; if a real transcript ever replaces it, re-check `qa.csv`.

- **Team decision at the next sync (R-02, from AI-04):** the check model. `gemini-3.5-flash-lite` meets the 2 s target but still passes some clearly unfinished frames; `gemini-3.8-flash` judged the dev material better but took 2–7 s with one timeout. The default stays on lite until decided.
- **Labelled frames (AI-03, team decision "no cooking"):** AI-04.3's "mistake frame → `warn` with the right id" and AI-04.5's confusion tables cannot be done without at least a few labelled dev frames, including mistakes. A non-cooking option is listed under "Footage and evaluation set".

- **Contract wording (docs owner, no rush):** API-CONTRACT §7 says the package reads only `GEMINI_API_KEY` and the four `GHOSTCHEF_MODEL_*` variables, but the package also reads `GHOSTCHEF_AI_FAKE`, `GHOSTCHEF_AI_FAKE_DELAY` and `GHOSTCHEF_FIXTURE_DIR` (all specified by AI-01 and referenced by the backend tasks). Suggest listing them in §7 as an additive change. Nothing is blocked.
