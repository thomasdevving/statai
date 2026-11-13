# Echo

**A chef records a recipe once through smart glasses. Anyone wearing the glasses can then cook it hands-free while Gemini compares what they are doing with the chef's own point-of-view footage, corrects mistakes as they happen, and answers questions in the chef's method.**

Built at **Junction 2026** (13–15 November, Espoo) for two challenges: **Meta — AI Glasses for Everyone, Everyday** (main) and **Google DeepMind — Best Use of Gemini API** (technology).

> **Status, Friday 13 November 2026, 23:00:** planning complete, **no code yet**. Nothing described in this repository has been built, run on glasses, or measured. Live state is in each track's `STATUS.md`.

## Start here

Four people, four laptops, four folders. You work in exactly one folder, so nobody's changes collide.

| Owner | Track | Open | Machine | First batch |
|---|---|---|---|---|
| **Thomas** | The iPhone / glasses app | [ios/README.md](ios/README.md) | **The Mac** + an iPhone | [IOS-01](ios/tasks/01-project-foundation.md) |
| **Stelios** | The API, storage, deployment | [backend/README.md](backend/README.md) | Any | [BE-01](backend/tasks/01-skeleton-and-mock-api.md) |
| **Aleksandr** | Prompts, Gemini calls, evaluation | [ai/README.md](ai/README.md) | Any | [AI-01](ai/tasks/01-package-skeleton-and-fixture.md) |
| **Türker** | Web tools, pitch, demo, submission | [web/README.md](web/README.md) | Any | [WEB-05 task 1](web/tasks/05-demo-ops-and-submission.md), then [WEB-01](web/tasks/01-foundation-and-simulator.md) |

Track sizes and the hand-over rule: [docs/PLAN.md §2](docs/PLAN.md#2-four-tracks-four-folders-four-laptops).

### On your laptop

```bash
git clone https://github.com/thomasdevving/statai
```

```bash
cd statai
```

Open Claude Code **in the repository root** (so [CLAUDE.md](CLAUDE.md) loads) and start one batch with:

```
I own the <track> track. Read CLAUDE.md, README.md, docs/API-CONTRACT.md and <track>/README.md,
then carry out <track>/tasks/<NN-name>.md completely. Work only inside <track>/.
Run the batch's verification commands. When every acceptance criterion passes, update
<track>/STATUS.md and stop. If something outside <track>/ blocks you, write it under
"Needs from other tracks" in STATUS.md and tell me instead of working around it.
```

Review what it did, commit with your track's prefix (`[ios]`, `[backend]`, `[ai]`, `[web]`), then `git pull --rebase origin main` and push. Start a fresh Claude session for the next batch. Use Opus 5.5 unless the batch file says a smaller model is enough.

### Tonight, before anything else

1. **Preliminary submission** is listed for 23:55 tonight on the event platform → [WEB-05 task 1](web/tasks/05-demo-ops-and-submission.md).
2. **Ask the Meta booth** about borrowing a Display pair and who supports the iOS SDK → questions in [IOS-02](ios/tasks/02-dat-glasses-spike.md#before-coding-human-at-the-meta-booth--do-this-tonight).
3. **Get a Gemini API key** → [AI-02 task 1](ai/tasks/02-gemini-access-and-models.md).
4. Push **AI-01**, then **BE-01**: the other two tracks build against them.

## How the pieces fit

```
 Meta glasses ⇄ ios/ (iPhone app) ──HTTPS──► backend/ (FastAPI) ──imports──► ai/ (ghostchef_ai) ──► Gemini API
                     │                            │        ▲
                     └──WebSocket──► Gemini Live   │        └── web/ (simulator · review page · demo monitor)
                                                   ▼
                                               Supabase
```

| Folder | What it is | Batches |
|---|---|---|
| [`ios/`](ios/README.md) | Swift app, two modes: **Chef** (record through the glasses, pinch = step mark, upload) and **Cook** (frames from the glasses, cards in the lens, watcher loop, voice) | 8 |
| [`backend/`](backend/README.md) | FastAPI: recipes, `/check`, `/watch`, sessions, live tokens, ffmpeg, deploy | 7 |
| [`ai/`](ai/README.md) | Python package with every prompt and Gemini call; fixture recipe; evaluation | 7 |
| [`web/`](web/README.md) | Browser simulator, review page (review / edit / publish + dev MP4 upload), demo monitor; pitch pack and submission | 5 |
| [`docs/`](docs/) | Shared, slow-changing documents (below) | — |

Each track folder has a `README.md` (setup, design, rules), a `STATUS.md` (what is actually done and measured), and `tasks/` — one markdown file per batch of tasks, each with concrete acceptance criteria.

## Documents

| Document | Read it for |
|---|---|
| [docs/TECH-SPEC.md](docs/TECH-SPEC.md) | **The team's concept**: summary, stack, flows, display spec, scope. The starting point for everything else |
| [docs/API-CONTRACT.md](docs/API-CONTRACT.md) | **Every interface between tracks**: HTTP API, data model, the `ghostchef_ai` package, client rules. Wins over any other description |
| [docs/PLAN.md](docs/PLAN.md) | Tracks and owners, batch dependencies, gates G0–G5, cut order, how to work with Claude |
| [docs/PRODUCT.md](docs/PRODUCT.md) | Problem, audience, why glasses, trust and accessibility, pilot path, what we may claim |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Components, technology roles, device and API assumptions with their status, failure behaviour, security |
| [docs/EVALUATION.md](docs/EVALUATION.md) | Judging criteria → evidence, the evaluation set, targets vs. measured results, recovery tests |
| [docs/DEMO-AND-SUBMISSION.md](docs/DEMO-AND-SUBMISSION.md) | Demo script, what the audience sees, failure playbook, deck outline, submission checklist |
| [docs/DECISIONS-AND-RISKS.md](docs/DECISIONS-AND-RISKS.md) | Settled decisions, risks with owners, open questions |
| [docs/EVENT-CONTEXT.md](docs/EVENT-CONTEXT.md) | Schedule, challenge briefs and rubric, judging, technical facts checked on 13 Nov |
| [docs/research/JUNCTION_2026_CONTEXT.md](docs/research/JUNCTION_2026_CONTEXT.md) | The full background research with sources |
| [CLAUDE.md](CLAUDE.md) | Short rules every Claude session in this repository follows |

## Where to see what is real

| Question | Look at |
|---|---|
| Which batches are done? | `ios/STATUS.md`, `backend/STATUS.md`, `ai/STATUS.md`, `web/STATUS.md` |
| What works on the glasses? | [ios/STATUS.md](ios/STATUS.md) → Device facts, End-to-end runs |
| Where is the API running? | [backend/STATUS.md](backend/STATUS.md) → Where the API is |
| Which Gemini models, what limits, what accuracy? | [ai/STATUS.md](ai/STATUS.md) |
| Is it submitted? | [web/STATUS.md](web/STATUS.md) → Submission |

## Ground rules

- One folder per person. Shared documents change deliberately, in their own commit.
- Change an interface in [docs/API-CONTRACT.md](docs/API-CONTRACT.md) first, then in code.
- Write down only what you ran and saw. Targets and results are kept apart.
- The repository is public: no keys, tokens, faces, or raw footage.
- When time runs out, cut from the top of the [cut order](docs/PLAN.md#6-cut-order), never the core loop.

## Licence

To be added before submission. The event FAQ states MIT-licensed submissions; the team confirms the requirement first ([WEB-05](web/tasks/05-demo-ops-and-submission.md)).
