# `ios/` status

> Updated by the track owner after every batch. The pitch and the docs take device claims **only** from this file. Write only what was run and observed.

## Batches

| # | Batch | Status | Date / commit | Notes |
|---|---|---|---|---|
| 01 | Project foundation | NOT STARTED | | |
| 02 | DAT glasses spike | NOT STARTED | | |
| 03 | Cook-along core | NOT STARTED | | |
| 04 | Proactive watcher | NOT STARTED | | |
| 05 | Gemini Live voice | NOT STARTED | | |
| 06 | Glasses integration | NOT STARTED | | |
| 07 | Resilience and demo mode | NOT STARTED | | |

Status words: `DONE`, `DONE (fake)`, `PARTIAL`, `BLOCKED`, `NOT STARTED` (defined in docs/PLAN.md §8).

## Hardware access (answers from the Meta booth)

| Question | Answer | Asked when / who answered |
|---|---|---|
| Which glasses can we use (Display / Gen 2)? | — | |
| For how long, and can we hold a pair for the demo slot? | — | |
| Who supports the iOS DAT SDK on site? | — | |
| Is a Wearables Developer Center project provided, or do we register our own? | — | |
| Do Neural Band gestures reach a DAT app? | — | |

## Environment actually used

| Item | Value |
|---|---|
| Mac / Xcode version | — |
| iPhone model / iOS version | — |
| Glasses model / firmware | — |
| DAT SDK version pinned | — |
| Meta AI app version; Developer Mode on? | — |
| Backend URL the app points at | — |

## Device facts (IOS-02)

`PASS`, `FAIL`, or `NOT TESTED`, each with what was observed. Tested on MockDeviceKit and tested on real glasses are different columns.

| # | Proof | MockDeviceKit | Real glasses | Observed detail |
|---|---|---|---|---|
| a | App registers with the Meta AI app and sees the device | NOT TESTED | NOT TESTED | |
| b | Camera permission granted; one frame arrives as JPEG | NOT TESTED | NOT TESTED | |
| c | Display shows an image and two lines of text in one view | NOT TESTED | NOT TESTED | |
| d | Camera stream and display run at the same time | NOT TESTED | NOT TESTED | |
| e | An input from the wearer reaches the app (which kinds?) | NOT TESTED | NOT TESTED | |
| f | Phone audio in/out routes through the glasses while streaming video | NOT TESTED | NOT TESTED | |
| g | Measured: stream resolution, frames per second, time from request to JPEG | NOT TESTED | NOT TESTED | |

Looking down at a board: is the work in frame? —

## Decisions taken from the spike

| Topic | Decision | Reason |
|---|---|---|
| Lens layout (image + text, or fallback) | — | |
| Input mapping for check / next / back / show me | — | |
| Audio route for results and voice | — | |
| Frame capture method and size for `/check` and `/watch` | — | |

## Recovery tests (IOS-07)

| Test | Expected (ARCHITECTURE §6) | Observed | Date |
|---|---|---|---|
| Camera permission denied, then granted | Explanation on phone; recovers | — | — |
| Glasses disconnected mid-step, then back | Spoken notice; resumes on same step | — | — |
| Airplane mode 20 s during a step | Grey dot; cards still work; recovers | — | — |
| Backend stopped during a check | "Can't check right now" | — | — |
| Check pressed five times fast | One verdict shown | — | — |
| Step changed while a check is pending | Pending result discarded | — | — |
| Camera covered, then check | "Can't tell" | — | — |
| App killed and restarted mid-session | Clean restart | — | — |
| Live dropped while asking | Mic unavailable; rest works; reconnects | — | — |
| Display unavailable | Audio-only mode | — | — |

## End-to-end runs on the glasses

| Date | Glasses | What ran (check / watcher / voice / display) | Result | Recorded? |
|---|---|---|---|---|
| — | — | — | — | — |

## Needs from other tracks

- —
