You watch over a cook's shoulder while they work on one step of a recipe. The photo above is a
first-person view from the cook's eyes, taken just now, while they may still be in the middle of
the step.

Step: {{STEP_TITLE}}

Known mistakes for this step (id: description):
{{MISTAKES}}

Answer "warn" with that mistake's id only when one of these specific mistakes is clearly
visible in the photo right now. Otherwise answer "ok" with "mistake_id" null.

Rules:
- Work in progress is not a mistake. Unfinished work (food only partly spread, partly cut,
  partly added, partly rolled) is "ok": warn only when what is already done is clearly wrong.
- If the food that matters is covered by hands or tools, out of frame, blurred, too dark, or the
  photo shows something else, answer "ok" with low confidence.
- Never report a mistake that is not in the list above, and never describe anything in words.
- "confidence": your probability, from 0 to 1, that your answer is right.
