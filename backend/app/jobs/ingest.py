"""Background ingestion job (BE-06): uploaded video -> probe -> Gemini -> ffmpeg -> `review`.

The bytes never pass through FastAPI, so validation happens here: the video is downloaded in
chunks (size limit), probed, and only then handed to the model. One job runs at a time; others
wait as `processing`.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
import weakref
from datetime import datetime, timedelta
from pathlib import Path

from app import ai, refcache
from app.config import get_settings
from app.errors import ApiError
from app.media import videocache
from app.media.ffmpeg import (
    FfmpegError,
    ProbeResult,
    extract_clip,
    extract_still,
    ffmpeg_available,
    probe,
)
from app.seed import clip_path, ref_image_path, step_from_spec
from app.store.base import BlobTooLarge, Step, Store, utcnow
from app.views import expire_stale_upload

log = logging.getLogger("ghostchef.ingest")

STALE_PROCESSING = timedelta(minutes=15)
MIN_CLIP_S = 1.0
MAX_CLIP_S = 6.0

_tasks: set[asyncio.Task[None]] = set()
# Recipes this process is about to process or is processing; startup_sweep leaves them alone.
_active: set[str] = set()
# One semaphore per running event loop: a module-level one would be bound to the first loop
# (TestClient makes a new loop per client).
_semaphores: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore] = (
    weakref.WeakKeyDictionary()
)


class IngestError(Exception):
    """A failure whose message is safe to show the chef."""


def _semaphore() -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    sem = _semaphores.get(loop)
    if sem is None:
        sem = _semaphores[loop] = asyncio.Semaphore(1)
    return sem


def reset() -> None:
    """Tests only."""
    _semaphores.clear()
    _active.clear()


def reserve(recipe_id: str) -> None:
    """Call before flipping a recipe to `processing`, so the sweep cannot fail it in between."""
    _active.add(recipe_id)


def release(recipe_id: str) -> None:
    _active.discard(recipe_id)


def start(store: Store, recipe_id: str) -> asyncio.Task[None]:
    _active.add(recipe_id)
    task = asyncio.create_task(run_ingestion(recipe_id, store=store), name=f"ingest-{recipe_id}")
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    task.add_done_callback(lambda _t: _active.discard(recipe_id))
    return task


async def wait_all() -> None:
    """Tests and shutdown: wait for every running job."""
    while _tasks:
        await asyncio.gather(*list(_tasks), return_exceptions=True)


async def cancel_all() -> None:
    """Shutdown: stop running jobs. Their recipes stay `processing` until the next startup."""
    for task in list(_tasks):
        task.cancel()
    await asyncio.gather(*list(_tasks), return_exceptions=True)


async def startup_sweep(store: Store, now: datetime | None = None) -> None:
    """Startup: stale `uploading` recipes fail, `processing` ones older than 15 minutes were
    interrupted by a restart (their job died with the process)."""
    now = now or utcnow()
    for recipe in await store.list_recipes():
        if recipe.status == "uploading":
            await expire_stale_upload(store, recipe, now)
        elif (
            recipe.status == "processing"
            and now - recipe.created_at > STALE_PROCESSING
            and recipe.id not in _active
        ):
            # The sweep runs while requests are served: re-read, and re-check _active with no
            # await before the update, so a job started meanwhile is never failed.
            current = await store.get_recipe(recipe.id)
            if current is None or current.status != "processing" or recipe.id in _active:
                continue
            await store.update_recipe(
                recipe.id, status="failed", error="interrupted by a restart; upload again"
            )


def _user_message(exc: Exception) -> str:
    """Fixed strings only: exception text may carry paths, keys or model output."""
    if isinstance(exc, IngestError):
        return str(exc)
    if ai.available():
        g = ai.get()
        if isinstance(exc, g.AITimeout):
            return "Gemini took too long to read the video; try again"
        if isinstance(exc, g.AIQuotaError):
            return "Gemini quota reached; try again in a few minutes"
        if isinstance(exc, g.AIInvalidOutput):
            return "Gemini returned an unusable recipe; try again"
        if isinstance(exc, g.AIError):
            return "Gemini could not process the video"
    if isinstance(exc, ApiError):
        return "storage error; try again"
    return "processing failed"


def _clamp_clip(
    start: float | None, end: float | None, duration: float
) -> tuple[float | None, float | None]:
    if start is None or end is None:
        return None, None
    start, end = max(0.0, start), min(duration, end)
    if end - start < MIN_CLIP_S:
        return None, None
    return start, min(end, start + MAX_CLIP_S)


async def _download_and_probe(store: Store, video_path: str, src: Path) -> ProbeResult:
    settings = get_settings()
    try:
        found = await store.download_to_file("videos", video_path, src, settings.max_video_bytes)
    except BlobTooLarge:
        raise IngestError(f"video larger than {settings.max_video_mb} MB") from None
    if not found:
        raise IngestError("uploaded video is missing")
    try:
        return await probe(src)
    except FfmpegError as exc:
        log.warning("probe failed: %s | %s", exc, exc.stderr)
        raise IngestError("not a readable MP4") from None


async def _extract_media(
    store: Store, recipe_id: str, step: Step, src: Path, workdir: Path
) -> None:
    """Still and clip for one step; failures are logged and leave the path None."""
    still = workdir / f"still-{step.idx}.jpg"
    try:
        await extract_still(src, step.timestamp_s, still)
        path = ref_image_path(recipe_id, step.idx)
        await store.put_blob("media", path, await asyncio.to_thread(still.read_bytes), "image/jpeg")
        step.ref_image_path = path
    except (FfmpegError, ApiError, OSError) as exc:
        log.warning("still for step %d of %s failed: %s", step.idx, recipe_id, _brief(exc))
    if step.clip_start_s is None or step.clip_end_s is None:
        return
    clip = workdir / f"clip-{step.idx}.mp4"
    try:
        await extract_clip(src, step.clip_start_s, step.clip_end_s, clip)
        path = clip_path(recipe_id, step.idx)
        await store.put_blob("media", path, await asyncio.to_thread(clip.read_bytes), "video/mp4")
        step.clip_path = path
    except (FfmpegError, ApiError, OSError) as exc:
        log.warning("clip for step %d of %s failed: %s", step.idx, recipe_id, _brief(exc))


def _brief(exc: Exception) -> str:
    stderr = exc.stderr if isinstance(exc, FfmpegError) else ""
    return f"{type(exc).__name__}: {exc} {stderr}".strip()


async def _discard(store: Store, recipe_id: str) -> None:
    """The recipe was deleted while the job ran: drop media it wrote after the purge."""
    try:
        await store.delete_prefix("media", recipe_id)
    except Exception:  # noqa: BLE001
        log.exception("could not clean media of deleted recipe %s", recipe_id)


async def _ingest(recipe_id: str, store: Store) -> None:
    recipe = await store.get_recipe(recipe_id)
    if recipe is None or recipe.status != "processing" or not recipe.video_path:
        return
    if not ffmpeg_available():
        raise IngestError("ffmpeg is not installed on the server")

    workdir = Path(await asyncio.to_thread(tempfile.mkdtemp, prefix="ghostchef-ingest-"))
    try:
        src = workdir / "src.mp4"
        info = await _download_and_probe(store, recipe.video_path, src)
        duration = info["duration_s"]
        marks = [m for m in recipe.step_marks_s if m <= duration]

        draft = await ai.get().extract_recipe(src, title_hint=recipe.title, step_marks_s=marks)
        if not draft.steps:
            raise IngestError("no steps found in the video")

        steps: list[Step] = []
        for spec in draft.steps:
            step = step_from_spec(recipe_id, spec.model_dump(mode="json"))
            step.timestamp_s = min(max(step.timestamp_s, 0.0), max(duration - 0.1, 0.0))
            step.clip_start_s, step.clip_end_s = _clamp_clip(
                step.clip_start_s, step.clip_end_s, duration
            )
            steps.append(step)

        if await store.get_recipe(recipe_id) is None:
            await _discard(store, recipe_id)
            return
        for step in steps:
            await _extract_media(store, recipe_id, step, src, workdir)

        if await store.get_recipe(recipe_id) is None:
            await _discard(store, recipe_id)
            return
        await store.replace_steps(recipe_id, steps)
        refcache.invalidate_recipe(recipe_id)
        await store.update_recipe(
            recipe_id, status="review", transcript=draft.transcript, error=None
        )
        log.info("ingestion of %s done: %d steps", recipe_id, len(steps))
        try:
            await videocache.put(recipe_id, src, info)
        except Exception:  # noqa: BLE001 - only a cache
            log.warning("could not cache the source video of %s", recipe_id)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


async def run_ingestion(recipe_id: str, *, store: Store) -> None:
    async with _semaphore():
        try:
            await _ingest(recipe_id, store)
        except Exception as exc:  # noqa: BLE001 - every failure must end as `failed`
            log.exception("ingestion of %s failed", recipe_id)
            try:
                if await store.get_recipe(recipe_id) is not None:
                    await store.update_recipe(recipe_id, status="failed", error=_user_message(exc))
                else:
                    await _discard(store, recipe_id)
            except Exception:  # noqa: BLE001
                log.exception("could not mark %s as failed", recipe_id)
