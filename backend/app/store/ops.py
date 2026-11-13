"""Store operations shared by routes and scripts, written once against the Store protocol."""

from __future__ import annotations

import asyncio

from app.store.base import Session, Store


async def purge_recipe(store: Store, recipe_id: str) -> list[Session] | None:
    """Deletes a recipe's blobs (videos/<id>/, media/<id>/, frames/<session>/), then its rows.

    Blobs go first: if a Storage call fails, the rows are still there and the DELETE can be
    retried, instead of leaving unreachable blobs behind. Returns the deleted sessions (callers
    drop their in-process state), or None when the recipe did not exist.
    """
    if await store.get_recipe(recipe_id) is None:
        return None
    sessions = await store.list_sessions(recipe_id=recipe_id, limit=1_000_000)
    await asyncio.gather(
        store.delete_prefix("videos", recipe_id),
        store.delete_prefix("media", recipe_id),
        *(store.delete_prefix("frames", s.id) for s in sessions),
    )
    if not await store.delete_recipe(recipe_id):
        return None
    return sessions
