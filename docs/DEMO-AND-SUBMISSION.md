# Ghost Chef — demo and submission

> The demo script, what the audience sees, what to do when something breaks, the deck outline, and the submission checklist.
> Owned by the `web/` track ([web/tasks/04](../web/tasks/04-user-evidence-and-pitch-pack.md), [web/tasks/05](../web/tasks/05-demo-ops-and-submission.md)). Live state of the checklists is kept in `web/STATUS.md`.
> Pitch length, review logistics, and required submission fields are **not yet known**; confirm them on site and adjust.

## 1. Who sees it and what they need

| Audience | When | What must be obvious in under a minute |
|---|---|---|
| Meta partner judges | Partner judging | A real pair of glasses doing something a phone cannot |
| Gemini partner judges | Partner judging | Gemini doing four distinct jobs, grounded, with evidence |
| Peer reviewers | Face-to-face review at the table | What it does and that it works, visible to someone not wearing the glasses |
| Grand jury (only if we reach the final five) | Stage pitch | The insight, the working proof, honest limits, what happens after Sunday |

Winning a partner challenge does not by itself put a team in the overall final.

## 2. The demo, beat by beat

One volunteer (ideally not a team member) wears the glasses. One operator runs the laptop with the monitor. One presenter talks.

| # | Beat | Wearer does | Lens / audio | Monitor shows | Presenter says |
|---|---|---|---|---|---|
| 1 | Setup (10 s) | Puts on glasses, looks at the mat | Step card "Spread rice" with the chef's reference | Chef reference + live wearer frame, "LIVE" badge | "A chef recorded this once, wearing the same glasses." |
| 2 | Mistake (15 s) | Spreads far too much rice, to the edges | — | Live frame | "Our volunteer has never rolled sushi." |
| 3 | Proactive catch (10 s) | Keeps working | Amber "⚠ Too much rice" + reference + one spoken sentence | Warning event, mistake id, confidence, latency | "Nobody asked. The glasses compared this view with the chef's and spoke first." |
| 4 | Fix (15 s) | Removes rice, clears the top margin | Warning clears | Live frame | "One instruction, in the chef's words." |
| 5 | Check (10 s) | Pinches / says "check" | "Checking…" → green ✓ "Looks right" + chime | Pass event with latency | "Now they ask, and it passes." |
| 6 | Question (20 s) | Asks aloud, e.g. "Why wet my hands?" | Mic icon, caption, spoken answer | Question event | "The answer comes from the chef's own narration." |
| 7 | Honest limit (10 s) | Covers the mat with a hand and checks | "Can't tell — look at the mat" | `unsure` event | "When it can't see, it says so instead of guessing." |
| 8 | Close (10 s) | — | — | Evidence slide | Measured numbers, proposed pilot, what's next |

Total about 100 seconds. Beats 6 and 7 are the first to drop for a shorter slot. Beat 3 falls back to beat 5 alone if the watcher is cut.

**Table version (peer review, ~60 s):** beats 1, 2, 5 (check → fix), 4, 5 (pass). Let the reviewer wear the glasses if hygiene and time allow; otherwise they watch the monitor.

**The question in beat 6 must be one the chef actually answers in the recording.** Pick it from the transcript and rehearse it.

## 3. What the audience sees

The **monitor** (`/app/monitor/`) on a laptop or external screen:

- left: the chef's reference frame for the current step; right: the wearer's latest frame;
- the current lens card rendered exactly as the wearer sees it;
- the event timeline (warning, check, pass, question) with latency;
- a badge that says **LIVE** when data is under 5 seconds old and **REPLAY** when showing a recording.

Rules: anything recorded is labelled as recorded. Slides showing future features are labelled "next". The backup video is never presented as a live run.

## 4. Kit and pre-demo checklist

**Kit** *(procurement is an open task — nothing here is bought yet)*: sushi rice (cooked, cooled, enough for ~15 attempts), nori sheets (20+), bamboo mat ×2, cling film for the mat, fillings that survive a day (cucumber sticks), bowl of water, knife and board (check venue rules for knives; slicing can be skipped), wet wipes, paper towels, gloves for volunteers, a dark non-reflective surface, a small light if the stand is dim, phone tripod for the backup recording, power bank, the Mac's cable for re-installing the app.

**Thirty minutes before:**

