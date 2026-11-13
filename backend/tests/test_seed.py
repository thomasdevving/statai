from __future__ import annotations

import asyncio

from app.deps import get_store
from app.seed import SEED_RECIPE_ID, seed_step_id

from .conftest import requires_ai


def test_seed_ids_are_deterministic():
    assert seed_step_id(SEED_RECIPE_ID, 3) == seed_step_id(SEED_RECIPE_ID, 3)
    assert seed_step_id(SEED_RECIPE_ID, 3) != seed_step_id(SEED_RECIPE_ID, 4)


@requires_ai
def test_startup_seeds_fixture_recipe(client):
    store = get_store()
    recipe = asyncio.run(store.get_recipe(SEED_RECIPE_ID))
    assert recipe is not None and recipe.status == "published"
    steps = asyncio.run(store.list_steps(SEED_RECIPE_ID))
    assert [s.idx for s in steps] == list(range(1, len(steps) + 1))
    assert steps[2].id == seed_step_id(SEED_RECIPE_ID, 3)
    assert any(w["id"] == "rice_too_thick" for w in steps[2].watch_fors)
    for s in steps:
        assert s.ref_image_path == f"{SEED_RECIPE_ID}/steps/{s.idx}/ref.jpg"
        assert asyncio.run(store.blob_exists("media", s.ref_image_path))
