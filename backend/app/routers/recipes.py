from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from app import metrics
from app.deps import get_store
from app.errors import ApiError
from app.jobs import ingest
from app.schemas import (
    ProcessStarted,
    RecipeCreate,
    RecipeCreated,
    RecipeDetail,
    RecipeList,
    RecipeListItem,
    RecipePatch,
)
from app.store.base import RECIPE_STATUSES, Recipe, Store, utcnow
from app.views import expire_stale_upload, load_recipe, recipe_detail

router = APIRouter(tags=["recipes"])

StoreDep = Annotated[Store, Depends(get_store)]


@router.post("/recipes", status_code=201, response_model=RecipeCreated)
async def create_recipe(body: RecipeCreate, store: StoreDep) -> RecipeCreated:
    recipe = Recipe(
        title=body.title,
        chef_name=body.chef_name,
        status="uploading",
        step_marks_s=list(body.step_marks_s),
        consent_at=utcnow(),
    )
    recipe.video_path = f"{recipe.id}/source.mp4"
    await store.create_recipe(recipe)
    up = await store.signed_upload("videos", recipe.video_path)
    return RecipeCreated(
        recipe_id=recipe.id,
        status=recipe.status,
        upload_url=up["upload_url"],
        upload_token=up["upload_token"],
        bucket="videos",
        object_path=recipe.video_path,
        resumable_endpoint=up["resumable_endpoint"],
        upload_expires_at=up["expires_at"],
    )


# Recipes with a /process call in progress. Checked and claimed with no await in between, so
# concurrent calls (retry + double tap) cannot both start a job.
_claimed: set[str] = set()


@router.post("/recipes/{recipe_id}/process", status_code=202, response_model=ProcessStarted)
async def process_recipe(recipe_id: str, store: StoreDep) -> ProcessStarted:
    recipe = await load_recipe(store, recipe_id)
    if recipe.id in _claimed:
        raise ApiError(409, "recipe_not_ready", "recipe is already being processed")
    _claimed.add(recipe.id)
    try:
        recipe = await load_recipe(store, recipe.id)  # re-read under the claim
        if recipe.status != "uploading":
            raise ApiError(409, "recipe_not_ready", f"recipe is {recipe.status}, not uploading")
        if not recipe.video_path or not await store.blob_exists("videos", recipe.video_path):
            raise ApiError(409, "upload_missing", "no video at the upload path yet")
        await store.update_recipe(recipe.id, status="processing", error=None)
        ingest.start(store, recipe.id)
    finally:
        _claimed.discard(recipe.id)
    return ProcessStarted(recipe_id=recipe.id, status="processing")


@router.get("/recipes", response_model=RecipeList)
async def list_recipes(
    store: StoreDep, status: Annotated[str | None, Query()] = None
) -> RecipeList:
    if status is not None and status not in RECIPE_STATUSES:
        raise ApiError(
            422, "validation_error", f"status must be one of {', '.join(RECIPE_STATUSES)}"
        )
    items = []
    for r in await store.list_recipes():
        r = await expire_stale_upload(store, r)
        if status is not None and r.status != status:
            continue
        items.append(
            RecipeListItem(
                id=r.id,
                title=r.title,
                chef_name=r.chef_name,
                status=r.status,
                step_count=len(await store.list_steps(r.id)),
                created_at=r.created_at,
            )
        )
    return RecipeList(recipes=items)


@router.get("/recipes/{recipe_id}", response_model=RecipeDetail)
async def get_recipe(recipe_id: str, store: StoreDep) -> RecipeDetail:
    return await recipe_detail(store, await load_recipe(store, recipe_id))


@router.patch("/recipes/{recipe_id}", response_model=RecipeDetail)
async def patch_recipe(recipe_id: str, body: RecipePatch, store: StoreDep) -> RecipeDetail:
    recipe = await load_recipe(store, recipe_id)
    fields = {k: getattr(body, k) for k in body.model_fields_set}
    if fields:
        recipe = await store.update_recipe(recipe.id, **fields) or recipe
    return await recipe_detail(store, recipe)


@router.post("/recipes/{recipe_id}/publish", response_model=RecipeDetail)
async def publish_recipe(recipe_id: str, store: StoreDep) -> RecipeDetail:
    recipe = await load_recipe(store, recipe_id)
    if recipe.status not in ("review", "published"):
        raise ApiError(409, "recipe_not_ready", f"recipe is {recipe.status}, not review")
    steps = await store.list_steps(recipe.id)
    if not steps:
        raise ApiError(409, "recipe_not_ready", "recipe has no steps")
    missing = [s.idx for s in steps if not s.ref_image_path]
    if missing:
        raise ApiError(409, "recipe_not_ready", f"steps without a reference image: {missing}")
    if recipe.status != "published":
        recipe = await store.update_recipe(recipe.id, status="published") or recipe
    return await recipe_detail(store, recipe)


@router.delete("/recipes/{recipe_id}", status_code=204)
async def delete_recipe(recipe_id: str, store: StoreDep) -> Response:
    recipe = await load_recipe(store, recipe_id)
    sessions = await store.list_sessions(recipe_id=recipe.id, limit=1_000_000)
    await store.delete_recipe(recipe.id)
    await asyncio.gather(
        store.delete_prefix("videos", recipe.id),
        store.delete_prefix("media", recipe.id),
        *(store.delete_prefix("frames", s.id) for s in sessions),
    )
    for s in sessions:
        metrics.drop(s.id)
    return Response(status_code=204)
