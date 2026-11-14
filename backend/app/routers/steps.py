from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app import refcache
from app.deps import get_store
from app.schemas import StepOut, StepPatch
from app.store.base import Store
from app.views import load_step, step_out

router = APIRouter(tags=["steps"])


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
    # A changed timestamp_s is stored; re-extracting the reference frame comes in BE-06.
    if fields:
        step = await store.update_step(step.id, **fields) or step
        refcache.invalidate_step(step.id)  # BE-06 re-extracts the still when timestamp_s changes
    return await step_out(store, step)
