# Ghost Chef — evaluation and judging evidence

> What we have to be able to show, how we measure it, and the results once they exist.
> **Every number in this file is either a proposed target (marked TARGET) or a measured result with its date and conditions. As of 2026-11-13 nothing has been measured.**
> The evaluation is built and run by the `ai/` track ([ai/tasks/03](../ai/tasks/03-footage-and-eval-set.md), [ai/tasks/07](../ai/tasks/07-evaluation-and-tuning.md)); observed user sessions by the `web/` track ([web/tasks/04](../web/tasks/04-user-evidence-and-pitch-pack.md)).

## 1. Criteria → evidence

### Meta — AI Glasses for Everyone, Everyday (four equal quarters, as reported by the team)

| Criterion | What we show | Where it comes from |
|---|---|---|
| Creativity and use case | The chef's first-person reference next to the learner's first-person frame; why a propped phone cannot do this | Demo monitor, PRODUCT.md §4 |
| Technical execution | Glasses frame → Gemini → lens + audio, live; architecture slide; measured latency; one recovery shown on purpose | IOS-06, monitor latency panel, §6 below |
| Real-world value and feasibility | Named audience, the task, notes from observed novice sessions, a proposed pilot with a measurable outcome | WEB-04, PRODUCT.md §9 |
| UX, accessibility, trust | Two-line lens, one spoken sentence, "can't tell" outcome, watching indicator, consent + delete, audio-only and display-only modes | IOS-03/04/07, PRODUCT.md §8 |

### Google DeepMind — Best Use of Gemini API

| Question in the brief | What we show |
|---|---|
| What problem? | PRODUCT.md §2 |
| How is Gemini integrated? | Four distinct uses: video → structured steps with timestamps; reference-vs-live image comparison; fast mistake watcher; Live voice with function calling grounded in the chef's transcript |
| What is innovative or technically impressive? | Grounding: every verdict is tied to a chef reference frame and written criteria; the **ablation** in §4 shows what fails without them |
| Why does Gemini matter? | Without multimodal video understanding there is no automatic step extraction; without multi-image reasoning there is no reference comparison |

## 2. Evidence ledger

| # | Claim | Evidence needed | Honest boundary | Owner | Status |
|---|---|---|---|---|---|
| E1 | Hands-free during the core task | A recording of a full run with no phone touch after "start" | Setup and recovery may need the phone | ios | NOT MEASURED |
| E2 | Verdicts are grounded in the chef's reference | Monitor shows reference frame + criteria used for each verdict | Advice not in the recording is model inference | ai, web | NOT MEASURED |
| E3 | Detects the defined mistake | Held-out correct / incorrect frames, §3 | One recipe, a few steps, our own kitchen | ai | NOT MEASURED |
| E4 | Does not approve wrong work | False-approval count on the held-out set | Small sample | ai | NOT MEASURED |
| E5 | Responds promptly | End-to-end latency from the deployed backend, p50 and max | Venue network varies | backend, ai | NOT MEASURED |
| E6 | Handles uncertainty | `unsure` on obscured / out-of-frame / unsupported cases | — | ai | NOT MEASURED |
| E7 | Watcher is not annoying | False alerts per minute on correct footage, after debounce | Short clips | ai | NOT MEASURED |
| E8 | Answers come from the chef's method | Q&A set: in-lesson questions answered with the chef's content; out-of-lesson questions declined or flagged | Small set, judged by us | ai | NOT MEASURED |
| E9 | A novice can use it | 2–3 observed sessions with people outside the team | Not a study | web | NOT MEASURED |
| E10 | Works on the glasses | The G3 run on the device, recorded | Borrowed device, one firmware | ios | NOT MEASURED |

## 3. Visual evaluation set

Built from the team's own footage of the seeded recipe. Scope: the **checkable demo steps** only (at minimum "Spread rice"; add "Add fillings" and "Roll" if time allows).

**Case types per step** (aim for the mix, not the count):

| Type | Label | Examples |
|---|---|---|
| Correct | `pass` | Right amount of rice, different hands, slightly different angle, a correct variation the chef would accept |
| Known mistake | `fix` + `mistake_id` | Rice too thick; rice covering the top margin |
| Unjudgeable | `unsure` | Hands covering the mat, blur, mat half out of frame, too dark |
| Off-task | `unsure` or watcher `ok` | Looking away, empty board, wrong step in view |

