# AI-07 — Evaluation, threshold tuning, ablation, results

| | |
|---|---|
| **Track** | `ai/` |
| **Gate** | First run for G3, final numbers for G4 |
| **Depends on** | AI-03 (labelled set), AI-04 (final prompts). Deployed-latency rows need BE-04. Q&A scoring needs AI-05. |
| **Unblocks** | The evidence slide (WEB-04) and every number anyone says on stage |
| **Size** | Medium |
| **Model** | Opus 5.5 for the runner. Sonnet 5.5 is enough for formatting result tables. |
| **Needs a human for** | Freezing the prompt, scoring Q&A answers, signing off the numbers |

## Goal

Measured, reproducible answers to: does it approve wrong work, does it reject right work, does it admit when it cannot see, how fast is it, does the watcher cry wolf, and what does the chef's reference actually add. Reported as counts on a held-out set, with the limits stated.

## Read first

- [../../docs/EVALUATION.md](../../docs/EVALUATION.md) — all of it. This batch implements §3, §4, and §7.
- `ai/eval/cases.csv`, `ai/eval/qa.csv`
- `ai/STATUS.md` — dev-set results from AI-04

## Rules

1. Tune on `dev` only. **Freeze** the prompts, model IDs, frame sizes, and threshold, and commit. Only then run `heldout`, **once**.
2. If the held-out result is bad, report it as it is. Do not re-tune on held-out and re-report as if it were unseen. If you do iterate after seeing held-out, say so in the results: the set is then no longer held out.
3. Every result file records: date and time, model IDs, prompt file hashes (or the git commit), frame size, set name and size, and where it was run from.

## Tasks

### AI-07.1 Evaluation runner

**Do** — `src/ghostchef_ai/eval.py`, runnable as `python -m ghostchef_ai.eval`:

```
--split dev|heldout
--config full|no-ref|generic
--mode check|watch         (default check)
--cases eval/cases.csv
--out eval/results/
--concurrency 2            (respect the rate limit from STATUS.md)
```

- `full`: `check_frame(frame, step, ref_image)` as shipped.
- `no-ref`: `check_frame(frame, step, None)`.
- `generic`: a deliberately plain prompt, kept in `prompts/generic_check.md` ("Here is a photo of a cooking step called <title>. Is it done correctly? Answer pass, fix, or unsure."), same output schema, no criteria, no reference.
- `--mode watch`: `watch_frame` per frame; a `fix`-labelled frame counts as detected when `status == "warn"` with the labelled `mistake_id`; `pass` and `unsure` frames count as false warnings when `status == "warn"` with `confidence ≥ threshold`.
- Output: one JSON file with every case (id, label, prediction, confidence, latency, error if any) and one Markdown summary with the confusion table, the named metrics from EVALUATION §4, latency p50 and max, and the count of errors/timeouts. File names: `<UTC timestamp>-<split>-<config>-<mode>.{json,md}`.
- Works in fake mode (for a unit test of the runner itself).

**Acceptance:** runner unit test passes in fake mode; a real `--split dev --config full` run completes and writes both files.

### AI-07.2 Watcher behaviour on clips

**Do** — `ai/scripts/watch_clip.py`:
- Input: a clip, the step index, the expected `mistake_id` or `none`, and optionally the second at which the mistake becomes visible / is fixed.
- Extract a frame every 2.5 s, call `watch_frame` on each in order, then **simulate the client debounce** exactly as in [API-CONTRACT §3.3](../../docs/API-CONTRACT.md#33-client-rules-for-the-watcher-ios-and-web-implement-these-identically) (2 consecutive, same id, confidence ≥ threshold).
- Report: alerts raised and when; for mistake clips the **detection delay** from the marked second; for correct clips the **false alerts per minute**; for fix-sequence clips whether warnings stop after the fix.

**Acceptance:** run on every dev clip from AI-03.2; summary table written to `eval/results/`.

### AI-07.3 Tune on dev, then freeze

**Do**
- Sweep `WATCH_THRESHOLD` over 0.5–0.9 on the dev clips; pick the value that gives zero false alerts on correct dev clips with the shortest detection delay. Write it to `STATUS.md` → "Tuned values the clients need".
- Confirm the `confidence < 0.5 → unsure` rule in `check.py` on dev; adjust the cut-off if it clearly helps.
- Commit with message `[ai] freeze prompts and thresholds for held-out run`. Note the commit hash.

**Acceptance:** `STATUS.md` shows the tuned threshold and the freeze commit. The iOS and web owners are told the threshold.

### AI-07.4 Held-out run and ablation

**Do** — once, after the freeze:

```bash
python -m ghostchef_ai.eval --split heldout --config full
python -m ghostchef_ai.eval --split heldout --config no-ref
python -m ghostchef_ai.eval --split heldout --config generic
python -m ghostchef_ai.eval --split heldout --config full --mode watch
python scripts/watch_clip.py …            # each held-out clip
```

**Acceptance**
- Result files committed under `ai/eval/results/`.
- `STATUS.md` "Results" has the filled tables from EVALUATION §4 (metrics table and ablation table), with set sizes, model IDs, date.
- A three-line plain summary: what it gets right, what it gets wrong, what the reference image added. If the ablation shows no benefit from the reference, say exactly that.

### AI-07.5 Deployed latency

**Do** — once BE-04 is live: read `latency` from `GET /sessions/{id}/monitor` after a rehearsal, or run the backend's smoke script against production (`backend/scripts/smoke.py`, run by the backend owner). Record p50 and max for check and watch, the network used (venue Wi-Fi or hotspot), and n.

**Acceptance:** the two latency rows in `STATUS.md` are filled from the deployed system, not from a laptop calling Gemini directly.

### AI-07.6 Voice Q&A scoring *(human)*

Run each question in `eval/qa.csv` through `scripts/live_smoke.py` (extend it to loop over the file and save transcripts or audio). A person scores each: `in_lesson` → used the chef's content correctly (yes/no); `out_of_lesson` → said the lesson does not cover it and did not invent a chef statement (yes/no).

**Acceptance:** counts recorded in `STATUS.md` as "x of 10" and "y of 5", with the scorer's initials.

### AI-07.7 Hand over the numbers

**Do**
- Prepare the exact rows for [EVALUATION.md §4](../../docs/EVALUATION.md#4-metrics-targets-results) and the status column of §2, and give them to whoever commits `[docs]` changes (or make that single `[docs]` commit yourself if the team agreed).
- Give the `web/` owner: the counts, the latency, the ablation table, the limits sentence ("one recipe, N steps, our own footage, M held-out frames"), and two or three example frames (a caught mistake, a correct pass, an `unsure`) that contain no faces.

**Acceptance:** the `web/` owner confirms they have what the evidence slide needs.

## Verification

```bash
cd ai
ruff check .
GHOSTCHEF_AI_FAKE=1 GHOSTCHEF_AI_FAKE_DELAY=0 pytest -q
python -m ghostchef_ai.eval --split dev --config full
ls eval/results/
```

## Out of scope

Changing the product to chase a number after the freeze. Observed user sessions (WEB-04).

## When done

Update `STATUS.md`, commit `[ai] AI-07 evaluation results`, push.
