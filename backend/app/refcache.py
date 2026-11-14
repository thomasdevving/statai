"""In-process LRU cache of reference stills for /check (BE-03.3).

Keyed by (step_id, ref_image_path). Entries are dropped when a step is patched, when a recipe's
steps are replaced (seed, ingestion) or deleted. A TTL bounds staleness when another process
(scripts/seed.py against Supabase) rewrites an image at the same path.
"""

from __future__ import annotations

import time
from collections import OrderedDict

from app.store.base import Step, Store

MAX_ENTRIES = 64
TTL_S = 300.0

# (step_id, path) -> (recipe_id, bytes, loaded_at monotonic)
_cache: OrderedDict[tuple[str, str], tuple[str, bytes, float]] = OrderedDict()


async def get_ref_image(store: Store, step: Step) -> bytes | None:
    """The step's reference still, or None when it has none (check_frame accepts None)."""
    if not step.ref_image_path:
        return None
    key = (step.id, step.ref_image_path)
    hit = _cache.get(key)
    now = time.monotonic()
    if hit is not None and now - hit[2] < TTL_S:
        _cache.move_to_end(key)
        return hit[1]
    data = await store.get_blob("media", step.ref_image_path)
    if data is None:
        _cache.pop(key, None)
        return None
    _cache[key] = (step.recipe_id, data, now)
    _cache.move_to_end(key)
    while len(_cache) > MAX_ENTRIES:
        _cache.popitem(last=False)
    return data


def invalidate_step(step_id: str) -> None:
    for key in [k for k in _cache if k[0] == step_id]:
        del _cache[key]


def invalidate_recipe(recipe_id: str) -> None:
    for key in [k for k, v in _cache.items() if v[0] == recipe_id]:
        del _cache[key]


def clear() -> None:
    _cache.clear()
