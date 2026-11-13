# Ghost Chef — build plan

> Who builds what, in which order, and what gets cut. Written Friday 13 Nov 2026, 23:00 Helsinki time, with **no code in the repository yet**.
> Status of each batch is tracked in the owning track's `STATUS.md`, not here.

## 1. Time

| | Local time (EET) | Source |
|---|---|---|
| Hacking started | Fri 13 Nov, 19:30 | Event homepage |
| This plan written | Fri 13 Nov, ~23:00 | — |
| Preliminary submission | Fri 13 Nov, 23:55 (platform) or 23:59 (homepage) | Conflict, see [EVENT-CONTEXT.md](EVENT-CONTEXT.md) |
| Final submission | Sun 15 Nov, 10:00 | Both public sources |

About **35 hours** remain to the final deadline, including sleep, meals, hardware pickup, and rehearsal. The gates below are ordered checkpoints; the clock times next to them are suggestions the team can move. What must not move is the order: the core loop is proven before anything optional is started.

## 2. Four tracks, four folders, four laptops

Each laptop works in exactly one folder. No two tracks ever edit the same file, so `git pull --rebase` never conflicts.

| Track | Folder | Machine | Size | Owner | What it delivers |
|---|---|---|---|---|---|
| **iOS** | [`ios/`](../ios/README.md) | **The Mac** (Xcode) + iPhone | **Largest and riskiest — 7 batches** | **Thomas** (the Mac; largest Claude allowance) | The app on the phone and glasses |
| **Backend** | [`backend/`](../backend/README.md) | Any | Large — 7 batches, integration hub | **Stelios** | API, storage, ffmpeg, deploy, end-to-end tests |
| **AI** | [`ai/`](../ai/README.md) | Any | Medium — 7 smaller batches, one is physical (filming) | **Aleksandr** | Every prompt and Gemini call, fixture recipe, evaluation |
| **Web** | [`web/`](../web/README.md) | Any | Medium-light in code — 5 batches; carries users, pitch, demo, submission | **Türker** | Simulator, chef studio, demo monitor, pitch pack, submission |

**Owners** were assigned by the team on 2026-11-14. The `ai/` and `web/` assignment was arbitrary (either person could take either) and the two may swap by agreement. TECH-SPEC lists the Gemini SDK calls and the chef UI under Stelios; in this four-way split they move to `ai/` (Aleksandr) and `web/` (Türker), and Stelios's backend imports and serves them.

**The heavier load.** The Mac owner has the largest Claude allowance (team, 2026-11-14), and `ios/` is the largest and riskiest track, so the two line up: no rebalancing is needed. `backend/` is the second-largest. The limit on `ios/` is time at the one Mac, not usage, so a second person pairs there during IOS-06 (risk R-06).

**Hand-over rule.** A batch may be run by someone outside the track only when the track owner hands it over explicitly and stops working in that folder until the batch is pushed. One writer per folder at a time.

### 2.1 What nobody owns alone

| Path | Rule |
|---|---|
| `docs/API-CONTRACT.md` | Changed only through its §9 protocol |
| `docs/TECH-SPEC.md` | The team's concept. Not edited |
| Other `docs/*`, `README.md`, `CLAUDE.md` | Changed deliberately, in a commit that touches nothing else, prefix `[docs]` |
| `<track>/STATUS.md` | Each track updates its own after every batch. This is where live state goes |

## 3. Batches and dependencies

A batch is one markdown file with a group of tasks. One Claude session runs one batch.

```
            G0                 G1                    G2                  G3                 G4        G5
 ai/      01 ──► 02 ──► 04 ──────────► 05 ──────────► 06 ──────────────► 07
                  └──► 03 (filming) ───────────────────────────────────► 07
 backend/ 01 ──► 02 ──► 03 ──────────► 04 ──────────► 05 ──► 06 ───────► 07
 ios/     01 ──► 02 (spike) ──► 03 ──► 04 ──────────► 06 / 05 ─────────► 07
 web/     01 ──────────────────► 03 ──────────────► 02 ──► 04 (draft) ──► 04 (final) ──► 05
          05 task 1 (preliminary submission) is done first, tonight; the rest of 05 closes at G5.
```

