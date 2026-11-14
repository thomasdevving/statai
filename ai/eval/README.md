# Evaluation set

> Five facts about the set (AI-03.4). Fill in the blanks after labelling; write only what is true.

1. **What it is:** first-person frames of the "Add fillings" step (step 4) of the sandwich fixture recipe, labelled `pass` / `fix` / `unsure` against the chef's criteria; `dev` is for writing prompts, `heldout` is run once in AI-07.
2. **Counts:** _not labelled yet_. Paste the table printed by `python scripts/check_cases.py`.
3. **Device:** _not recorded yet_. Glasses model, or phone used as a stand-in (a phone is not proof of what the glasses see).
4. **Labelled by:** _initials, date_. Labels were set by looking at each frame before any model saw it.
5. **Known weaknesses:** _e.g. one kitchen, one light, two people's hands, one recipe_.

## Workflow

```bash
# from ai/  — 1. frames from each clip into the right split folder
python scripts/extract_frames.py footage/<clip>.mp4 eval/frames/dev --every 2.5 --prefix <clip>
python scripts/extract_frames.py footage/heldout/<clip>.mp4 eval/frames/heldout --every 2.5 --prefix <clip>
# 2. delete near-duplicates and any frame with a face or a bystander
# 3. add one unlabelled row per new frame, then fill in label (+ mistake_id for fix) in a spreadsheet
python scripts/check_cases.py --scaffold --step 4 --labeller <initials> --device "<device>"
# 4. validate and print the counts
python scripts/check_cases.py --require-minimum
```

Do not open the `heldout` frames while writing prompts (AI-04). Raw clips live in `ai/footage/` (gitignored) and on the team drive, never in git. Keep committed frames under ~30 MB.

## Voice Q&A cases (`qa.csv`, AI-05.5)

Columns `id,question,kind,expected`; `kind` is `in_lesson` (answerable from the chef's transcript) or `out_of_lesson` (the answer must start "The chef doesn't cover that in this lesson"). 10 + 5 rows. The row with `id` **`demo`** is the question for demo beat 6 ("Why spread it to the edges?"). **Built from the placeholder narration** in `fixtures/sushi_recipe.json` (no real chef take exists, team decision 2026-11-14): if a real transcript ever replaces it, re-check every `expected` and keep the demo question one the chef actually answers. Scoring happens in AI-07.
