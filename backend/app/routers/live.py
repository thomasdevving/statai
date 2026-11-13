"""GET /live-token (API-CONTRACT §5)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app import ai
from app.deps import get_store
from app.schemas import LiveConfigOut, LiveTokenOut
from app.store.base import Store
from app.views import load_recipe, load_session, step_spec

router = APIRouter(tags=["live"])

API_VERSION = "v1beta"


@router.get("/live-token", response_model=LiveTokenOut)
async def live_token(
    store: Annotated[Store, Depends(get_store)],
    recipe_id: Annotated[str, Query()],
    session_id: Annotated[str | None, Query()] = None,
) -> LiveTokenOut:
    recipe = await load_recipe(store, recipe_id)
    if session_id:
        await load_session(store, session_id)
    steps = await store.list_steps(recipe.id)
    g = ai.get()
    config = g.build_live_config(
        recipe.title, recipe.chef_name, recipe.transcript or "", [step_spec(s) for s in steps]
    )
    token = await g.mint_live_token(config)
    return LiveTokenOut(
        token=token.token,
        expires_at=token.expires_at,
        new_session_expires_at=token.new_session_expires_at,
        model=config.model,
        api_version=API_VERSION,
        locked=token.locked,
        config=LiveConfigOut(
            system_instruction=config.system_instruction,
            response_modalities=list(config.response_modalities),
            voice=config.voice,
            tools=list(config.tools),
            session_resumption=config.session_resumption,
        ),
    )
