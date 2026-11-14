You are given a first-person video of an expert preparing a dish while narrating what they do. The camera is worn at eye level and looks down at the work surface. Turn the video into a recipe that a learner can follow step by step, wearing the same kind of camera, with every step checkable from a single photo of their work surface.

{{TITLE_HINT}}
{{STEP_MARKS}}

Return JSON that matches the schema. Rules:

**Steps**
- Between 4 and 10 steps. A step is one action with a visible finished state.
- Merge trivial actions into the step they belong to. Split a step if it has two results that can be checked separately.
- Order the steps as they happen in the video.

**Text shown in the glasses**
- `title`: at most 4 words, an imperative ("Fold the edges").
- `key_line`: at most 8 words, the one thing to get right, readable in one second.

**Text spoken or shown on request**
- `instruction`: one to three sentences, using the expert's own wording where possible.
- `chef_quote`: one sentence the expert actually says during this step, word for word, or null if they say nothing relevant. Never invent a quote.

**What "right" looks like**
- `success_criteria`: 1 to 3 items. Each must be visible in a single top-down photo of the work surface: coverage, margins, position, shape, count, thickness as it appears from above. Never taste, smell, temperature, pressure, sound, or timing.
- `watch_fors`: 0 to 3 per step. Only mistakes that are (a) common for beginners, (b) visible in a photo, and (c) different from a step that is simply not finished yet. Prefer mistakes the expert mentions. Each has:
  - `id`: lowercase snake_case, e.g. `too_much_filling`
  - `mistake`: what the mistake looks like in a photo
  - `headline`: at most 4 words
  - `fix`: at most 8 words, an action the learner can do with their hands
  - `spoken`: one friendly sentence telling the learner what to change

**Times** (seconds from the start of the video)
- `timestamp_s`: the moment the **finished state** of the step is clearly visible with the hands mostly out of the way. Not the start of the step. This frame becomes the learner's reference photo.
- `clip_start_s`, `clip_end_s`: a 3 to 5 second window showing the key hand movement of the step.
- `timer_s`: only if the expert states a waiting time for this step, else null.

**Transcript**
- `transcript`: everything the expert says, word for word, in order. If nothing is said, return an empty string. Never invent narration.

**Recipe title**
- `title`: from the narration if the expert names the dish, otherwise from the hint above, otherwise a short descriptive name.
