"""ffmpeg / ffprobe helpers (BE-06.1). Always argv lists via create_subprocess_exec, never a shell.

Inputs are untrusted uploads: the demuxer is forced to mov/mp4 and only the `file` protocol is
allowed, so a crafted file cannot make ffmpeg open other URLs or paths.
"""

from __future__ import annotations

import asyncio
import functools
import json
import math
import shutil
from pathlib import Path
from typing import Any, TypedDict

PROBE_TIMEOUT_S = 30.0
STILL_TIMEOUT_S = 60.0
CLIP_TIMEOUT_S = 120.0
MAX_CLIP_S = 6.0
_STDERR_TAIL = 800


class FfmpegError(RuntimeError):
    """A failed ffmpeg/ffprobe call. `stderr` is for logs only, never for clients."""

    def __init__(self, message: str, stderr: str = "") -> None:
        super().__init__(message)
        self.stderr = stderr[-_STDERR_TAIL:]


class ProbeResult(TypedDict):
    duration_s: float
    width: int
    height: int
    rotation: int


@functools.cache
def ffmpeg_available() -> bool:
    return bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


async def _run(args: list[str], timeout_s: float) -> bytes:
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout_s)
    except TimeoutError:
        await _kill(proc)
        raise FfmpegError("timed out") from None
    except BaseException:
        await _kill(proc)
        raise
    if proc.returncode != 0:
        tail = err.decode("utf-8", "replace")
        raise FfmpegError(f"{Path(args[0]).name} exited with {proc.returncode}", tail)
    return out


async def _kill(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is None:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
    await asyncio.shield(proc.wait())


def _abs(path: Path | str) -> str:
    return str(Path(path).resolve())


def _scale(long_edge: int) -> str:
    # ffmpeg autorotates before filters, so iw/ih are the upright size. Never upscale.
    return f"scale='if(gte(iw,ih),min({long_edge},iw),-2)':'if(gte(iw,ih),-2,min({long_edge},ih))'"


def _rotation(stream: dict[str, Any]) -> int:
    for side in stream.get("side_data_list") or []:
        if "rotation" in side:
            return round(float(side["rotation"])) % 360
    rotate = (stream.get("tags") or {}).get("rotate")
    if rotate is not None:
        try:
            return round(float(rotate)) % 360
        except ValueError:
            pass
    return 0


async def probe(path: Path | str) -> ProbeResult:
    out = await _run(
        [
            "ffprobe", "-v", "error", "-f", "mov", "-protocol_whitelist", "file",
            "-print_format", "json", "-show_format", "-show_streams", "-select_streams", "v:0",
            _abs(path),
        ],
        PROBE_TIMEOUT_S,
    )  # fmt: skip
    try:
        data = json.loads(out)
        streams = data.get("streams") or []
        if not streams:
            raise FfmpegError("no video stream")
        stream = streams[0]
        raw = (data.get("format") or {}).get("duration") or stream.get("duration")
        duration = float(raw)
        width, height = int(stream["width"]), int(stream["height"])
    except FfmpegError:
        raise
    except (ValueError, TypeError, KeyError):
        raise FfmpegError("unreadable probe output") from None
    if not math.isfinite(duration) or duration <= 0 or width <= 0 or height <= 0:
        raise FfmpegError("video has no usable duration")
    return {
        "duration_s": duration,
        "width": width,
        "height": height,
        "rotation": _rotation(stream),
    }


def _check_output(out_path: Path, what: str) -> None:
    if not out_path.is_file() or out_path.stat().st_size == 0:
        out_path.unlink(missing_ok=True)
        raise FfmpegError(f"{what} produced no output")


async def extract_still(
    path: Path | str, at_s: float, out_path: Path | str, long_edge: int = 1280
) -> None:
    out = Path(out_path).resolve()
    await _run(
        [
            "ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", "-y",
            "-ss", f"{max(at_s, 0.0):.3f}", "-f", "mov", "-protocol_whitelist", "file",
            "-i", _abs(path), "-frames:v", "1", "-vf", _scale(long_edge),
            "-q:v", "3", "-an", str(out),
        ],
        STILL_TIMEOUT_S,
    )  # fmt: skip
    _check_output(out, "still")


async def extract_clip(
    path: Path | str, start_s: float, end_s: float, out_path: Path | str, long_edge: int = 720
) -> None:
    duration = min(end_s - start_s, MAX_CLIP_S)
    if duration <= 0:
        raise FfmpegError("empty clip window")
    out = Path(out_path).resolve()
    await _run(
        [
            "ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", "-y",
            "-ss", f"{max(start_s, 0.0):.3f}", "-t", f"{duration:.3f}",
            "-f", "mov", "-protocol_whitelist", "file", "-i", _abs(path),
            "-map", "0:v:0", "-an", "-sn", "-dn", "-vf", _scale(long_edge),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "26", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", "-map_metadata", "-1", str(out),
        ],
        CLIP_TIMEOUT_S,
    )  # fmt: skip
    _check_output(out, "clip")
