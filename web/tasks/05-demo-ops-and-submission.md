# WEB-05 — Demo operations and submission

| | |
|---|---|
| **Track** | `web/` |
| **Gate** | **Task 1 is due tonight (Fri 13 Nov, 23:55).** The rest runs through G4 and ends at G5. |
| **Depends on** | Nothing for tasks 1–3. A working loop for rehearsals. |
| **Unblocks** | Being allowed to present at all |
| **Size** | Small in code, large in consequences |
| **Model** | Sonnet 5.5 is enough for drafting descriptions and checklists |
| **Needs a human for** | Everything that submits, buys, asks, or records |

## Goal

The entry is submitted correctly and on time to both challenges, the demo can be set up and reset by anyone on the team, there is a labelled backup if the live run fails, and nothing we say or publish breaks a rule we did not read.

## Read first

- [../../docs/DEMO-AND-SUBMISSION.md](../../docs/DEMO-AND-SUBMISSION.md) — this batch executes it
- [../../docs/EVENT-CONTEXT.md](../../docs/EVENT-CONTEXT.md) — schedule, the two time conflicts, rules still to confirm
- [../../docs/DECISIONS-AND-RISKS.md](../../docs/DECISIONS-AND-RISKS.md) — open questions Q-07 to Q-12
- `web/STATUS.md` — the tables you keep current

## Tasks

### WEB-05.1 Preliminary submission — **tonight** *(human)*

- Open the event platform. Find out what the preliminary submission asks for.
- Submit by **23:55** (the platform's time; the homepage says 23:59 — use the earlier).
- Likely content: team, project name, challenges, a short description. Use:
  - Challenges: **Meta — AI Glasses for Everyone, Everyday** (main) and **Google DeepMind — Best Use of Gemini API** (technology). Not Arduino.
  - Description: the one-sentence product description from [PRODUCT §1](../../docs/PRODUCT.md#1-one-sentence).
- If the form wants something we do not have (a video, a public demo link), write what exists truthfully; do not invent.

**Acceptance:** `STATUS.md` → Submission, "Preliminary" row: DONE with the time, or the reason it could not be done and what an organizer said.

### WEB-05.2 Get the rules answered *(human)*

Ask organizers (info desk, the event's chat) and read the authenticated participant pages. Record answers and where they came from in `STATUS.md` → "Open questions":

- Final submission fields; whether a video is required, its length limit, where it is hosted.
- Pitch length and format for partner judging, peer review, and the final.
- Repository: must it be public; rules on code or assets created before the event; whether commits after the deadline are allowed; whether the MIT licence is mandatory.
- Food and knives at the stand and on stage.

Tell the team anything that changes the plan at the next sync, and correct [EVENT-CONTEXT](../../docs/EVENT-CONTEXT.md) / [DEMO-AND-SUBMISSION](../../docs/DEMO-AND-SUBMISSION.md) through a `[docs]` commit.

**Acceptance:** no dashes left in the questions table, or each remaining one says who was asked and when.

### WEB-05.3 Kit *(human)*

Buy and prepare the kit in DEMO-AND-SUBMISSION §4. Sushi rice needs cooking, seasoning, and cooling: plan it for Saturday morning. Coordinate with the AI owner — their filming (AI-03) needs the same ingredients first. Keep a second, untouched set of nori and rice for Sunday.

**Acceptance:** `STATUS.md` → Demo kit table filled; rice exists.

### WEB-05.4 Run sheet

**Do** — `pitch/run-sheet.md`, one printed page the operator follows:
1. The thirty-minutes-before checklist (from DEMO-AND-SUBMISSION §4) with the real URLs, device names, and settings values filled in.
2. Roles: presenter, wearer (or how to brief a volunteer in two sentences), operator.
3. The beats table (DEMO-AND-SUBMISSION §2) with **the exact question** for the voice beat and the exact scripted mistake.
4. The reset procedure, numbered.
5. The failure table (DEMO-AND-SUBMISSION §5), with the emergency backend URL and the hotspot name.
6. Who to call for each subsystem.

Update it whenever a rehearsal shows a step is wrong.

**Acceptance:** a teammate who has not operated the demo sets it up from the sheet alone.

### WEB-05.5 Rehearsals and the backup recording *(human)*

- Rehearse at the real table under the real light. Log every run in `STATUS.md` → Rehearsals: operator, wearer, device, clean or not, what went wrong. Report failures to the owning track immediately.
- Gate G4 needs **three consecutive clean runs** operated by someone who did not build the app.
- Record one clean run as the backup: a second phone on a tripod framing hands and table, with the monitor in shot or recorded separately. Hands only; consent from the wearer; no bystanders; no audio of other people's conversations if avoidable. Store it outside the repository; note its location and label ("recorded Sat 14 Nov, 21:40, live run on <device>").
- Load it into the monitor's Backup mode and check the REPLAY badge shows.

**Acceptance:** rehearsal log shows the three clean runs; the backup exists and plays in the monitor.

### WEB-05.6 Repository readiness

**Do** — with the other owners' agreement, in `[docs]` commits that touch nothing else:
- The root `README.md` reflects the final state: what works, how to run each part, what is planned (ask each owner for their two lines).
- A `LICENSE` file at the repository root, MIT, with the team members' names as copyright holders — **after** WEB-05.2 confirmed the licence requirement. Third-party licences and footage permissions are separate matters; the chef footage is not in the repository.
- Check nothing private is in the history: `git log --all -p | grep -n -i -E "service_role|api[_-]?key\s*=|AIza|secret"` and look at any hit. Check no faces or bystanders are in committed images (`ai/eval/frames/`, `web/pitch/`).
- Every `STATUS.md` is current; EVALUATION §4 has the measured results.

**Acceptance:** a person outside the team can read the README and understand what the project is, what is real, and how to run it. The secret scan is clean.

### WEB-05.7 Final submission *(human)* — internal target Sun 09:00, deadline 10:00

Work through [DEMO-AND-SUBMISSION §6](../../docs/DEMO-AND-SUBMISSION.md#6-submission-checklist):
- Both challenges selected. Title and description from `pitch/one-liners.md`.
- Links: repository, deck PDF, video if required. **Open each in a private browser window** on a device that is not logged in.
- The description states what was built this weekend, what runs live, what is planned.
- Submit. Screenshot the confirmation into the team chat. Fill `STATUS.md` → Submission.
- After submitting: no pushes to `main` unless the rules (WEB-05.2) allow them.

**Acceptance:** confirmation saved; `STATUS.md` shows DONE with the time.

### WEB-05.8 Judging logistics *(human)*

Find out when and where partner judging and peer review happen and who must be at the table. Decide who presents to Meta, who to Google, and who stays to demo for peer reviewers. Charge everything. Bring the printed run sheet.

**Acceptance:** times, places, and names written at the top of `pitch/run-sheet.md`.

## Verification

The acceptance criteria are the verification: each is a recorded fact in `web/STATUS.md`.

## Out of scope

Building features. Changing the demo script on Sunday morning.

## When done

Update `STATUS.md`, commit `[web] WEB-05 demo ops and submission`, push (if still allowed).
