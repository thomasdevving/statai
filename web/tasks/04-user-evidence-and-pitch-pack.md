# WEB-04 — User evidence and the pitch pack

| | |
|---|---|
| **Track** | `web/` |
| **Gate** | Draft for G3, final for G4 |
| **Depends on** | A loop people can try (simulator or app). Final numbers from AI-07; final device facts from IOS-06 / IOS-07. |
| **Unblocks** | Partner judging, peer review, the final pitch |
| **Size** | Medium, mostly human work |
| **Model** | Opus 5.5 for drafting the deck narrative and Q&A; Sonnet 5.5 is enough for formatting |
| **Needs a human for** | Talking to people, building slides in a slide tool, deciding the story |

## Goal

A pitch that a stranger can retell after one minute, where every claim points at something measured or observed this weekend, and where the limits are stated before a judge has to ask.

## Read first

- [../../docs/PRODUCT.md](../../docs/PRODUCT.md) — all of it; §10 (allowed claims) and §11 (the four sentences) especially
- [../../docs/EVALUATION.md](../../docs/EVALUATION.md) §1 (criteria → evidence), §2 (ledger), §5 (session notes template)
- [../../docs/DEMO-AND-SUBMISSION.md](../../docs/DEMO-AND-SUBMISSION.md) §1, §2, §7, §8
- [../../docs/EVENT-CONTEXT.md](../../docs/EVENT-CONTEXT.md) §2–§3
- `ai/STATUS.md`, `ios/STATUS.md`, `backend/STATUS.md` — the only sources for numbers and device claims

## Tasks

### WEB-04.1 One-liners

**Do** — `pitch/one-liners.md`:
- The one-sentence description (start from PRODUCT §1; make it sayable in one breath).
- A 60-second table explanation, written out, timed by reading aloud.
- The four sentences from PRODUCT §11, adjusted to what was actually built.
- The project title and a 280-character description for the submission form.

**Acceptance:** a teammate from another track reads the 60-second version aloud in under 65 seconds and says it matches the build.

### WEB-04.2 Watch people use it *(human)*

Two or three people **outside the team** (other hackers, volunteers, mentors), each for five minutes, on the best thing that works at the time (the app on the glasses, the app on the phone, or the simulator — write down which).

- Give them the task ("spread the rice for this roll; the glasses will help") and then **say nothing**.
- Fill the template from EVALUATION §5 for each, in `pitch/user-notes.md`. Roles only ("first-year CS student, never made sushi"); no names, photos, or contact details without permission.
- Afterwards ask: what was confusing, would you use this again and for what, what would make you trust it.

**Acceptance:** at least two sessions recorded with date, device used, whether they completed unaided, and one verbatim quote each. Add the rows to `STATUS.md` → User evidence. If nobody could be recruited, the deck says "not yet tested with users".

### WEB-04.3 A pilot conversation *(human)*

Find one person who teaches or has taught cooking (a team member's contact, a venue caterer, a mentor) and ask three questions: how do you notice a student's mistake today; how many students can you watch at once; would you record a technique once if students could follow it this way, and what would stop you.

Write the answers in `pitch/user-notes.md` under "Pilot conversation".

**Acceptance:** either notes from a real conversation, or the sentence "No instructor conversation happened" in `STATUS.md`. The deck's pilot slide is worded accordingly: "proposed pilot" unless someone actually agreed to something.

### WEB-04.4 Architecture diagram

**Do** — `pitch/architecture.svg` (hand-written SVG or exported from a diagram tool): glasses → iPhone app → backend → Gemini, with the four Gemini jobs labelled (video → steps; reference vs. live comparison; fast mistake watcher; Live voice with function calls), plus Supabase and the chef studio. One slide, readable from the back of a room, no more than ~12 boxes. Base it on [ARCHITECTURE §1–§2](../../docs/ARCHITECTURE.md#1-components-and-folders), and remove anything that was cut.

**Acceptance:** opens in a browser; a teammate confirms it matches what runs.

### WEB-04.5 Evidence page

**Do** — `pitch/evidence.md`, the single page the deck's evidence slide is built from:
- The metrics and ablation tables **copied from `ai/STATUS.md`** with set sizes, model IDs, and date.
- Measured latency (deployed) from `backend/STATUS.md` or the monitor.
- What ran on the glasses, **copied from `ios/STATUS.md`** (model, firmware, which parts on-device).
- User session counts from WEB-04.2.
- A "Limits" list: one recipe; N steps evaluated; our own footage; small sample; borrowed device; anything that failed.
- Two or three example frames from the AI owner (caught mistake, correct pass, `unsure`), with no faces.

Then fill `STATUS.md` → "Claims audit": every number and capability sentence in the deck, its source file, and OK or not.

**Acceptance:** no claim in the deck lacks a row; rows without a source are removed from the deck, not from the audit.

### WEB-04.6 The deck

**Do**
- `pitch/deck-outline.md`: slide-by-slide text and speaker notes following DEMO-AND-SUBMISSION §7 (the moment → one sentence + live demo → why glasses → how it works → evidence → trust → who and next). Adjust the slide count to the real time slot once known.
- Build the slides in the team's tool of choice *(human)*. Export `pitch/deck.pdf` and commit it if it is under ~10 MB.
- The demo is the centre: slides are what you show when the demo is not running.
- A "What we built this weekend" line and a "What's next" slide that is clearly labelled as future.

**Acceptance:** PDF exists; a run-through with the demo fits the slot; the claims audit is all OK.

### WEB-04.7 Questions and answers

**Do** — `pitch/qa.md`: a short, honest answer (2–3 sentences, with the number or the file it comes from) to each question in DEMO-AND-SUBMISSION §8, plus: "What does Gemini do that a simpler model could not?", "What happens to the footage?", "Is this just for sushi?", "How is this different from existing cooking assistants?" (acknowledge related research such as AROMA; state our demonstrated distinction).

**Acceptance:** each team member has read it; two rehearsed Q&A rounds done with a teammate asking at random.

## Verification

Read the 60-second pitch aloud with a timer. Open `deck.pdf` and `architecture.svg`. Check every row of the claims audit against its source file.

## Out of scope

Market sizing without research. Logos, branding work, a landing page.

## When done

Update `STATUS.md`, commit `[web] WEB-04 pitch pack and user evidence`, push.
