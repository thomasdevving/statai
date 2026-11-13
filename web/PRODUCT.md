# Product

<!-- impeccable:product-schema 1 -->

Scope: the `web/` track only (simulator, review page, demo monitor, pitch assets). Product truth for the whole project lives in [../docs/PRODUCT.md](../docs/PRODUCT.md) and [../docs/TECH-SPEC.md](../docs/TECH-SPEC.md); this file summarises what web work must preserve and does not override them.

## Platform

web

## Stack

Plain HTML, CSS and ES modules. No build step, no framework, no package install (decided in [README.md](README.md)). Served by the FastAPI backend under `/app/` or by any static server.

## Users

- **Hackathon judges and the audience at the stand** watching the demo monitor from about three metres away while a volunteer cooks wearing the glasses. They cannot see inside the lens.
- **The chef or instructor** reviewing, editing and publishing a recipe the iOS app recorded, on a laptop.
- **The team** using the simulator to test `backend/` and `ai/` end to end without the glasses, and as a last-resort demo fallback.

## Product Purpose

A chef records a recipe once through smart glasses; anyone wearing the glasses can then cook it hands-free while Gemini compares their view with the chef's own point-of-view footage, corrects mistakes as they happen, and answers questions in the chef's method. The web track makes that visible to people outside the lens, lets the chef correct what was extracted, and carries the pitch and submission.

## Positioning

The comparison is like with like: the chef's reference and the learner's frame are both first-person from eye level, so "does mine look like the chef's?" is answerable. The system can speak first because the camera already sees the work.

## Operating Context

- Junction 2026 hackathon; Meta main challenge plus Gemini technology challenge.
- The demo dish is a maki roll; the stage moment is a volunteer spreading too much rice, the glasses catching it, the fix, the pass.
- The monitor runs on a laptop or external screen at a busy stand.

## Capabilities and Constraints

- The lens card looks the same everywhere: black background, bright elements, at most two short text lines, amber for fix, green for pass.
- Every page shows what it is connected to (API base, `ai_mode`, `storage`), turning red when `ai_mode` is `fake`.
- Anything not live carries a visible `REPLAY` badge.
- Claims use only measured values recorded in the tracks' `STATUS.md` files and `docs/EVALUATION.md`.
- **Open:** final product name (Q-12). Working name for web surfaces is **Echo** (user decision, 2026-11-14; matches the Monitor C mockup).

## Brand Commitments

- Working name **Echo** (see Open above).
- The user pinned the palette: `#0082FB`, `#0064E0`, `#F1F5F8`, `#1C2B33`, plus amber and green status colours for fix and pass. Typeface in the existing Monitor C mockup is Figtree.
- Our own mark only. Meta's logo and name are not used as our branding.

## Evidence on Hand

- Monitor C mockup (design reference, outside the repo).
- Fixture recipe and placeholder step images in `../ai/fixtures/`.
- No user testing yet; no measured accuracy or latency numbers yet. Do not fabricate either.

## Product Principles

1. Show the audience what the wearer sees, and why the system spoke.
2. Honest labels over impressive ones: fake, replay and live are always distinguishable.
3. Readable from three metres beats dense.
4. The chef's method is the authority; inferred advice is never attributed to the chef.

## Accessibility & Inclusion

Everything works with the keyboard, images have alt text, and no information is carried by colour alone (fix and pass also differ by icon and word).
