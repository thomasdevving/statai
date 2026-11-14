"""GET /live-token (API-CONTRACT §5, BE-05.1).

- The recipe must be `published` (else 409 recipe_not_ready).
- The Live **config** is cached per recipe, keyed by recipe id + a hash of everything that goes
  into it, so repeated calls do not rebuild it. The **token** is never cached (single use).
- At most one token per session_id every 3 s (429), so a client reconnect loop cannot burn quota.
- The token is never logged: only recipe id, model, locked and expiry.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from collections import OrderedDict
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request

from app import ai, faults
from app.config import Settings, get_settings
from app.deps import get_store
from app.errors import ApiError
from app.schemas import LiveConfigOut, LiveTokenOut
from app.store.base import Recipe, Step, Store
from app.views import load_recipe, load_session, step_spec

router = APIRouter(tags=["live"])
log = logging.getLogger("ghostchef.live")

API_VERSION = "v1beta"
GUARD_S = 3.0
CONFIG_CACHE_MAX = 32

# cache key -> LiveConfig (ghostchef_ai model)
_config_cache: OrderedDict[str, Any] = OrderedDict()
# session_id -> monotonic time of the last token minted (or attempted) for it
_last_mint: dict[str, float] = {}


def _config_key(recipe: Recipe, steps: list[Step], live_model: str) -> str:
    material = {
        "model": live_model,
        "title": recipe.title,
        "chef_name": recipe.chef_name,
        "transcript": recipe.transcript or "",
        "steps": [step_spec(s).model_dump(mode="json") for s in steps],
    }
    digest = hashlib.sha256(
        json.dumps(material, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    return f"{recipe.id}:{digest}"


def _live_config(recipe: Recipe, steps: list[Step]) -> Any:
    g = ai.get()
    key = _config_key(recipe, steps, g.model_ids().get("live", ""))
    config = _config_cache.get(key)
    if config is not None:
        _config_cache.move_to_end(key)
        return config
    config = g.build_live_config(
        recipe.title, recipe.chef_name, recipe.transcript or "", [step_spec(s) for s in steps]
    )
    # One entry per recipe: a changed recipe replaces its old config instead of piling up.
    for k in [k for k in _config_cache if k.startswith(f"{recipe.id}:")]:
        del _config_cache[k]
    _config_cache[key] = config
    while len(_config_cache) > CONFIG_CACHE_MAX:
        _config_cache.popitem(last=False)
    return config


def _claim_guard(session_id: str) -> float:
    now = time.monotonic()
    last = _last_mint.get(session_id)
    if last is not None and now - last < GUARD_S:
        raise ApiError(
            429, "quota_exhausted", "one live token per session every 3 s", retryable=True
        )
    # Keep the table small: entries older than the window carry no information.
    if len(_last_mint) > 256:
        for sid in [s for s, t in _last_mint.items() if now - t >= GUARD_S]:
            del _last_mint[sid]
    _last_mint[session_id] = now
    return now


def evict_recipe(recipe_id: str, session_ids: list[str]) -> None:
    """A deleted recipe: drop its cached config and its sessions' guard entries."""
    for k in [k for k in _config_cache if k.startswith(f"{recipe_id}:")]:
        del _config_cache[k]
    for sid in session_ids:
        _last_mint.pop(sid, None)


def reset() -> None:
    """Tests and store resets: forget cached configs and the per-session guard."""
    _config_cache.clear()
    _last_mint.clear()


@router.get("/live-token", response_model=LiveTokenOut)
async def live_token(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    store: Annotated[Store, Depends(get_store)],
    recipe_id: Annotated[str, Query()],
    session_id: Annotated[str | None, Query()] = None,
) -> LiveTokenOut:
    recipe = await load_recipe(store, recipe_id)
    session = await load_session(store, session_id) if session_id else None
    if recipe.status != "published":
        raise ApiError(409, "recipe_not_ready", f"recipe is {recipe.status}, not published")
    steps = await store.list_steps(recipe.id)
    config = _live_config(recipe, steps)
    stamp = 0.0
    if session is not None:
        stamp = _claim_guard(session.id)
    try:
        faults.raise_if_injected(request, settings, ai.get())
        token = await ai.get().mint_live_token(config)
    except BaseException:
        # A failed mint (Gemini error, timeout) does not hold the window: the client's
        # retry after 1 s gets a real attempt rather than a 429.
        if session is not None and _last_mint.get(session.id) == stamp:
            del _last_mint[session.id]
        raise
    log.info(
        "live_token",
        extra={
            "fields": {
                "recipe_id": recipe.id,
                "model": config.model,
                "locked": token.locked,
                "expires_at": token.expires_at.isoformat(),
            }
        },
    )
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
