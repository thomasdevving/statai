# `web/` status

> Updated by the track owner after every batch. Also the live state of the demo and submission checklists from docs/DEMO-AND-SUBMISSION.md. Write only what was done and observed.

## Batches

| # | Batch | Status | Date / commit | Notes |
|---|---|---|---|---|
| 01 | Foundation and simulator | PARTIAL | 2026-11-14 | 01.1–01.5 pass against BE-01 in **fake mode** (memory store, `ai_mode: fake`). 01.6 first real loop not run: needs the backend on real Gemini (BE-03.1). Webcam path built but not yet tried by a person with a real camera. Details below. |
| 02 | Review page | NOT STARTED | | |
| 03 | Demo monitor | NOT STARTED | | |
| 04 | User evidence and pitch pack | NOT STARTED | | |
| 05 | Demo ops and submission | NOT STARTED | | |

Status words: `DONE`, `DONE (fake)`, `PARTIAL`, `BLOCKED`, `NOT STARTED` (defined in docs/PLAN.md §8).

## WEB-01 verification (2026-11-14, fake mode)

Run against `backend/` at commit 14a8623 on `localhost:8000`, `STORAGE=memory`, `GHOSTCHEF_AI_FAKE=1`, in the Claude desktop app's built-in Chromium. Served both from the backend (`/app/`) and standalone (`python -m http.server 5173`, cross-origin). All results below are **fake-mode**; no Gemini call was made.

| Criterion | Result |
|---|---|
| `node --test "web/tests/*.test.mjs"` | 11/11 pass (Node 24) |
| Landing page shows `ai_mode` and `storage` | Pass: strip shows `ai_mode fake`, `storage memory`, contract 2.0, red "Fake AI" |
| Wrong or missing key | Pass: strip shows "Key rejected" + "Open settings"; recipe list explains the key problem |
| API down | Pass: strip shows "API unreachable"; a check shows "No connection" |
| `?gallery=1` renders every lens kind | Pass: 12 cards (step ×4 watch states, checking, pass, fix, proactive fix, unsure, notice, done, recipePick) |
| "Spread rice": 1st check fix, 2nd pass + auto-advance | Pass: fix "Too much rice" (751 ms server), then pass, advanced to step 4 after 2 s |
| Nearly black tiny JPEG gives "Can't tell" | Pass (782-byte frame), returns to the step after 4 s |
| Step change during a slow check discards the result | Pass: `/check` delayed 3 s in the page, moved to step 5 mid-flight; the step-4 `fix` arrived and was ignored |
| Watcher warns after the fake's 4th and 5th calls, not before | Pass: calls 1–3 ok, 4 warn (no alert), 5 warn → amber "Spotted" card, `warning_shown` posted |
| No overlapping watch requests | Pass: 0 overlaps; gaps between end and next start 2.6–3.7 s at the 2.5 s setting |
| Dismiss mutes the id for 20 s | Pass: `warning_dismissed` posted; later `rice_too_thick` warns inside 20 s raised nothing |
| Ignored warning dismisses itself after 12 s | Pass: 12.0 s, posted as `warning_dismissed` |
| Watch errors are silent; 3 in a row pause 15 s | Pass: dot "offline", line "Watcher paused for 15 s after three errors" |
| Done card from `GET /sessions/{id}` summary | Pass |
| Phone width (375 px) | No horizontal scroll |

Not verified: webcam capture with a real camera and a person; speech output by ear; Safari; the deployed HTTPS URL.

## Submission

| Item | State | When / by whom | Link or note |
|---|---|---|---|
| Preliminary submission (Fri night) | NOT DONE | | |
| Challenges selected on the platform: Meta main + Gemini technology | NOT DONE | | |
| Final submission | NOT DONE | | |
| Confirmation saved | NOT DONE | | |

## Open questions for organizers and partners

| # | Question | Answer | Source / when |
|---|---|---|---|
| Q-07 | What does the preliminary submission require, and by exactly when (23:55 or 23:59)? | — | |
| Q-08a | Final submission fields? Is a video required; maximum length? | — | |
| Q-08b | Pitch length and format for partner judging, peer review, and the final? | — | |
| Q-08c | Must the repository be public? Rules on code written before the event? Edits after the deadline? | — | |
| Q-08d | Is the MIT licence required for the repository? | — | |
| Q-09 | Are cooked food and knives allowed at the stand and on stage? | — | |
| Q-10 | A cooking instructor or school we can talk to before Sunday? | — | |
| Q-12 | Final product name (repository is `statai`, concept is "Ghost Chef") | — | |

## Demo kit

| Item | Have it? | Who brings it |
|---|---|---|
| Cooked sushi rice (enough for ~15 attempts) | — | |
| Nori (20+ sheets) | — | |
| Bamboo mats ×2, cling film | — | |
| Filling (cucumber sticks), bowl of water | — | |
| Dark matte surface, small light | — | |
| Wet wipes, paper towels, gloves | — | |
| Tripod / second phone for recording | — | |
| Power bank, cables, hotspot phone | — | |
| External screen or laptop for the monitor | — | |

## User evidence

| Date | Who (role only) | What they used | Completed unaided? | Notes file |
|---|---|---|---|---|
| — | — | — | — | — |

Pilot conversation: none yet.

## Rehearsals

| Date / time | Operator | Wearer | Device | Clean? | What went wrong |
|---|---|---|---|---|---|
| — | — | — | — | — | — |

Backup recording: none yet.

## Claims audit (before the deck is final)

| Claim in the deck | Source file and value | OK? |
|---|---|---|
| — | — | — |

## Needs from other tracks

- —
