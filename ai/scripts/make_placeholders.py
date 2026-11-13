"""Write placeholder reference stills for the fixture recipe.

Usage (from ai/):  python scripts/make_placeholders.py [--fixture fixtures]

One 720x1280 portrait JPEG per step at fixtures/images/step-<idx>.jpg, clearly marked as a
placeholder. A light deterministic noise texture keeps each file above 5000 bytes, so fake
check_frame does not treat it as unjudgeable. Replaced by real chef stills in AI-03.5.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 720, 1280


def _font(size: int) -> ImageFont.ImageFont:
    for name in ("DejaVuSans-Bold.ttf", "arialbd.ttf", "Arial Bold.ttf", "Helvetica.ttc"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow < 10.1
        return ImageFont.load_default()


def _texture(seed: int) -> Image.Image:
    rng = random.Random(seed)
    small = Image.new("RGB", (W // 8, H // 8))
    small.putdata(
        [(18 + rng.randint(0, 22), 22 + rng.randint(0, 22), 28 + rng.randint(0, 22))
         for _ in range((W // 8) * (H // 8))]
    )
    return small.resize((W, H), Image.Resampling.NEAREST)


def make(idx: int, title: str, out: Path) -> None:
    img = _texture(idx)
    d = ImageDraw.Draw(img)
    big, small = _font(64), _font(30)
    d.text((W / 2, H / 2 - 40), f"{idx}. {title}", font=big, fill=(240, 240, 240), anchor="mm")
    d.text((W / 2, H / 2 + 50), "PLACEHOLDER — not chef footage", font=small,
           fill=(255, 190, 70), anchor="mm")
    img.save(out, "JPEG", quality=80)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--fixture", default=str(Path(__file__).resolve().parents[1] / "fixtures"))
    args = p.parse_args()
    fixture = Path(args.fixture)
    recipe = json.loads((fixture / "sushi_recipe.json").read_text(encoding="utf-8"))
    images = fixture / "images"
    images.mkdir(parents=True, exist_ok=True)
    for step in recipe["steps"]:
        out = images / f"step-{step['idx']}.jpg"
        make(step["idx"], step["title"], out)
        print(f"{out}  {out.stat().st_size} bytes")


if __name__ == "__main__":
    main()
