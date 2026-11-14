"""Extract JPEG frames from a video with ffmpeg (AI-03.3).

Usage (from ai/):

    # one frame every 2.5 s (the watcher interval), long edge 1280 px
    python scripts/extract_frames.py footage/clip.mp4 eval/frames/dev --every 2.5

    # a single reference still at 74.5 s, saved as fixtures/images/step-3.jpg
    python scripts/extract_frames.py footage/chef-take-1.mp4 fixtures/images --at 74.5 --name step-3

Frames are named <prefix>-<seconds>.jpg, e.g. take1-0074.50.jpg (prefix defaults to the video
file name). Images are never upscaled; rotation metadata from phones is applied by ffmpeg.
Needs the ffmpeg and ffprobe binaries on the PATH. This is a helper script: the
ghostchef_ai package itself never calls ffmpeg (that is backend/'s job).
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

INSTALL_HINT = (
    "ffmpeg / ffprobe not found on the PATH. Install it, then open a new terminal:\n"
    "  Windows:  winget install ffmpeg\n"
    "  macOS:    brew install ffmpeg\n"
    "  Linux:    sudo apt install ffmpeg"
)


def find_tools() -> tuple[str, str]:
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        sys.exit(INSTALL_HINT)
    return ffmpeg, ffprobe


def probe_duration(ffprobe: str, video: Path) -> float:
    out = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "json", str(video)],
        capture_output=True, text=True, check=False,
    )
    if out.returncode != 0:
        sys.exit(f"ffprobe could not read {video}: {out.stderr.strip()[:300]}")
    try:
        return float(json.loads(out.stdout)["format"]["duration"])
    except (KeyError, ValueError, json.JSONDecodeError):
        sys.exit(f"ffprobe returned no duration for {video}")


def timestamps(duration: float, every: float) -> list[float]:
    """0, every, 2*every, ... strictly before the end (the last frame may not exist)."""
    if every <= 0:
        raise ValueError("--every must be positive")
    out, i = [], 0
    while (t := round(i * every, 3)) < duration - 0.05:
        out.append(t)
        i += 1
    return out


def scale_filter(long_edge: int) -> str:
    """Fit the long edge to at most long_edge px, keep aspect ratio, never upscale."""
    L = long_edge
    return (f"scale='if(gt(iw,ih),min({L},iw),-2)':'if(gt(iw,ih),-2,min({L},ih))'")


def ffmpeg_cmd(ffmpeg: str, video: Path, at: float, out: Path, long_edge: int,
               qscale: int) -> list[str]:
    # -ss before -i: fast, keyframe-accurate seek that ffmpeg then refines to the exact time.
    return [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{at:.3f}",
            "-i", str(video), "-frames:v", "1", "-vf", scale_filter(long_edge),
            "-q:v", str(qscale), str(out)]


def frame_name(prefix: str, t: float) -> str:
    return f"{prefix}-{t:07.2f}.jpg"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("video", type=Path)
    p.add_argument("out_dir", type=Path)
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--every", type=float, default=2.5, help="seconds between frames")
    mode.add_argument("--at", type=float, help="extract one frame at this second")
    p.add_argument("--long-edge", type=int, default=1280)
    p.add_argument("--prefix", help="file name prefix (default: video file name)")
    p.add_argument("--name", help="with --at: output file name without .jpg")
    p.add_argument("--qscale", type=int, default=3, help="ffmpeg JPEG quality, 2 best..31 worst")
    args = p.parse_args(argv)

    if not args.video.is_file():
        sys.exit(f"no such video: {args.video}")
    ffmpeg, ffprobe = find_tools()
    duration = probe_duration(ffprobe, args.video)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    prefix = args.prefix or args.video.stem

    if args.at is not None:
        if not 0 <= args.at < duration:
            sys.exit(f"--at {args.at} is outside the video (0 – {duration:.2f} s)")
        jobs = [(args.at, args.out_dir / f"{args.name or frame_name(prefix, args.at)[:-4]}.jpg")]
    else:
        jobs = [(t, args.out_dir / frame_name(prefix, t)) for t in timestamps(duration, args.every)]

    written = 0
    for t, out in jobs:
        r = subprocess.run(ffmpeg_cmd(ffmpeg, args.video, t, out, args.long_edge, args.qscale),
                           capture_output=True, text=True, check=False)
        if r.returncode != 0 or not out.exists():
            print(f"skip {t:.2f}s: {r.stderr.strip()[:200] or 'no frame produced'}",
                  file=sys.stderr)
            continue
        written += 1
    print(f"{args.video.name}: {duration:.2f} s -> {written} frame(s) in {args.out_dir}")
    return 0 if written else 1


if __name__ == "__main__":
    sys.exit(main())