**Split.** `dev` frames are used while writing prompts. `heldout` frames are captured in a separate take (different person or session if possible) and are **not looked at** until the prompt is frozen. The split is a column in `ai/eval/cases.csv`.

**Size.** TARGET: about 20 dev + 20 held-out cases for the main step; fewer is acceptable if labelled carefully. Report the real number.

**Labels** are assigned by a human looking at the frame and the chef's criteria, before running the model, and recorded with the labeller's initials.

## 4. Metrics, targets, results

| Metric | Definition | TARGET (proposed) | Result | Date / conditions |
|---|---|---|---|---|
| False approvals (`/check`) | Label `fix`, model says `pass` | 0 on held-out | — | — |
| False rejections (`/check`) | Label `pass`, model says `fix` | ≤ 2 in 20 | — | — |
| Appropriate `unsure` | Label `unsure`, model says `unsure` | ≥ 80% | — | — |
| Wrong `unsure` | Label `pass`/`fix`, model says `unsure` | ≤ 3 in 20 | — | — |
| `/check` latency | Server `latency_ms` from the deployed backend, p50 / max | p50 ≤ 2000 ms | — | — |
| `/watch` latency | Same, p50 / max | p50 ≤ 1500 ms | — | — |
| Watcher detection delay | Mistake visible → alert shown, on clips | ≤ 8 s | — | — |
| Watcher false alerts | Alerts per minute on correct footage, after debounce | ≤ 1 in 5 min | — | — |
| Fix success | After a `fix`, the wearer's next check passes | Observed in each demo rehearsal | — | — |
| Q&A grounding | In-lesson questions answered with chef content / out-of-lesson handled honestly | ≥ 8 of 10 / all | — | — |

**Ablation for the Gemini judges** (same held-out set, three configurations):

| Configuration | False approvals | False rejections | `unsure` | Note |
|---|---|---|---|---|
| A. Full: reference image + criteria + mistakes | — | — | — | What we ship |
| B. No reference image (criteria text only) | — | — | — | Shows what the chef's frame adds |
| C. Generic prompt ("is this sushi step done correctly?") | — | — | — | Shows what grounding adds |

If B or C performs as well as A, say so and simplify the product. Do not hide it.

**Reporting rules.** Report counts ("17 of 20"), never a bare percentage. State the recipe, the number of steps covered, the set size, and that it was the team's own footage. Never report an aggregate that hides a false approval. Do not write a number into the deck before it appears in this table.

## 5. Observed user sessions

Template for each session, kept in `web/pitch/user-notes.md`:

```
Date/time · Who (role, cooking experience; no names without permission) · Device used
Task given · Completed unaided? · Where they hesitated · What they said, verbatim
Did the fix instruction make sense first time? · Would they use it again, and for what?
```

## 6. Recovery tests

Trigger each one deliberately before G4 and record what happened in `ios/STATUS.md` (device) or `backend/STATUS.md` (server). Expected behaviour is defined in [ARCHITECTURE.md §6](ARCHITECTURE.md#6-failure-behaviour).

- [ ] Deny camera permission, then grant it
- [ ] Glasses out of range / hinges closed mid-step, then back
- [ ] Airplane mode for 20 s during a step, then back
- [ ] Backend stopped during a check
- [ ] Forced model timeout (`CHECK_BUDGET_S=0.01`)
- [ ] Forced quota error (fake mode switch or a deliberately throttled key)
- [ ] Pinch "check" five times fast
- [ ] Change step while a check is pending
- [ ] Cover the camera with a hand and check → `unsure`
- [ ] Kill and restart the app mid-session
- [ ] Live session dropped (toggle Wi-Fi) while asking a question
- [ ] Display unavailable → audio-only mode

## 7. Reproducing

```
cd ai
python -m ghostchef_ai.eval --split heldout --config full      # writes ai/eval/results/<timestamp>-full.json
python -m ghostchef_ai.eval --split heldout --config no-ref
python -m ghostchef_ai.eval --split heldout --config generic
```

These commands are specified in AI-07 and do not exist until that batch is done.
