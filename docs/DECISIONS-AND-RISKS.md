# Ghost Chef — decisions, risks, open questions

> Decisions are settled unless the team changes them here. Risks each have an owner and a next test. Open questions are things only a person on site or an account owner can answer.
> Last updated 2026-11-13.

## 1. Decisions

| # | Decision | Source | Reason | Reversible? |
|---|---|---|---|---|
| D-01 | Main challenge **Meta — AI Glasses for Everyone, Everyday**; technology challenge **Google DeepMind — Best Use of Gemini API** | Team | — | Settled |
| D-02 | **Arduino is excluded**: no boards, no edge-AI scoring, no Arduino submission | Team | A Meta representative's earlier suggestion to combine them was superseded | Settled. Do not reopen |
| D-03 | Native **DAT SDK on iOS**, not the Display Web Apps route | TECH-SPEC | Web Apps expose no camera; the app needs it. The teammate with a Mac and iPhone owns it | Settled |
| D-04 | Thin **FastAPI** backend on **Railway** | TECH-SPEC | Keys off the phone; long video jobs; ffmpeg | Hosting is reversible: an emergency laptop runs the same code |
| D-05 | **Supabase** for Postgres and Storage | TECH-SPEC | Managed, signed URLs | A `memory` store stays available as fallback |
| D-06 | **Gemini Live opened directly from the phone** with an ephemeral token minted by the backend | TECH-SPEC | Lowest voice latency; key stays server-side | Yes: Live is item 10 in the cut order |
| D-07 | The proactive watcher is a **polling classifier with debounce**, not Gemini Live | TECH-SPEC | Live over-talks or stays silent; polling is controllable | Settled |
| D-08 | One **seeded, pre-ingested sushi recipe**; the demo never depends on live ingestion | TECH-SPEC | Demo safety | Settled |
| D-09 | Work is split into **four tracks = four folders** (`ios/`, `backend/`, `ai/`, `web/`), one laptop each, no shared files | Team (2026-11-13) | Four laptops in parallel without merge conflicts | Settled |
| D-10 | Contract additions over TECH-SPEC: `unsure` verdict, `request_id` + stale-result rule, `watch_fors` ids, publish/delete/consent, monitor endpoints, Live function calls, the `ghostchef_ai` package boundary | Proposed in this plan; listed in [API-CONTRACT §10](API-CONTRACT.md#10-differences-from-tech-spec) | Needed to make the spec buildable in parallel and to cover the trust criterion | **Yes — team should confirm or strike individual items** |
| D-11 | A **web simulator** and a **demo monitor** are added to the `web/` track | Proposed in this plan | End-to-end testing without the Mac; the audience cannot see a lens | Yes. Monitor polish is item 7 in the cut order |
| D-12 | `spoken` results use **on-device text-to-speech**; Gemini Live speaks only answers to questions | Proposed in this plan | One deterministic path; works when Live is down; no double speech | Yes |
| D-13 | **Mock-first**: fake-mode AI package and a full mock API in the first hours | Proposed in this plan | Nobody waits for anybody | Yes |
| D-14 | Trunk-based git on `main`, commits scoped to one track folder | Proposed in this plan | Simplest thing that cannot conflict | Yes |

## 2. Risks

Likelihood / impact: H, M, L. Ordered by how much they threaten the core demo.

| # | Risk | L | I | Owner | Next test / mitigation | Fallback |
|---|---|---|---|---|---|---|
| R-01 | **No Display pair when we need it.** Ten Display and ten Gen 2 pairs are shared by all teams; nothing is booked | H | H | ios | Ask the booth tonight: how booking works, for how long, whether a pair can be held for the demo slot | Build on `MockDeviceKit` + phone camera; plan access windows; audio-only on a Gen 2 pair |
| R-02 | **A single frame cannot separate "too much rice" from "right".** POV distance, white rice on dark nori, glare | M | H | ai | AI-03 films it tonight/tomorrow; AI-04 runs the first 10 frames by hand before anything else | Choose a more visible scripted mistake (rice covering the top margin; filling in the wrong place); make the criterion "can you see nori at the top edge" |
| R-03 | **Camera + display + Bluetooth audio at once** was confirmed only verbally | M | H | ios | IOS-02 proofs (d) and (f) | Display + check without Live; or audio through the phone speaker |
| R-04 | **Neural Band gestures may not reach a DAT app on iOS.** The changelog shows only an experimental inputs module and display buttons | M | M | ios | IOS-02 proof (e) | Display buttons, captouch tap, voice commands; the phone as a remote in the operator's hand |
| R-05 | **iOS DAT help on site may be thin.** The named mentor is an Android DAT mentor | M | M | ios | Ask at the booth who knows the iOS SDK; install Meta's Claude Code plugin and docs MCP | Rely on the samples in the SDK repo |
| R-06 | **One Mac.** Every iOS task queues behind one machine and one person | H | M | ios | Keep everything that is not Swift out of `ios/`; the web simulator covers backend/AI testing | Second person pairs at the Mac during IOS-06 |
| R-07 | **Gemini quota or latency** makes the watcher unusable | M | M | ai | AI-02 reads real limits and measures a latency baseline | Slower interval; smaller model; on-demand check only |
| R-08 | **Live from Swift over a raw WebSocket** takes longer than planned | M | M | ios | Verify the endpoint and message shapes in the current reference before coding; timebox | Cut function calls, then cut Live (cut order 8, 10) |
| R-09 | **Stage noise** breaks voice | H | M | ios | Push-to-talk toggle; test near the stage | Skip the question beat; captions on the lens |
| R-10 | **Venue Wi-Fi** unreliable | H | M | backend | Hotspot test; emergency laptop backend | Hotspot + laptop |
| R-11 | **Sushi logistics.** Ingredients, cooked rice, a place to film, knives, hygiene with shared glasses | M | M | web | Buy and cook on Saturday morning; ask organizers about food and knives at the stand | A non-food stand-in is a different product: avoid; simplify to nori + rice only |
| R-12 | **Stage lighting** differs from where prompts were tuned | M | M | ai | Capture held-out frames at the actual demo spot | Small light in the kit; `unsure` when too dark |
| R-13 | **Integration happens for the first time on Sunday** | M | H | backend | Gates G1 and G2 require integrated runs; the smoke script runs after every backend push | — |
| R-14 | **Accounts and credits**: Gemini credits not yet received; Supabase and Railway projects not yet created; Wearables Developer Center registration not yet done | M | H | each track | First task of AI-02, BE-02, BE-04, IOS-02 | Free tiers; emergency laptop |
| R-15 | **Rules we have not read**: pre-existing code, licence, video, edits after deadline | L | M | web | Read the participant terms on the platform | — |
| R-16 | **Overclaiming** on device support, accuracy, or pilot | M | M | web | Deck numbers come only from EVALUATION.md; claims table in PRODUCT.md §10 | — |
| R-17 | **Country or account restrictions** on the glasses' developer features | L | H | ios | Ask the booth; they supply the devices | Whatever Meta staff configure on the loan devices |
| R-18 | **Too many additions** (simulator, monitor, `unsure`, function calls) dilute the core | M | M | all | Cut order in PLAN.md §6; gates forbid optional work before the core loop | Strike items of D-10 / D-11 |

## 3. Open questions

| # | Question | Who can answer | Blocks |
|---|---|---|---|
| Q-01 | Which glasses do we get, when, for how long, and can we keep a pair for the demo? | Meta booth | IOS-02, IOS-06, the demo |
| Q-02 | Who on site supports the **iOS** DAT SDK? | Meta booth | IOS-02 |
| Q-03 | Do Neural Band gestures reach a DAT app, or only display buttons and captouch? | Meta booth / IOS-02 | Input mapping |
| Q-04 | Has the team received Gemini credits, and on which project and tier? | Team / Google booth | AI-02 |
| Q-05 | ~~Who owns which track?~~ **Answered 2026-11-14:** iOS = Thomas, backend = Stelios, AI = Aleksandr, web = Türker | Team | Resolved |
| Q-06 | ~~Who has the larger Claude allowance?~~ **Answered 2026-11-14: the Mac owner**, who owns `ios/` | Team | Resolved |
| Q-07 | What does the preliminary submission require, and by exactly when? | Platform / organizers | Tonight |
| Q-08 | Pitch length, review format, required submission fields, video rules | Organizers / authenticated platform | WEB-05 |
| Q-09 | Are cooked food and knives allowed at the stand and on stage? | Organizers | Demo |
| Q-10 | Is there a real cooking instructor we can talk to before Sunday? | Team's network | Pilot claim |
| Q-11 | `CONCEPT.md`, referenced by TECH-SPEC, is not in the repository | Team | Nothing critical; add it if it exists |
| Q-12 | Is the product name "Ghost Chef" final? (The repository is named `statai`) | Team | Submission title |
