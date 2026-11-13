# AI-03 — Chef footage and the labelled evaluation set

| | |
|---|---|
| **Track** | `ai/` (help from the `web/` owner with shopping and filming) |
| **Gate** | G1 — footage must exist before prompts can be trusted |
| **Depends on** | Ingredients and a camera. No code dependency. |
| **Unblocks** | AI-04 (real frames), AI-06 (real video), AI-07 (evaluation), BE-02 (real reference stills in the seed) |
| **Size** | Medium, mostly physical |
| **Model** | Sonnet 5.5 is enough for the two helper scripts. Labelling is done by a person. |
| **Needs a human for** | Almost everything: cooking, filming, labelling |

## Goal

Real first-person footage of the sushi lesson, real reference stills, and a labelled set of correct / mistaken / unjudgeable frames split into `dev` and `heldout`. This is the raw material for the central product question: **can one frame tell "too much rice" from "right"?** (risk R-02).

## Read first

- [../../docs/EVALUATION.md §3](../../docs/EVALUATION.md#3-visual-evaluation-set) — case types, split, labelling rules
- [../../docs/PRODUCT.md §7](../../docs/PRODUCT.md#7-what-correct-means-here) — what "correct" means
- [../../docs/DEMO-AND-SUBMISSION.md §4](../../docs/DEMO-AND-SUBMISSION.md#4-kit-and-pre-demo-checklist) — kit list
- `ai/fixtures/sushi_recipe.json` — the placeholder steps you are about to replace with real ones

## Before filming

- **Kit:** cooked sushi rice (plenty), nori, bamboo mat, a bowl of water, one filling, a dark matte surface. Nothing here has been bought yet; check [DECISIONS-AND-RISKS](../../docs/DECISIONS-AND-RISKS.md) Q-09 about food at the venue.
- **Camera:** the glasses if a pair is available (ask the `ios/` owner; the Meta AI app can record video). Otherwise a phone held at the forehead or on a head/chest strap, **portrait orientation**, looking down at the board. Write down which device was used: frames from a phone are a stand-in, not proof of what the glasses see.
- **Consent:** the person filmed agrees to the footage being processed by Gemini and shown in the demo. Film hands and board only. No faces, no bystanders, no screens with private data.
- **Light:** film at least one take where the demo will actually happen.

## Tasks

### AI-03.1 The chef take *(human)*

One continuous take, 3–6 minutes, of someone who can roll maki competently:

- Say each step out loud as you do it, in full sentences, including the reason ("wet your hands so the rice doesn't stick").
- At the end of each step, **hold still for two seconds looking straight down at the finished state**, hands out of the way. These moments become the reference stills.
- Say explicitly what good looks like and what the common mistake is ("you should still see nori through the rice; most people use far too much").

If the iOS app's **Chef mode** (IOS-08) already records through the glasses, record this take with it and pinch at the start of each step: that is the product's real path, and the step marks reach ingestion. Otherwise use the camera above and record it again in Chef mode later (IOS-08.5). Save as `ai/footage/chef-take-1.mp4` (this folder is gitignored). Upload it to the team's shared drive and write the link and the device in `STATUS.md`.

**Acceptance:** the file plays, narration is audible, every step has a two-second hold.

### AI-03.2 Mistake and variation takes *(human)*

For the main checkable step, **Spread rice**, film short clips (10–30 s each). Two different people's hands if possible.

| Clip set | Count (aim) | Content |
|---|---|---|
| Correct | 4 | Right amount; vary hands, angle, how tidy it is |
| `rice_too_thick` | 4 | Clearly too much; then *slightly* too much (the hard case) |
| `rice_covers_top_edge` | 3 | No bare margin at the far edge |
| Unjudgeable | 4 | Hand covering the mat; mat half out of frame; motion blur; too dark |
| Off-task | 2 | Looking away at the room; empty mat |
| **Fix sequence** | 2 | Too much rice → remove rice → correct. One continuous clip each. These test the watcher's detection delay and the re-check. |

If time allows, repeat a smaller version for **Add fillings** (`too_much_filling`).

Film a **second session** (different person or different time and light) for the held-out set. Keep it in a separate folder from the start: `ai/footage/heldout/`.

**Acceptance:** clips exist for every row; held-out clips are in their own folder.

### AI-03.3 Frame extraction script

**Do** — `ai/scripts/extract_frames.py`:
- Arguments: input video, output directory, `--every` seconds (default 2.5, the watcher interval), `--long-edge` (default 1280), `--prefix`.
- Uses the `ffmpeg` binary through `subprocess` (this is a script, not the package, so ffmpeg is allowed here). Writes JPEG quality ~80, named `<prefix>-<seconds>.jpg`.
- Also supports `--at 74.5` to extract a single frame at a timestamp (used for reference stills).
- Prints a clear error if `ffmpeg` is not on the PATH, with install hints (`winget install ffmpeg`, `brew install ffmpeg`, `apt install ffmpeg`).

**Acceptance:** running it on one clip produces correctly sized frames.

### AI-03.4 Build the labelled set *(human, with the script)*

- Extract frames from every clip into `ai/eval/frames/dev/` and `ai/eval/frames/heldout/`.
- Delete near-duplicates and anything showing a face or a bystander.
- Create `ai/eval/cases.csv` with columns:

  `case_id,file,step_idx,split,label,mistake_id,labeller,source_device,notes`

  - `label` is `pass`, `fix`, or `unsure`. `mistake_id` is filled only for `fix`.
  - `split` is `dev` or `heldout`.
  - Label by looking at the frame and the chef's stated criteria, **before** running any model on it. Put your initials in `labeller`.
- Write `ai/eval/README.md` in five lines: what the set is, how many cases per label and split, which device, who labelled, known weaknesses.
- Total committed frame size should stay under ~30 MB. Raw clips stay out of git.

**Acceptance**
- `cases.csv` parses; every `file` exists; counts per `split` × `label` are printed by a tiny check script or test and recorded in `STATUS.md`.
- At least: dev ≥ 3 `pass`, ≥ 3 `fix`, ≥ 2 `unsure`; held-out the same. More is better; report the real numbers.

### AI-03.5 Real reference stills and fixture v1

**Do**
- From `chef-take-1.mp4`, pick the timestamp of each step's two-second hold. Extract each with `extract_frames.py --at`, portrait, long edge 1280, and save over `ai/fixtures/images/step-<idx>.jpg`.
- Edit `ai/fixtures/sushi_recipe.json` by hand so it matches the real take: real step order and count, real `timestamp_s`, criteria in the chef's own terms, `chef_quote` copied from what was actually said, and a real `transcript` (type it or use any transcription you have; remove the `[PLACEHOLDER NARRATION …]` line only when the whole transcript is real).
- Keep the `rice_too_thick` watch-for id and its three strings unchanged (the demo depends on them), unless the team decides on a different scripted mistake: then update [DEMO-AND-SUBMISSION §2](../../docs/DEMO-AND-SUBMISSION.md#2-the-demo-beat-by-beat) through a `[docs]` commit.
- Re-run the fixture validation test.

**Acceptance**
- Fixture validates. Images are real stills (no "PLACEHOLDER" text). `pytest` passes.
- `STATUS.md` "Footage and evaluation set" table is filled in.

### AI-03.6 First look at the hard question *(human judgment, 15 minutes)*

Put a correct frame, a "slightly too much" frame, and the reference still side by side. Can **you** tell them apart at a glance? If a person cannot, a model will not do it reliably.

- If yes: continue.
- If no: change the scripted mistake to one that is visible (rice over the top margin; filling in the wrong place) or change the criterion to something binary ("bare nori visible along the far edge"). Record the decision in `STATUS.md` and tell the team at the next sync.

**Acceptance:** one sentence in `STATUS.md` stating the outcome.

## Verification

```bash
cd ai
python scripts/extract_frames.py footage/chef-take-1.mp4 /tmp/frames-test --every 5
pytest -q
```

## Out of scope

Running models on the frames (AI-04, AI-07). Automated ingestion of the chef video (AI-06).

## When done

Update `STATUS.md` (batch 03), commit `[ai] AI-03 footage, eval set, real fixture stills`, push, and tell the backend owner that real reference stills are in the fixture so they can re-seed.
