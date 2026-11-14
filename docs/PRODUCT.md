# Ghost Chef — product brief

> Scope, audience, and what we may claim. The technical concept is [TECH-SPEC.md](TECH-SPEC.md); this file adds the audience, trust, and judging-facing framing the spec does not cover.
>
> Labels: **[TEAM]** stated by the team · **[VERIFIED]** checked against a public source on 2026-11-13 · **[REC]** recommendation · **[OPEN]** not yet known or not yet tested.

## 1. One sentence

A chef records a recipe once through smart glasses; anyone wearing the glasses can then cook it hands-free while Gemini compares what they are doing with the chef's own point-of-view footage, corrects mistakes as they happen, and answers questions in the chef's method. **[TEAM]**

## 2. The problem

Learning a hands-on technique from a video breaks at the exact moment it matters:

- Your hands are wet, sticky, or holding a knife, so you cannot pause, scrub, or search a phone.
- The video cannot see your board. You find out the filling was all in the middle when the sandwich falls apart at the first bite.
- A human instructor fixes this by glancing at your hands and saying one sentence. That attention does not scale beyond a small class.

The ordinary alternatives are a phone propped against a jar (no feedback, needs touching), a recipe app with voice control (no eyes on your work), and a generic visual assistant (not grounded in this chef's method, does not know which step you are on).

## 3. Audience

| Who | Situation | What they get |
|---|---|---|
| **Primary: a home cook learning a specific dish from a specific chef** | Hands busy and messy, following along for the first or second time | Step cards in the lens, a check against the chef's reference when asked, a warning when a known mistake appears, spoken answers |
| **Secondary: the chef or instructor** | Teaches the same technique repeatedly | Records once in the app's Chef mode while cooking normally, pinching to mark each new step; reviews and corrects the extracted steps on a web page |

**[OPEN]** Nobody outside the team has used it yet. Observed sessions with 2–3 novices are a task in [web/tasks/04](../web/tasks/04-user-evidence-and-pitch-pack.md).

## 4. Why glasses, and why the wearer's perspective

- **Same viewpoint on both sides.** The chef's reference is recorded from eye level looking down at the board. The learner's frame comes from the same position. Comparing like with like is what makes "does mine look like the chef's?" answerable. A propped phone sees a different angle from the one the lesson was filmed at.
- **Hands stay on the food.** Input is a pinch, a swipe, or speech. Output is two short lines in the lens plus one spoken sentence.
- **The system can speak first.** Because the camera already sees the work, a mistake can be flagged before the learner knows to ask.

This is not a mirrored phone screen: the phone is in a pocket for the whole cook-along.

## 5. User journeys

**Chef (once per recipe).** Open the app in **Chef mode** → cook the dish wearing the glasses and talk through each step, pinching to mark each new step (the lens shows "● REC") → stop → the app uploads the video → Gemini returns steps with timestamps, success criteria, and common mistakes, using the pinch marks as hints → the chef fixes wording and re-picks any reference frame on the review web page → publish.

**Cook (every time).** Open the app in **Cook mode** → pick the recipe from the library (all its images and clips download before cooking starts) → see step card with the chef's reference still → work → the watcher flags a known mistake, or the cook pinches / says "check" → Pass advances; Fix shows the reference and one instruction → fix it → re-check passes → ask a question out loud at any time → Done summary.

**Demo (the one journey that must work).** A volunteer makes a sandwich, piles the filling in the middle, the glasses catch it and show the chef's reference, they fix it, the check passes, they ask a question and get a spoken answer. **[TEAM]** Full script: [DEMO-AND-SUBMISSION.md](DEMO-AND-SUBMISSION.md).

## 6. Scope

The Must / Nice / Cut lists are in [TECH-SPEC.md § Scope](TECH-SPEC.md#scope) and are unchanged. The order in which things get cut when time runs out is in [PLAN.md § Cut order](PLAN.md#6-cut-order).

**Non-goals for this weekend:** general cooking knowledge beyond the recorded lesson; judging taste, temperature, or doneness that a camera cannot see; AR overlays anchored to the food; accounts and multi-user features; any dish other than the one seeded recipe on stage; Arduino or any extra hardware.

## 7. What "correct" means here

A step is checked only against criteria that are **visible in a single first-person frame**: coverage, placement, margins, alignment, shape (for example "the filling reaches the edges of the bread"). Each step's `success_criteria` and `watch_fors` are written (or edited by the chef) to be that kind of criterion.

- When the criteria are not visible in the frame, the answer is **`unsure`** with an instruction for getting a better view. It is never a guess.
- Advice that comes from the chef's recording is presented as the chef's ("Chef says…"). Anything the model infers beyond the recording is not attributed to the chef.
- The system makes no food-safety claims.

## 8. Trust, consent, accessibility

These map to the Meta rubric's "UX, accessibility, and trust" quarter.

| Topic | What we do | Status |
|---|---|---|
| Chef consent | Chef mode asks for explicit consent before recording starts, and the web dev-fallback upload requires a consent tick (`consent: true` on `POST /recipes`); the lens shows "● REC" for the whole recording; `DELETE /recipes/{id}` removes the video and everything derived from it | Planned (IOS-08, BE-06, WEB-02) |
| Wearer awareness | The lens shows "● watching" whenever frames are being sent; grey when not | Planned (IOS-04) |
| Bystanders | The glasses' own capture LED behaviour is Meta's; our demo frames a work surface, not faces. We do not store watcher frames except those that triggered a warning | Planned (BE-03) |
| Data retention | Wearer frames live in a private bucket and are deleted with the recipe or session; nothing is public; keys never reach the phone | Planned (BE-02) |
| Gemini data handling | **[OPEN]** Depends on the account tier the event credits come with. Record the actual setting in `ai/STATUS.md`; do not state a policy we have not read | Open |
| Audio-first parity | Every lens state has a spoken equivalent, so the experience works on displayless glasses and for people who cannot read the lens | Planned (IOS-07) |
| Display-only parity | Every spoken result is also shown as headline + fix, for noisy rooms and for deaf or hard-of-hearing users | Planned (IOS-03) |
| Uncertainty | `unsure` verdict; watcher only warns after two consecutive confident hits | Planned (AI-04, IOS-04) |
| Permission / connectivity / device-state changes | Defined per failure in [ARCHITECTURE.md § Failure behaviour](ARCHITECTURE.md#6-failure-behaviour) | Planned (IOS-07) |

## 9. Adoption and pilot path

**[OPEN] — hypothesis, not a partnership.** The reachable first pilot is one cooking class with one instructor and shared glasses: the instructor records one technique, each student takes a turn following it. Success would be measured by instructor interventions per student and by whether students complete the step unaided.

To make this credible before the pitch (owner: `web/` track): talk to one real instructor or cooking-school contact, or failing that one experienced cook at the event, and write down what they said. Until that conversation happens, the deck says "proposed pilot", never "pilot partner".

## 10. What we can and cannot claim

| Say | Only if |
|---|---|
| "Works on Meta Ray-Ban Display glasses" | It ran end to end on the actual device and `ios/STATUS.md` records it |
| "Catches the mistake in N seconds" | N is a measured number from `ai/eval/results/` or the monitor's latency panel |
| "Grounded in the chef's method" | The answer cites the chef's reference frame, criteria, or transcript |
| "X of Y test cases correct" | The held-out set was run; say the set size and that it is one recipe |

Never say "first", "only", "works for any recipe", or a percentage accuracy that was not measured. Related prior work exists: AROMA is a research system connecting a wearable camera, recipe video, and cooking assistance for blind and low-vision users ([paper](https://arxiv.org/abs/2507.10963)). Our distinction to demonstrate, not to assert: chef-approved checkpoints with source evidence, and a measured correct-and-recheck loop.

## 11. The four sentences every team member should be able to say

1. **Wearer's perspective:** "The learner's camera sits where the chef's camera sat, so we can compare your board with the chef's board directly, while your hands stay on the food."
2. **Gemini's job:** "Gemini watches the chef's video and turns it into checkable steps, then compares your live view with the chef's reference frame to say pass, fix, or can't tell, and answers spoken questions from the chef's own narration."
3. **What we built beyond an API call:** "A reference-grounded checking loop with a debounced watcher, stale-answer rejection, an explicit uncertainty outcome, and an evaluation set that measures false approvals."
4. **Outcome:** "A beginner makes a real mistake, is told once what to change, fixes it, and gets a pass, without touching a screen."
