"""Shared helpers: id parsing, loading-or-404, record → response conversion."""

from __future__ import annotations

import uuid
from datetime import timedelta

from app.config import get_settings
from app.errors import ApiError, not_found
from app.schemas import EventOut, RecipeDetail, StepOut
from app.store.base import Event, Recipe, Session, Step, Store, utcnow

UPLOAD_NEVER_COMPLETED = timedelta(hours=2)


def parse_uuid(value: str, name: str) -> str:
    try:
        return str(uuid.UUID(value))
    except (ValueError, AttributeError, TypeError):
        raise ApiError(422, "validation_error", f"{name} must be a UUID") from None


async def expire_stale_upload(store: Store, recipe: Recipe) -> Recipe:
    """API-CONTRACT §2: a recipe left in `uploading` for more than 2 h becomes `failed`."""
    if recipe.status == "uploading" and utcnow() - recipe.created_at > UPLOAD_NEVER_COMPLETED:
        updated = await store.update_recipe(
            recipe.id, status="failed", error="upload never completed"
        )
        return updated or recipe
    return recipe


async def load_recipe(store: Store, recipe_id: str) -> Recipe:
    recipe = await store.get_recipe(parse_uuid(recipe_id, "recipe_id"))
    if recipe is None:
        raise not_found("recipe")
    return await expire_stale_upload(store, recipe)


async def load_step(store: Store, step_id: str) -> Step:
    step = await store.get_step(parse_uuid(step_id, "step_id"))
    if step is None:
        raise not_found("step")
    return step


async def load_session(store: Store, session_id: str) -> Session:
    session = await store.get_session(parse_uuid(session_id, "session_id"))
    if session is None:
        raise not_found("session")
    return session


async def step_out(store: Store, step: Step) -> StepOut:
    ttl = get_settings().signed_url_ttl_s
    ref = await store.signed_url("media", step.ref_image_path, ttl) if step.ref_image_path else None
    clip = await store.signed_url("media", step.clip_path, ttl) if step.clip_path else None
    return StepOut(
        id=step.id,
        recipe_id=step.recipe_id,
        idx=step.idx,
        title=step.title,
        key_line=step.key_line,
        instruction=step.instruction,
        chef_quote=step.chef_quote,
        timestamp_s=step.timestamp_s,
        clip_start_s=step.clip_start_s,
        clip_end_s=step.clip_end_s,
        success_criteria=list(step.success_criteria),
        watch_fors=[dict(w) for w in step.watch_fors],
        ref_image_url=ref,
        clip_url=clip,
        timer_s=step.timer_s,
    )


async def recipe_detail(store: Store, recipe: Recipe) -> RecipeDetail:
    steps = await store.list_steps(recipe.id)
    video_url = None
    if recipe.status == "review" and recipe.video_path:
        video_url = await store.signed_url(
            "videos", recipe.video_path, get_settings().signed_url_ttl_s
        )
    return RecipeDetail(
        id=recipe.id,
        title=recipe.title,
        chef_name=recipe.chef_name,
        status=recipe.status,
        error=recipe.error,
        video_url=video_url,
        step_marks_s=list(recipe.step_marks_s),
        transcript=recipe.transcript,
        created_at=recipe.created_at,
        steps=[await step_out(store, s) for s in steps],
    )


def event_out(e: Event) -> EventOut:
    return EventOut(
        id=e.id,
        kind=e.kind,
        step_id=e.step_id,
        request_id=e.request_id,
        payload=e.payload,
        created_at=e.created_at,
    )


def step_spec(step: Step):  # -> ghostchef_ai.StepSpec
    from app import ai

    return ai.get().StepSpec.model_validate(
        {
            "idx": step.idx,
            "title": step.title,
            "key_line": step.key_line,
            "instruction": step.instruction,
            "chef_quote": step.chef_quote,
            "timestamp_s": step.timestamp_s,
            "clip_start_s": step.clip_start_s,
            "clip_end_s": step.clip_end_s,
            "success_criteria": list(step.success_criteria),
            "watch_fors": [dict(w) for w in step.watch_fors],
            "timer_s": step.timer_s,
        }
    )
