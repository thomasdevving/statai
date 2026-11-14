"""Local copies of source videos for review-time re-extraction (BE-06.4).

The chef re-picks several frames in a row, so the source video is kept on local disk for
10 minutes (extended on every use), at most 2 videos at once, least recently used evicted first.
Everything lives in one private temp dir, removed on shutdown.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
import time
import weakref
from collections import OrderedDict
from pathlib import Path

from app.config import get_settings
from app.media.ffmpeg import ProbeResult, probe
from app.store.base import Recipe, Store

log = logging.getLogger("ghostchef.videocache")

TTL_S = 600.0
MAX_ENTRIES = 2

# recipe_id -> (file, probe result, expires monotonic)
_entries: OrderedDict[str, tuple[Path, ProbeResult, float]] = OrderedDict()
_dir: Path | None = None
_inflight: set[str] = set()
_cancelled: set[str] = set()  # evicted while their download was running
_timer: asyncio.TimerHandle | None = None
_locks: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock] = (
    weakref.WeakKeyDictionary()
)


def _lock() -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    lock = _locks.get(loop)
    if lock is None:
        lock = _locks[loop] = asyncio.Lock()
    return lock


def _cache_dir() -> Path:
    global _dir
    if _dir is None or not _dir.is_dir():
        _dir = Path(tempfile.mkdtemp(prefix="ghostchef-videocache-"))
    return _dir


def _drop(recipe_id: str) -> None:
    entry = _entries.pop(recipe_id, None)
    if entry is not None:
        entry[0].unlink(missing_ok=True)


def _purge_expired() -> None:
    now = time.monotonic()
    for rid in [r for r, (_, _, until) in _entries.items() if until <= now]:
        _drop(rid)


def _schedule_purge() -> None:
    """Idle servers must not keep videos on disk past their TTL: purge on a timer too."""
    global _timer
    if _timer is not None:
        _timer.cancel()
        _timer = None
    if not _entries:
        return
    delay = max(min(until for _, _, until in _entries.values()) - time.monotonic(), 0.0) + 0.05
    _timer = asyncio.get_running_loop().call_later(delay, _on_timer)


def _on_timer() -> None:
    global _timer
    _timer = None
    _purge_expired()
    _schedule_purge()


def _enforce_limit() -> None:
    while len(_entries) > MAX_ENTRIES:
        _drop(next(iter(_entries)))


def _lookup(recipe_id: str) -> tuple[Path, ProbeResult] | None:
    _purge_expired()
    entry = _entries.get(recipe_id)
    if entry is None or not entry[0].is_file():
        _drop(recipe_id)
        return None
    _entries[recipe_id] = (entry[0], entry[1], time.monotonic() + TTL_S)
    _entries.move_to_end(recipe_id)
    _schedule_purge()
    return entry[0], entry[1]


async def put(recipe_id: str, source: Path, info: ProbeResult) -> None:
    """Adopt `source` (moved, not copied) as the cached copy for recipe_id."""
    _purge_expired()
    _drop(recipe_id)
    target = _cache_dir() / f"{recipe_id}.mp4"
    await asyncio.to_thread(shutil.move, str(source), str(target))
    _entries[recipe_id] = (target, info, time.monotonic() + TTL_S)
    _entries.move_to_end(recipe_id)
    _enforce_limit()
    _schedule_purge()


async def get_or_download(store: Store, recipe: Recipe) -> tuple[Path, ProbeResult] | None:
    """The local copy of the recipe's source video and its probe, downloading it if needed.
    None when the object is gone. Raises BlobTooLarge / FfmpegError for unusable videos."""
    if not recipe.video_path:
        return None
    async with _lock():
        hit = _lookup(recipe.id)
        if hit is not None:
            return hit
        target = _cache_dir() / f"{recipe.id}.mp4"
        _inflight.add(recipe.id)
        try:
            found = await store.download_to_file(
                "videos", recipe.video_path, target, get_settings().max_video_bytes
            )
            if not found:
                return None
            info = await probe(target)
            if recipe.id in _cancelled:  # deleted while downloading: do not cache it
                target.unlink(missing_ok=True)
                return None
        except BaseException:
            target.unlink(missing_ok=True)
            raise
        finally:
            _inflight.discard(recipe.id)
            _cancelled.discard(recipe.id)
        _entries[recipe.id] = (target, info, time.monotonic() + TTL_S)
        _entries.move_to_end(recipe.id)
        _enforce_limit()
        _schedule_purge()
        return target, info


def evict(recipe_id: str) -> None:
    _drop(recipe_id)
    if recipe_id in _inflight:
        _cancelled.add(recipe_id)


def clear() -> None:
    global _dir, _timer
    if _timer is not None:
        _timer.cancel()
        _timer = None
    _entries.clear()
    if _dir is not None:
        shutil.rmtree(_dir, ignore_errors=True)
        _dir = None


reset = clear
