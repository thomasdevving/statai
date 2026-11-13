# Junction 2026 — event context

> A compact extract of what affects the build. The full research, with every source and its limits, is [research/JUNCTION_2026_CONTEXT.md](research/JUNCTION_2026_CONTEXT.md) (checked 2026-11-13).
> Labels: **[VERIFIED]** retrieved from an organizer or vendor source · **[TEAM]** supplied by the team from the challenge briefs · **[OPEN]** unresolved.

## 1. Event

- **Junction 2026: European Tech Renaissance**, 13–15 November 2026, Hype Areena, Espoo. Teams of 1–4. **[VERIFIED]** ([platform](https://hackjunction.app/hackathons/junction-2026), [site](https://2026.hackjunction.com/))
- All times are Helsinki time (EET, UTC+2).

| When | What | Source |
|---|---|---|
| Fri 13 Nov 19:30 | Hacking starts | Homepage |
| Fri 13 Nov 23:55 | Preliminary submission | Platform — **the homepage says 23:59** |
| Sat 14 Nov 12:00 | Submissions open | Platform |
| Sun 15 Nov 10:00 | **Final submissions** | Both |
| Sun 15 Nov 10:30 | Review starts | Homepage — **the platform says 14:00** |
| Sun 15 Nov 17:00 | Event ends | Platform |

Plan against the earlier time wherever the two sources disagree, and check organizer announcements.

## 2. Our challenges

**Main: Meta — AI Glasses for Everyone, Everyday. [TEAM]**
A functional prototype showing how the first-person field of view makes an everyday interaction possible or meaningfully better. Mirroring a phone screen is not enough. Audio-first and display experiences are judged equally. Mobile integrations through the Device Access Toolkit and web apps are both accepted.

Required: working prototype, deck, a clear intended audience, a plausible adoption or pilot path. The brief stresses accessibility, consent, responsible data handling, and behaviour when permissions, connectivity, or device state change.

| Criterion | Weight |
|---|---|
| Creativity and use case | 25% |
| Technical execution | 25% |
| Real-world value and feasibility | 25% |
| UX, accessibility, and trust | 25% |

Resources: ten shared Ray-Ban Meta Display pairs and ten shared Ray-Ban Meta Gen 2 pairs; on-site developer support; contact Amanda Le, listed as the Android DAT mentor. **No pair is confirmed for this team. [OPEN]**

**Technology: Google DeepMind — Best Use of Gemini API. [TEAM]**
Explain the problem, the integration, what is innovative or technically impressive, and why Gemini matters. A finished product with a chatbot bolted on is a weak fit. Credits reportedly for up to 400 teams; participants must be 18 or older. **Whether this team has received credits is [OPEN].**

**Arduino is excluded** by team decision. One main challenge plus any number of technology challenges is the rule as the team reports it.

## 3. Judging

- Partner winners are chosen by the partners. **[VERIFIED]**
- Face-to-face **peer review** selects five overall finalists; a live pitch to the grand jury decides the overall winner. **[VERIFIED]** ([site](https://2026.hackjunction.com/))
- Published jury priorities include meaningful problems, evaluation of failure, repeat use, pragmatic insight, and production feasibility. **[VERIFIED]** Prepare for: does anyone need it, does it actually work, what is the insight, what happens after Sunday.

How we answer each audience: [DEMO-AND-SUBMISSION.md §1](DEMO-AND-SUBMISSION.md#1-who-sees-it-and-what-they-need) and [EVALUATION.md §1](EVALUATION.md#1-criteria--evidence).

## 4. Rules to confirm

- The FAQ states team ownership and **MIT-licensed submissions**. **[VERIFIED]**
- The terms page returned no readable text during research, and the authenticated participant guide and submission form were not inspected. Rules on pre-existing code, repository visibility, video length, pitch duration, and edits after the deadline are **[OPEN]**.

## 5. Technical facts checked on 2026-11-13

These were read in vendor documentation that evening. They show a supported route exists; they do not show that it works on our account or on a borrowed device.

**Meta Device Access Toolkit, iOS** — [changelog](https://github.com/facebook/meta-wearables-dat-ios/blob/main/CHANGELOG.md), [repository](https://github.com/facebook/meta-wearables-dat-ios), [FAQ](https://developers.meta.com/wearables/faq/)

- Latest release **1.0.1** (2026-10-09); 1.0.0 was 2026-09-24. Developer preview. Swift Package URL `https://github.com/facebook/meta-wearables-dat-ios`.
- Minimum **iOS 17.2** since 0.9.0.
- **Display module `MWDATDisplay`** since 0.7.0, with `FlexBox`, `Text`, `Button`, `Image`, `Icon`, `VideoPlayer`; `ButtonGroup` since 0.9.0; `Display.clearDisplay()`; `DeviceType.supportsDisplay`.
- Camera: `StreamingResolution.Medium` is 504×896; 720×1280 can be requested; codecs `raw` and `hvc1`; raw `CMSampleBuffer` exposed on `VideoFrame`. Photo capture and camera audio streaming are marked experimental.
- 1.0.0 adds **experimental** `MWDATInputs`, `MWDATMotion`, `MWDATSpeech` modules and voice invocations. **The changelog does not mention the Neural Band.**
- **`MockDeviceKit`**: phone-camera mock feed, `pairGlasses(model:)`, captouch simulation, mock display preview.
- Supported devices per the FAQ: Ray-Ban Meta Gen 1 and Gen 2, Meta Ray-Ban Display, Oakley Meta HSTN and Vanguard. Developer Mode is enabled through the Meta AI app. Full capabilities are limited to "AI glasses supported countries".
- The FAQ's list for **Web Apps** on Display covers position, location, Neural Band wrist motion and input; it lists no camera access.
- Meta ships a Claude Code plugin and a docs MCP server for the SDK (commands in [ios/README.md](../ios/README.md)).

**Gemini API** — [models](https://aistudio.google.com/docs/models), [ephemeral tokens](https://aistudio.google.com/docs/live-api/ephemeral-tokens) (the `ai.google.dev/gemini-api/docs` URLs now redirect there)

- Models listed publicly: `gemini-4-carbon`, `gemini-4-argon`, `gemini-4-hydrogen`; stable `gemini-3.8-flash`, `gemini-3.6-flash`, `gemini-3.5-flash-lite`, `gemini-3.1-flash-lite`; Live `gemini-3.8-live`, `gemini-3.8-live-extended-thinking`.
- `gemini-2.5-flash` and `gemini-2.5-pro` are deprecated; from 1 December 2026 requests to them are rerouted to newer models. `gemini-2.0-flash` is shut down.
- **Ephemeral tokens** (preview, Live API only, API version `v1beta`): created with `client.auth_tokens.create(...)`; defaults are one use, one minute to open a session, thirty minutes to send messages; can be locked to a model and configuration; a client without the SDK passes the token as an `access_token` query parameter or an `Authorization: Token …` header.
- Rate limits are per project and tier. Credits do not tell us the throughput.

**Not checked:** the Live API WebSocket endpoint and message format (the page could not be fetched), DAT input and display layout limits, and anything requiring an account or a device. The tracks verify these in IOS-02, IOS-05, and AI-02.

## 6. What past winners suggest

Analysis, not a formula; detail and sources are in the research file §7–§8. A strong entry makes one valuable, distinctive capability work, makes its operation visible to people who are not using it, and shows enough evidence to be believed. For us: prove the glasses-to-verdict loop early, make it visible on the monitor, measure it honestly, keep the scope small.
