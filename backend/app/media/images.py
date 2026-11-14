"""JPEG validation and downscaling for /check and /watch frames (BE-03.2).

Pillow is blocking, so the async wrappers run it in a worker thread. Each frame is opened and
decoded once: validation and downscaling share one pass (`_prepare_sync`).
"""

from __future__ import annotations

import asyncio
import io
import logging

from PIL import Image, ImageOps, UnidentifiedImageError

from app.errors import ApiError

log = logging.getLogger("ghostchef.images")

MB = 1024 * 1024

# Contract §3 limits.
CHECK_MAX_BYTES = int(1.5 * MB)
CHECK_LONG_EDGE = 1280
WATCH_SOFT_BYTES = 200 * 1024  # over this a watch frame is downscaled, not rejected
WATCH_MAX_BYTES = CHECK_MAX_BYTES  # hard limit for watch (lenient with clients)
WATCH_LONG_EDGE = 512

# A small file can still declare a huge canvas (decompression bomb). 16 MP covers any phone or
# glasses camera frame; the decoder's draft mode keeps the actual decode near the target size.
MAX_PIXELS = 16_000_000
JPEG_QUALITY = 80
# Camera JPEGs with an MPF marker (iPhone depth / gain maps) open as "MPO"; they are JPEGs.
JPEG_FORMATS = ("JPEG", "MPO")
_ORIENTATION = 0x0112
_SWAPS_AXES = (5, 6, 7, 8)


def _unreadable() -> ApiError:
    return ApiError(415, "unsupported_media", "frame is not a readable JPEG")


def _open_jpeg(data: bytes) -> Image.Image:
    try:
        img = Image.open(io.BytesIO(data))
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise _unreadable() from None
    if img.format not in JPEG_FORMATS:
        raise ApiError(415, "unsupported_media", "frame must be a JPEG")
    width, height = img.size
    if width <= 0 or height <= 0 or width * height > MAX_PIXELS:
        raise ApiError(413, "payload_too_large", "frame dimensions are too large")
    return img


def _check_size(data: bytes, max_bytes: int) -> None:
    if not data:
        raise ApiError(422, "validation_error", "frame is empty")
    if len(data) > max_bytes:
        raise ApiError(413, "payload_too_large", f"frame is larger than {max_bytes / MB:.1f} MB")


def _prepare_sync(data: bytes, max_bytes: int, long_edge: int, force: bool) -> bytes:
    """Validates (size, JPEG, fully decodable) and returns the bytes to send to the model.

    The original bytes come back untouched when the upright image fits `long_edge`, carries no
    EXIF and `force` is off. Otherwise the frame is re-encoded at `long_edge` (quality 80) with
    EXIF orientation applied first and all EXIF (including location) dropped.
    """
    _check_size(data, max_bytes)
    img = _open_jpeg(data)
    try:
        exif = img.getexif()
    except Exception:  # noqa: BLE001 - a corrupt EXIF block: treat as none, re-encode below
        exif = None
    w, h = img.size
    if exif and exif.get(_ORIENTATION) in _SWAPS_AXES:
        w, h = h, w
    if max(w, h) <= long_edge and not exif and not force:
        try:
            img.load()  # decode fully: catches truncated or corrupt data
        except (OSError, ValueError, SyntaxError, Image.DecompressionBombError):
            raise _unreadable() from None
        return data

    try:
        img.draft("RGB", (long_edge, long_edge))  # decode at a reduced DCT scale when possible
        img.load()
        upright = ImageOps.exif_transpose(img) if exif else img
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError):
        raise _unreadable() from None
    if max(upright.size) > long_edge:
        upright.thumbnail((long_edge, long_edge), Image.Resampling.LANCZOS)
    if upright.mode != "RGB":
        upright = upright.convert("RGB")
    out = io.BytesIO()
    upright.save(out, "JPEG", quality=JPEG_QUALITY, optimize=True)  # no EXIF written
    return out.getvalue()


def validate_jpeg_sync(data: bytes, max_bytes: int) -> None:
    """413 over `max_bytes` or the pixel cap, 415 when Pillow cannot decode it as a JPEG."""
    _check_size(data, max_bytes)
    img = _open_jpeg(data)
    try:
        img.load()
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError):
        raise _unreadable() from None


def downscale_jpeg_sync(data: bytes, long_edge: int, *, force: bool = False) -> bytes:
    return _prepare_sync(data, len(data) or 1, long_edge, force)


async def validate_jpeg(data: bytes, max_bytes: int) -> None:
    await asyncio.to_thread(validate_jpeg_sync, data, max_bytes)


async def downscale_jpeg(data: bytes, long_edge: int, *, force: bool = False) -> bytes:
    return await asyncio.to_thread(downscale_jpeg_sync, data, long_edge, force=force)


async def prepare_check_frame(data: bytes) -> bytes:
    return await asyncio.to_thread(_prepare_sync, data, CHECK_MAX_BYTES, CHECK_LONG_EDGE, False)


async def prepare_watch_frame(data: bytes) -> bytes:
    over_budget = len(data) > WATCH_SOFT_BYTES
    if over_budget and len(data) <= WATCH_MAX_BYTES:
        log.warning(
            "watch frame of %d bytes is over the %d byte limit; downscaling",
            len(data),
            WATCH_SOFT_BYTES,
        )
    return await asyncio.to_thread(
        _prepare_sync, data, WATCH_MAX_BYTES, WATCH_LONG_EDGE, over_budget
    )