Cross-track dependencies (everything else is internal to a track):

| Batch | Needs first | Why |
|---|---|---|
| BE-01 | AI-01 | Imports `ghostchef_ai` in fake mode and seeds from the fixture |
| IOS-01, WEB-01 | BE-01 running anywhere reachable | A mock API with every endpoint in contract shape. Both can start on bundled fixtures before it is up |
| BE-03 | AI-04 | Real `check_frame` / `watch_frame` |
| BE-02 (seed with real stills) | AI-03 footage | Until then it seeds placeholder images |
| BE-05 | AI-05 | Live config and token minting |
| IOS-05 | BE-05 | A real `/live-token` |
| BE-06 | AI-06 | Real `extract_recipe` |
| WEB-02 | BE-06 for the real thing | Buildable earlier against the mock, which simulates `processing → review` |
| IOS-06 | IOS-02 result + glasses in hand | Device facts decide the display and input mapping |
| AI-07 | AI-03, AI-04, BE-04 | Eval frames, final prompts, deployed latency |
| WEB-04 | AI-07 results, IOS-06 | Evidence slide and device claims use measured values only |

**Mock-first is the rule that makes four laptops parallel:** AI-01 ships a fake-mode package, BE-01 ships every endpoint on top of it, and both clients build against that. Real implementations then replace fakes behind unchanged interfaces.

## 4. Gates

A gate is passed when its exit criteria are demonstrated to the team, not when someone says it is nearly done. Do not start work that belongs after a gate until the gate is passed, except the batches listed as parallel.

### G0 — Everyone unblocked · suggested Sat 01:30

