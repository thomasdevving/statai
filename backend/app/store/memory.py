"""MemoryStore: dict-backed rows, blobs as files under DATA_DIR/<bucket>/<path>.

Used for tests, for the first hours of the hackathon, and as the emergency fallback.
"""

from __future__ import annotations

import asyncio
import copy
import hmac
import secrets
import shutil
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote

from app.request_ctx import request_base_url
from app.store.base import Event, Recipe, Session, SignedUpload, Step, utcnow
from app.store.paths import BadPath, check_blob_path, check_prefix

UPLOAD_TTL = timedelta(hours=2)


class MemoryStore:
    def __init__(self, data_dir: Path, public_base_url: str | None = None) -> None:
        self.data_dir = data_dir.resolve()
        self.public_base_url = public_base_url.rstrip("/") if public_base_url else None
        self._recipes: dict[str, Recipe] = {}
        self._steps: dict[str, Step] = {}
        self._sessions: dict[str, Session] = {}
        self._events: dict[str, list[Event]] = {}
        # token -> (bucket, path, expires_at); single use
        self._upload_tokens: dict[str, tuple[str, str, datetime]] = {}

    # ------------------------------------------------------------------ recipes
    async def list_recipes(self, status: str | None = None) -> list[Recipe]:
        rows = [r for r in self._recipes.values() if status is None or r.status == status]
        rows.sort(key=lambda r: r.created_at, reverse=True)
        return [copy.deepcopy(r) for r in rows]

    async def get_recipe(self, recipe_id: str) -> Recipe | None:
        r = self._recipes.get(recipe_id)
        return copy.deepcopy(r) if r else None

    async def create_recipe(self, recipe: Recipe) -> Recipe:
        self._recipes[recipe.id] = copy.deepcopy(recipe)
        return copy.deepcopy(recipe)

    async def update_recipe(self, recipe_id: str, **fields: Any) -> Recipe | None:
        r = self._recipes.get(recipe_id)
        if r is None:
            return None
        self._recipes[recipe_id] = replace(r, **copy.deepcopy(fields))
        return copy.deepcopy(self._recipes[recipe_id])

    async def delete_recipe(self, recipe_id: str) -> bool:
        if self._recipes.pop(recipe_id, None) is None:
            return False
        for sid in [s.id for s in self._steps.values() if s.recipe_id == recipe_id]:
            del self._steps[sid]
        for sess_id in [s.id for s in self._sessions.values() if s.recipe_id == recipe_id]:
            del self._sessions[sess_id]
            self._events.pop(sess_id, None)
        return True

    # ------------------------------------------------------------------ steps
    async def get_step(self, step_id: str) -> Step | None:
        s = self._steps.get(step_id)
        return copy.deepcopy(s) if s else None

    async def list_steps(self, recipe_id: str) -> list[Step]:
        rows = sorted(
            (s for s in self._steps.values() if s.recipe_id == recipe_id), key=lambda s: s.idx
        )
        return [copy.deepcopy(s) for s in rows]

    async def replace_steps(self, recipe_id: str, steps: list[Step]) -> list[Step]:
        idxs = [s.idx for s in steps]
        if len(set(idxs)) != len(idxs):
            raise ValueError("duplicate step idx")
        for sid in [s.id for s in self._steps.values() if s.recipe_id == recipe_id]:
            del self._steps[sid]
        for s in steps:
            stored = replace(copy.deepcopy(s), recipe_id=recipe_id)
            self._steps[stored.id] = stored
        # Mirror "session_events.step_id ... on delete set null".
        live_ids = set(self._steps)
        for events in self._events.values():
            for e in events:
                if e.step_id and e.step_id not in live_ids:
                    e.step_id = None
        return await self.list_steps(recipe_id)

    async def update_step(self, step_id: str, **fields: Any) -> Step | None:
        s = self._steps.get(step_id)
        if s is None:
            return None
        self._steps[step_id] = replace(s, **copy.deepcopy(fields))
        return copy.deepcopy(self._steps[step_id])

    # ------------------------------------------------------------------ sessions
    async def create_session(self, session: Session) -> Session:
        self._sessions[session.id] = copy.deepcopy(session)
        self._events.setdefault(session.id, [])
        return copy.deepcopy(session)

    async def get_session(self, session_id: str) -> Session | None:
        s = self._sessions.get(session_id)
        return copy.deepcopy(s) if s else None

    async def update_session(self, session_id: str, **fields: Any) -> Session | None:
        s = self._sessions.get(session_id)
        if s is None:
            return None
        self._sessions[session_id] = replace(s, **copy.deepcopy(fields))
        return copy.deepcopy(self._sessions[session_id])

    async def list_sessions(
        self, *, active: bool | None = None, limit: int = 20, recipe_id: str | None = None
    ) -> list[Session]:
        rows = list(self._sessions.values())
        if active is True:
            rows = [s for s in rows if s.finished_at is None]
        elif active is False:
            rows = [s for s in rows if s.finished_at is not None]
        if recipe_id is not None:
            rows = [s for s in rows if s.recipe_id == recipe_id]
        rows.sort(key=lambda s: s.started_at, reverse=True)
        return [copy.deepcopy(s) for s in rows[: max(limit, 0)]]

    async def append_event(self, event: Event) -> Event:
        if event.session_id not in self._sessions:
            raise KeyError(event.session_id)
        self._events.setdefault(event.session_id, []).append(copy.deepcopy(event))
        return copy.deepcopy(event)

    async def list_events(self, session_id: str) -> list[Event]:
        return [copy.deepcopy(e) for e in self._events.get(session_id, [])]

    # ------------------------------------------------------------------ blobs
    def blob_file(self, bucket: str, path: str) -> Path:
        """Absolute file path for a blob. Raises BadPath for anything outside DATA_DIR."""
        bucket, path = check_blob_path(bucket, path)
        target = (self.data_dir / bucket / path).resolve()
        if not target.is_relative_to(self.data_dir / bucket):
            raise BadPath("bad path")
        return target

    async def put_blob(self, bucket: str, path: str, data: bytes, content_type: str) -> None:
        target = self.blob_file(bucket, path)

        def _write() -> None:
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_name(target.name + ".part")
            tmp.write_bytes(data)
            tmp.replace(target)

        await asyncio.to_thread(_write)

    async def get_blob(self, bucket: str, path: str) -> bytes | None:
        target = self.blob_file(bucket, path)

        def _read() -> bytes | None:
            return target.read_bytes() if target.is_file() else None

        return await asyncio.to_thread(_read)

    async def delete_blob(self, bucket: str, path: str) -> None:
        target = self.blob_file(bucket, path)
        await asyncio.to_thread(lambda: target.unlink(missing_ok=True))

    async def delete_prefix(self, bucket: str, prefix: str) -> None:
        bucket, prefix = check_prefix(bucket, prefix)
        target = self.blob_file(bucket, prefix)
        await asyncio.to_thread(shutil.rmtree, target, True)

    async def blob_exists(self, bucket: str, path: str) -> bool:
        target = self.blob_file(bucket, path)
        return await asyncio.to_thread(target.is_file)

    def _base(self) -> str:
        return self.public_base_url or (request_base_url.get() or "http://localhost:8000")

    async def signed_url(self, bucket: str, path: str, ttl_s: int) -> str:
        check_blob_path(bucket, path)
        # Memory mode serves files unauthenticated from /local-files; ttl is not enforced.
        return f"{self._base()}/local-files/{bucket}/{quote(path)}"

    async def signed_upload(self, bucket: str, path: str) -> SignedUpload:
        check_blob_path(bucket, path)
        token = secrets.token_urlsafe(32)
        expires_at = utcnow() + UPLOAD_TTL
        self._upload_tokens[token] = (bucket, path, expires_at)
        return {
            "upload_url": f"{self._base()}/local-upload/{bucket}/{quote(path)}?token={token}",
            "upload_token": token,
            "resumable_endpoint": None,
            "expires_at": expires_at,
        }

    def consume_upload_token(self, bucket: str, path: str, token: str) -> bool:
        """Single use, constant-time compare. True when the token matches bucket/path."""
        match: str | None = None
        given = token.encode()
        for known in list(self._upload_tokens):
            if hmac.compare_digest(known.encode(), given):
                match = known
        if match is None:
            return False
        t_bucket, t_path, expires_at = self._upload_tokens[match]
        if t_bucket != bucket or t_path != path or utcnow() > expires_at:
            return False
        del self._upload_tokens[match]
        return True
