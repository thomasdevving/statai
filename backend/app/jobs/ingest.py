"""Background ingestion job: uploaded video → ghostchef_ai.extract_recipe → steps → `review`.

BE-01 version: no ffmpeg. Each step's reference image is the fixture image with the same idx,
if one exists. BE-06 replaces that with frames extracted from the video.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from app import ai
from app.config import get_settings
from app.seed import ref_image_path, step_from_spec
from app.store.base import Store
from app.store.memory import MemoryStore

log = logging.getLogger("ghostchef.ingest")

_tasks: set[asyncio.Task[None]] = set()


def start(store: Store, recipe_id: str) -> asyncio.Task[None]:
    task = asyncio.create_task(run(store, recipe_id), name=f"ingest-{recipe_id}")
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return task


async def wait_all() -> None:
    """Tests and shutdown: wait for every running job."""
    while _tasks:
        await asyncio.gather(*list(_tasks), return_exceptions=True)


async def cancel_all() -> None:
    """Shutdown: stop running jobs. Their recipes stay `processing` (memory is gone anyway)."""
    for task in list(_tasks):
        task.cancel()
    await asyncio.gather(*list(_tasks), return_exceptions=True)


async def _fail(store: Store, recipe_id: str, error: str) -> None:
    await store.update_recipe(recipe_id, status="failed", error=error)


def _local_video_path(store: Store, video_path: str) -> Path:
    if isinstance(store, MemoryStore):
        return store.blob_file("videos", video_path)
    raise NotImplementedError("downloading the video from Supabase comes in BE-06")


async def run(store: Store, recipe_id: str) -> None:
    try:
        recipe = await store.get_recipe(recipe_id)
        if recipe is None or recipe.video_path is None:
            return
        path = _local_video_path(store, recipe.video_path)
        size = await asyncio.to_thread(lambda: path.stat().st_size)
        settings = get_settings()
        if size > settings.max_video_bytes:
            await _fail(store, recipe_id, f"video is larger than {settings.max_video_mb} MB")
            return

        g = ai.get()
        draft = await g.extract_recipe(
            path, title_hint=recipe.title, step_marks_s=list(recipe.step_marks_s)
        )

        from ghostchef_ai import config as ai_config

        images = ai_config.fixture_dir() / "images"
        steps = []
        for spec in draft.steps:
            step = step_from_spec(recipe_id, spec.model_dump(mode="json"))
            image = images / f"step-{spec.idx}.jpg"
            if image.is_file():
                rel = ref_image_path(recipe_id, spec.idx)
                await store.put_blob("media", rel, image.read_bytes(), "image/jpeg")
                step.ref_image_path = rel
            steps.append(step)

        if await store.get_recipe(recipe_id) is None:  # deleted while we worked
            await store.delete_prefix("media", recipe_id)
            return
        await store.replace_steps(recipe_id, steps)
        await store.update_recipe(
            recipe_id, status="review", transcript=draft.transcript, error=None
        )
        log.info("ingestion of %s done: %d steps", recipe_id, len(steps))
    except Exception as exc:  # noqa: BLE001 - every failure must end as `failed`
        log.exception("ingestion of %s failed", recipe_id)
        message = str(exc) if ai.available() and isinstance(exc, ai.get().AIError) else ""
        try:
            if await store.get_recipe(recipe_id) is not None:
                await _fail(store, recipe_id, message or "processing failed")
        except Exception:  # noqa: BLE001
            log.exception("could not mark %s as failed", recipe_id)
