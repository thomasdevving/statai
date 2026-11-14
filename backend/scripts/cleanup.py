#!/usr/bin/env python3
"""Data hygiene (BE-07.5): old sessions with their frames, and failed recipes.

    python scripts/cleanup.py [--hours 6] [--yes]

Dry run by default: prints what it would delete. With --yes it deletes
  - sessions started more than --hours ago, with their events and their frames/<session>/ blobs,
  - recipes with status `failed` (blobs first, via purge_recipe).
The seeded demo recipe (and its steps and media) is never touched; its OLD SESSIONS are cleaned
like any other, which is what empties the monitor's session list.

STORAGE=supabase works on the real rows and buckets (use the service key in backend/.env).
STORAGE=memory: rows live only inside the running server process, which this script cannot reach,
so it can only remove frame folders under DATA_DIR/frames whose newest file is older than --hours.
Never prints keys or signed URLs.
"""

from __future__ import annotations

import argparse
import asyncio
import shutil
import sys
import time
from datetime import timedelta
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.config import get_settings  # noqa: E402
from app.deps import get_store  # noqa: E402
from app.errors import ApiError  # noqa: E402
from app.seed import SEED_RECIPE_ID  # noqa: E402
from app.store.base import Recipe, Session, Store, utcnow  # noqa: E402
from app.store.memory import MemoryStore  # noqa: E402
from app.store.ops import purge_recipe  # noqa: E402


async def old_sessions(store: Store, hours: float) -> list[Session]:
    cutoff = utcnow() - timedelta(hours=hours)
    return await store.list_sessions(limit=1_000_000, started_before=cutoff)


async def failed_recipes(store: Store) -> list[Recipe]:
    return [r for r in await store.list_recipes(status="failed") if r.id != SEED_RECIPE_ID]


def stale_frame_dirs(store: MemoryStore, hours: float) -> list[Path]:
    """frames/<session>/ folders whose newest file (or the folder itself) is older than hours."""
    root = store.data_dir / "frames"
    if not root.is_dir():
        return []
    cutoff = time.time() - hours * 3600
    out = []
    for d in sorted(p for p in root.iterdir() if p.is_dir() and not p.is_symlink()):
        newest = max([d.stat().st_mtime, *(f.stat().st_mtime for f in d.iterdir())])
        if newest < cutoff:
            out.append(d)
    return out


async def delete_session_fully(store: Store, session: Session) -> None:
    """Frames first, then rows: a failed Storage call leaves the rows to retry."""
    await store.delete_prefix("frames", session.id)
    await store.delete_session(session.id)


async def run(hours: float, yes: bool) -> int:
    settings = get_settings()
    store = get_store()
    mode = "DELETE" if yes else "dry run"
    print(f"storage: {settings.storage}   older than: {hours:g} h   mode: {mode}")

    if isinstance(store, MemoryStore):
        print(
            "note: memory mode. Sessions and recipes live only inside the running server, so\n"
            "      this script cannot list or delete them (restarting the server clears them).\n"
            f"      It cleans only leftover frame folders under {store.data_dir / 'frames'}."
        )
        dirs = stale_frame_dirs(store, hours)
        print(f"frame folders to delete: {len(dirs)}")
        for d in dirs:
            print(f"  frames/{d.name}")
        if yes:
            for d in dirs:
                await asyncio.to_thread(shutil.rmtree, d, True)
            print(f"deleted {len(dirs)} frame folder(s)")
        return 0

    sessions = await old_sessions(store, hours)
    failed = await failed_recipes(store)
    print(f"sessions to delete: {len(sessions)}")
    for s in sessions[:50]:
        print(f"  session {s.id}  started {s.started_at:%Y-%m-%d %H:%M}Z  recipe {s.recipe_id}")
    if len(sessions) > 50:
        print(f"  ... and {len(sessions) - 50} more")
    print(f"failed recipes to delete: {len(failed)}")
    for r in failed:
        print(f"  recipe {r.id}  {r.title!r}  created {r.created_at:%Y-%m-%d %H:%M}Z")
    print(f"protected: seeded recipe {SEED_RECIPE_ID} is never deleted")

    if not yes:
        print("dry run: nothing deleted. Pass --yes to delete.")
        return 0

    done_sessions = 0
    for s in sessions:
        await delete_session_fully(store, s)
        done_sessions += 1
    done_recipes = 0
    for r in failed:
        if r.id == SEED_RECIPE_ID:
            continue
        if await purge_recipe(store, r.id) is not None:
            done_recipes += 1
    print(f"deleted {done_sessions} session(s) and {done_recipes} failed recipe(s)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--hours", type=float, default=6.0, help="session age limit (default 6)")
    ap.add_argument("--yes", action="store_true", help="actually delete (default: dry run)")
    args = ap.parse_args()
    if args.hours < 0:
        print("--hours must be >= 0", file=sys.stderr)
        return 2
    try:
        return asyncio.run(run(args.hours, args.yes))
    except ApiError as exc:
        print(f"failed: {exc.code}: {exc.message} (see log above)", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(f"failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
