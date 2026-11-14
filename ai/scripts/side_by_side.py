"""Put frames side by side for the AI-03.6 "can a person tell?" check.

Usage (from ai/):

    python scripts/side_by_side.py fixtures/images/step-3.jpg eval/frames/dev/a.jpg \
        eval/frames/dev/b.jpg --labels "chef reference" "correct" "slightly too much" \
        -o eval/side_by_side.jpg

Writes one JPEG with the images in a row at the same height, each labelled underneath.
Look at it for a few seconds: if you cannot tell correct from mistake at a glance, a single
frame will not be enough for the model either (see ai/tasks/03, AI-03.6).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HEIGHT, LABEL_H, GAP = 900, 60, 16


def _font(size: int):
    for name in ("DejaVuSans.ttf", "arial.ttf", "Arial.ttf", "Helvetica.ttc"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def compose(paths: list[Path], labels: list[str]) -> Image.Image:
    tiles = []
    for p in paths:
        with Image.open(p) as im:
            im = im.convert("RGB")
            w = round(im.width * HEIGHT / im.height)
            tiles.append(im.resize((w, HEIGHT)))
    width = sum(t.width for t in tiles) + GAP * (len(tiles) + 1)
    sheet = Image.new("RGB", (width, HEIGHT + LABEL_H + 2 * GAP), (16, 16, 16))
    draw, font = ImageDraw.Draw(sheet), _font(32)
    x = GAP
    for tile, label in zip(tiles, labels, strict=True):
        sheet.paste(tile, (x, GAP))
        draw.text((x + tile.width / 2, GAP + HEIGHT + LABEL_H / 2), label, font=font,
                  fill=(235, 235, 235), anchor="mm")
        x += tile.width + GAP
    return sheet


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("images", nargs="+", type=Path)
    p.add_argument("--labels", nargs="+")
    p.add_argument("-o", "--output", type=Path, default=Path("eval/side_by_side.jpg"))
    args = p.parse_args(argv)
    labels = args.labels or [i.stem for i in args.images]
    if len(labels) != len(args.images):
        sys.exit("give exactly one --labels entry per image")
    missing = [str(i) for i in args.images if not i.is_file()]
    if missing:
        sys.exit(f"not found: {', '.join(missing)}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    compose(args.images, labels).save(args.output, "JPEG", quality=85)
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
