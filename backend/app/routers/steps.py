from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends

from app import refcache
from app.deps import get_store
from app.errors import ApiError, not_found
from app.media import videocache
from app.media.ffmpeg import FfmpegError, extract_still
from app.schemas import StepOut, StepPatch
from app.seed import ref_image_path
from app.store.base import BlobTooLarge, Store
from app.views import load_recipe, load_step, step_out

log = logging.getLogger("ghostchef.steps")

router = APIRouter(tags=["steps"])


async def _reextract_still(
    store: Store, recipe_id: str, idx: int, at_s: float
) -> tuple[str, float]:
    """New reference still for a step from the (cached) source video.

    Returns (media path, timestamp actually used). Nothing is written to Storage unless the
    extraction succeeded.
    """
    recipe = await load_recipe(store, recipe_id)
    try:
        cached = await videocache.get_or_download(store, recipe)
    except BlobTooLarge:
        raise ApiError(409, "recipe_not_ready", "source video is too large") from None
    except FfmpegError:
        raise ApiError(409, "recipe_not_ready", "source video is not readable") from None
    if cached is None:
        raise ApiError(409, "recipe_not_ready", "source video is gone")
    video, info = cached
    duration = info["duration_s"]
    if at_s > duration:
        raise ApiError(
            422, "validation_error", f"timestamp_s is past the end of the video ({duration:.1f} s)"
        )
    at_s = min(at_s, max(duration - 0.1, 0.0))

    workdir = Path(await asyncio.to_thread(tempfile.mkdtemp, prefix="ghostchef-still-"))
    try:
        out = workdir / "ref.jpg"
        try:
            await extract_still(video, at_s, out)
        except FfmpegError as exc:
            log.warning("re-extraction failed: %s | %s", exc, exc.stderr)
            raise ApiError(500, "internal", "could not extract a frame") from None
        data = await asyncio.to_thread(out.read_bytes)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    path = ref_image_path(recipe_id, idx)
    await store.put_blob("media", path, data, "image/jpeg")
    return path, at_s


async def _drop_orphan(store: Store, recipe_id: str, path: str) -> None:
    try:
        if await store.get_recipe(recipe_id) is None:
            await store.delete_prefix("media", recipe_id)
        else:
            await store.delete_blob("media", path)
    except Exception:  # noqa: BLE001 - best effort; the 404 is what matters
        log.exception("could not remove orphaned still for recipe %s", recipe_id)


@router.patch("/steps/{step_id}", response_model=StepOut)
async def patch_step(
    step_id: str, body: StepPatch, store: Annotated[Store, Depends(get_store)]
) -> StepOut:
    step = await load_step(store, step_id)
    fields = {}
    for name in body.model_fields_set:
        value = getattr(body, name)
        if name == "watch_fors":
            value = [w.model_dump() for w in value]
        fields[name] = value
    new_ts = fields.get("timestamp_s")
    if new_ts is not None and new_ts != step.timestamp_s:
        recipe = await load_recipe(store, step.recipe_id)
        if recipe.video_path is None:
            log.info("step %s: no source video; timestamp_s stored without a new still", step.id)
        else:
            fields["ref_image_path"], fields["timestamp_s"] = await _reextract_still(
                store, recipe.id, step.idx, new_ts
            )
    if fields:
        updated = await store.update_step(step.id, **fields)
        # The recipe may have been deleted meanwhile; a still written after the purge is an orphan.
        if updated is None or await store.get_step(step.id) is None:
            if "ref_image_path" in fields:
                await _drop_orphan(store, step.recipe_id, fields["ref_image_path"])
            raise not_found("step")
        step = updated
        refcache.invalidate_step(step.id)
    return await step_out(store, step)