- [ ] AI-01, BE-01, IOS-01, WEB-01 pushed.
- [ ] `GET /health` answers on a teammate's laptop over the LAN with `ai_mode: fake`.
- [ ] The iOS app lists the fixture recipe from that server. The web simulator does too.
- [ ] A Gemini API key exists and one real call succeeded (start of AI-02).
- [ ] Someone asked the Meta booth: can we get a Display pair, when, for how long, and who helps with **iOS** DAT. Answers written in `ios/STATUS.md`.
- [ ] Preliminary submission handled (see [DEMO-AND-SUBMISSION.md](DEMO-AND-SUBMISSION.md#6-submission-checklist)).

### G1 — First real loop · suggested Sat 11:00

- [ ] A real camera frame (webcam in the simulator is enough) gets a real Gemini verdict against a real reference image, through `/check`.
- [ ] IOS-02 spike results are written down: each of the seven proofs is PASS, FAIL, or NOT TESTED with a reason.
- [ ] Chef footage of the sushi recipe exists (AI-03), with deliberately wrong takes.
- [ ] Decision taken and recorded: Display + gestures as specified, or one of the fallbacks in [DECISIONS-AND-RISKS.md](DECISIONS-AND-RISKS.md).

### G2 — Core journey · suggested Sat 16:00

- [ ] On the iPhone (phone camera is acceptable here): pick recipe → step card → check → fix → re-check passes → next step.
- [ ] The watcher raises the scripted "too much rice" warning on real rice and stays quiet on a correct layer, at least once each.
- [ ] Backend is deployed (BE-04) with Supabase and the real seeded recipe.
- [ ] The monitor shows the session live.

### G3 — Feature freeze · suggested Sat 22:00

- [ ] The G2 journey runs **on the glasses** (camera from the glasses, card in the lens or the agreed fallback).
- [ ] Voice: one spoken question is answered from the chef's method; "check" and "next" work by voice.
- [ ] Chef studio: upload → review → publish works on one real video.
- [ ] Evaluation run #1 exists in `ai/eval/results/`.
- [ ] Deck draft exists. A backup recording of one full run exists.
- [ ] **After this gate no new feature is started.** Only fixes, tuning, and demo hardening.

### G4 — Demo-ready · suggested Sun 07:30

- [ ] Three consecutive clean runs of the demo script by someone who is not the developer of the app.
- [ ] Each failure in the [recovery checklist](EVALUATION.md#6-recovery-tests) was triggered once and behaved as documented.
- [ ] Evaluation results and measured latency are in the deck; every claim in the deck matches the build.
- [ ] Demo kit packed and reset procedure rehearsed.

### G5 — Submitted · suggested Sun 09:00 (official deadline 10:00)

- [ ] Submission form complete, every link opens in a private browser window, confirmation saved.
- [ ] No code changes after submission unless the rules allow them.

## 5. Sync ritual

Every ~3 hours, 10 minutes, standing, at one screen:

1. **Show** the integrated thing working (not a description of it).
2. Each track: which batch is done, which is running, what is blocking.
3. Name the single biggest risk right now and who tests it next.
4. Apply the cut order if a gate is late.

Between syncs, cross-track requests go in the team chat and in the requester's `STATUS.md` under "Needs from other tracks".

## 6. Cut order

Cut from the top. Never cut from the bottom group.

| Order | Feature | If cut |
|---|---|---|
| 1 | Personalization, accounts, other domains | Already cut; "what's next" slide |
| 2 | Timer widget | Nothing in the demo needs it |
| 3 | Done summary screen | End on the last Pass |
| 4 | In-app chef recording through DAT | Upload an MP4 instead |
| 5 | "Show me" clips | The reference still stays |
| 6 | Studio: re-pick frame with a video scrubber | Edit text only; timestamps typed as numbers |
| 7 | Monitor polish (timeline, latency panel) | Keep frame + reference + verdict |
| 8 | Voice commands as function calls | Keep spoken Q&A; gestures do the commands |
| 9 | Live ingestion shown in the demo | Show the studio on a pre-ingested recipe |
| 10 | Gemini Live voice Q&A | Loses a Gemini talking point; core loop intact |
| 11 | Proactive watcher on the glasses | On-demand check only |
| 12 | In-lens display | Audio-only on the glasses, lens mirrored on the monitor |

**Never cut — this is the project:** a frame from the glasses → Gemini compares it with the chef's reference → the wearer is told pass / fix / can't tell → they fix it → the re-check passes. If the glasses themselves are unobtainable, the phone camera is a development fallback and is described as such; it does not satisfy the Meta requirement.

## 7. Working with Claude on each laptop

1. `git clone https://github.com/thomasdevving/statai && cd statai` (or `git pull --rebase origin main`).
2. Open Claude Code **in the repository root**, so `CLAUDE.md` loads.
3. Start one batch with this prompt, replacing the two placeholders:

   ```
   I own the <track> track. Read CLAUDE.md, README.md, docs/API-CONTRACT.md and <track>/README.md,
   then carry out <track>/tasks/<NN-name>.md completely. Work only inside <track>/.
   Run the batch's verification commands. When every acceptance criterion passes, update
   <track>/STATUS.md and stop. If something outside <track>/ blocks you, write it under
   "Needs from other tracks" in STATUS.md and tell me instead of working around it.
   ```
4. Review, then commit with the track prefix and push: `git pull --rebase origin main && git push`.
5. Start a **fresh** Claude session for the next batch. Batches are written to be self-contained, and a fresh session keeps context small.

**Models.** Opus 5.5 for every batch by default. Each batch file names the tasks where a smaller model (Sonnet 5.5 or Haiku 5.5) is enough: status updates, fixture edits, copy changes, simple styling, labelling helpers.

## 8. Definition of done

A feature is demo-ready when: its intended path works **on the relevant device**; its main failure behaviour is the one documented; **another teammate can operate it**; and its real state is written in the track's `STATUS.md`. A successful isolated API response is not proof that the wearer's experience works.

Reporting vocabulary used in every `STATUS.md`:

| Word | Meaning |
|---|---|
| `DONE` | Acceptance criteria met and verified in this state of `main` |
| `DONE (fake)` | Works against fake mode or fixtures only |
| `PARTIAL` | Listed criteria that pass, listed criteria that do not |
| `BLOCKED` | Cannot proceed; names what is needed and from whom |
| `NOT STARTED` | — |
