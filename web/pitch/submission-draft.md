# Submission text — draft

> Drafted by Claude for the human owner to paste. Nothing here has been submitted. Claims follow [docs/PRODUCT.md §10](../../docs/PRODUCT.md#10-what-we-can-and-cannot-claim): only what exists in the repository today.
> Final name is still open (Q-12); the team is using **Echo**.

## Preliminary submission (WEB-05.1)

**Status:** not missed, per the web owner (Sat 14 Nov). Record the submission time and who submitted in `web/STATUS.md` → Submission. The fields below are what was planned; reuse them for the final form.

| Field | Value |
|---|---|
| Project name | Echo |
| Challenges | **Meta — AI Glasses for Everyone, Everyday** (main); **Google DeepMind — Best Use of Gemini API** (technology). Not Arduino. |
| Team | Thomas, Stelios, Aleksandr, Türker |
| Short description | A chef records a recipe once through smart glasses; anyone wearing the glasses can then cook it hands-free while Gemini compares what they are doing with the chef's own point-of-view footage, corrects mistakes as they happen, and answers questions in the chef's method. |
| Repository | https://github.com/thomasdevving/statai |
| Video / demo link | None yet. If the form requires one, say so; do not invent a link. |

## Final description skeleton (WEB-05.7)

Fill the three lists from each track's `STATUS.md` on Sunday morning; delete anything not true at that moment.

**What we built this weekend**
- ⟨iOS app: Cook mode and Chef mode on Meta glasses via the Device Access Toolkit — per ios/STATUS.md⟩
- ⟨FastAPI backend: recipes, check, watch, sessions, Gemini Live tokens — per backend/STATUS.md⟩
- ⟨Gemini: recipe extraction from chef video, frame check against the chef's reference, proactive watcher, Live voice answers — per ai/STATUS.md⟩
- Web: a browser simulator of the cook-along loop, a recipe review page, and an audience monitor ⟨per web/STATUS.md⟩

**What runs live in the demo**
- ⟨only items verified on the real device and production backend⟩

**What is planned, not built**
- ⟨e.g. more dishes, personalization⟩

**Measured results**
- ⟨numbers from docs/EVALUATION.md §4 only; none measured yet⟩