- [ ] Glasses charged, paired, Developer Mode on, app registered. Phone on charger, Do Not Disturb, auto-lock off.
- [ ] `GET /health` on the production URL shows `ai_mode: gemini`, `storage: supabase`.
- [ ] App settings point at the production URL. Watch threshold is the tuned value from `ai/STATUS.md`.
- [ ] Seeded recipe is `published` and its reference images load.
- [ ] One full dry run on the actual table, under the actual light.
- [ ] Monitor open and attached to the session. Backup video open in another tab.
- [ ] Hotspot ready. Emergency laptop backend started (see §5).
- [ ] Fresh nori and rice portions laid out for three runs.

**Reset between runs (target under 30 s):** new nori on the mat → app "Restart session" → monitor re-attaches automatically → wipe hands.

## 5. When something breaks

Decide in advance; do not debug in front of judges.

| Symptom | Do this | Say this |
|---|---|---|
| Venue Wi-Fi unusable | Phone and laptop onto the hotspot | Nothing |
| Production backend down | Switch the app's base URL to the emergency laptop | Nothing |
| Watcher silent after 15 s | Wearer says "check" (beat 5 does the catch) | "Let's ask it." |
| Watcher false alarm | Dismiss; carry on | "It's cautious. Two hits in a row are needed, and you just saw the second." |
| Voice not responding (noise) | Skip beat 6, or use push-to-talk | "It's loud here; the answer is also on the lens." |
| Lens display fails | Audio-only mode; point at the monitor's lens card | "Audio-first works on glasses without a display too." |
| Glasses will not connect | Phone camera held at chest height, lens preview on the phone | "This is our development fallback on the phone camera", **explicitly** |
| Everything fails | Play the backup recording, labelled | "This is a recording from this morning." |

## 6. Submission checklist

**Open questions to resolve on site** (owner: `web/` track): exact form fields; whether a video is required and its maximum length; pitch duration; repository visibility requirement; rules on code written before the event; whether edits are allowed after the deadline; the preliminary-submission content and its real deadline (platform says Fri 23:55, homepage says 23:59).

- [ ] **Preliminary submission (Friday night):** team, project name, selected challenges (Meta main + Gemini technology), short description. Use PRODUCT.md §1.
- [ ] Both challenges selected on the platform: **Meta — AI Glasses for Everyone, Everyday** and **Google DeepMind — Best Use of Gemini API**. Arduino not selected.
- [ ] Repository: public, `main` up to date, README explains how to run, no secrets in history (`git log -p | grep -i -E "api_key|service_role"` finds nothing real).
- [ ] `LICENSE` file added. The event FAQ states MIT-licensed submissions; the full terms page could not be read during research, so confirm before adding, and keep third-party licenses and footage permissions separate.
- [ ] Deck exported to PDF and linked.
- [ ] Demo video (if required or allowed): recorded with consent of everyone visible, no bystanders, labelled if any part is not live.
- [ ] Description states what was built this weekend, what is live, and what is planned.
- [ ] Every link opened in a private window by someone who did not create it.
- [ ] Submitted before the internal target; confirmation screenshot saved in the team chat.

## 7. Deck outline

Keep it to the slot length once known. One idea per slide.

1. **The moment.** Hands covered in rice, phone propped on a jar, no idea if it's right.
2. **Ghost Chef in one sentence** + the live demo.
3. **Why glasses.** Same viewpoint as the chef; hands stay on the food; the system can speak first.
4. **How it works.** One diagram: glasses → phone → backend → Gemini; the four Gemini jobs.
5. **Evidence.** Measured counts and latency from [EVALUATION.md](EVALUATION.md); the ablation; what it cannot do.
6. **Trust.** Consent and delete for the chef; watching indicator; "can't tell"; audio-only and display-only modes.
7. **Who and next.** The audience, the proposed pilot and how its success would be measured, what's next (personalization, other hands-on skills).

## 8. Questions to rehearse

Why glasses and not a phone on a stand? · Why Gemini; what would break without it? · How is this more than a generic visual assistant? · How do you know the verdict is right? · What does it do when it is wrong? · What did you build this weekend, and what existed before? · What happens without internet? · Who gave consent to be recorded, and where is the footage? · Who would pilot it, and how would you know it worked? · Does it work for anything other than sushi?

Answers are drafted in `web/pitch/qa.md` (WEB-04) from the facts in this repository, with measured numbers only.
