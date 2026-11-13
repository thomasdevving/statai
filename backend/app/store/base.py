"""Store protocol and record types, mirroring API-CONTRACT §6.

Routers talk only to this protocol, so BE-02 can swap MemoryStore for SupabaseStore without
touching them.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal, Protocol, TypedDict

RecipeStatus = Literal["uploading", "processing", "review", "published", "failed"]
RECIPE_STATUSES: tuple[str, ...] = ("uploading", "processing", "review", "published", "failed")
BUCKETS: tuple[str, ...] = ("videos", "media", "frames")


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid.uuid4())


@dataclass
class Recipe:
    title: str
    status: RecipeStatus
    id: str = field(default_factory=new_id)
    chef_name: str | None = None
    video_path: str | None = None
    transcript: str | None = None
    step_marks_s: list[float] = field(default_factory=list)
    error: str | None = None
    consent_at: datetime | None = None
    created_at: datetime = field(default_factory=utcnow)


@dataclass
class Step:
    recipe_id: str
    idx: int
    title: str
    key_line: str
    instruction: str
    timestamp_s: float
    id: str = field(default_factory=new_id)
    chef_quote: str | None = None
    clip_start_s: float | None = None
    clip_end_s: float | None = None
    success_criteria: list[str] = field(default_factory=list)
    watch_fors: list[dict[str, Any]] = field(default_factory=list)
    ref_image_path: str | None = None  # bucket "media"
    clip_path: str | None = None  # bucket "media"
    timer_s: int | None = None


@dataclass
class Session:
    recipe_id: str
    client: str
    id: str = field(default_factory=new_id)
    device_label: str | None = None
    started_at: datetime = field(default_factory=utcnow)
    finished_at: datetime | None = None


@dataclass
class Event:
    session_id: str
    kind: str
    id: str = field(default_factory=new_id)
    step_id: str | None = None
    request_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utcnow)


class SignedUpload(TypedDict):
    upload_url: str
    upload_token: str
    resumable_endpoint: str | None
    expires_at: datetime


class Store(Protocol):
    # recipes
    async def list_recipes(self, status: str | None = None) -> list[Recipe]: ...
    async def get_recipe(self, recipe_id: str) -> Recipe | None: ...
    async def create_recipe(self, recipe: Recipe) -> Recipe: ...
    async def update_recipe(self, recipe_id: str, **fields: Any) -> Recipe | None: ...
    async def delete_recipe(self, recipe_id: str) -> bool:
        """Deletes the recipe, its steps, its sessions and their events (rows only)."""
        ...

    # steps
    async def get_step(self, step_id: str) -> Step | None: ...
    async def list_steps(self, recipe_id: str) -> list[Step]:
        """Ordered by idx."""
        ...

    async def replace_steps(self, recipe_id: str, steps: list[Step]) -> list[Step]: ...
    async def update_step(self, step_id: str, **fields: Any) -> Step | None: ...

    # sessions and events
    async def create_session(self, session: Session) -> Session: ...
    async def get_session(self, session_id: str) -> Session | None: ...
    async def update_session(self, session_id: str, **fields: Any) -> Session | None: ...
    async def list_sessions(
        self, *, active: bool | None = None, limit: int = 20, recipe_id: str | None = None
    ) -> list[Session]:
        """Most recent first."""
        ...

    async def append_event(self, event: Event) -> Event: ...
    async def list_events(self, session_id: str) -> list[Event]:
        """Oldest first."""
        ...

    # blobs
    async def put_blob(self, bucket: str, path: str, data: bytes, content_type: str) -> None: ...
    async def get_blob(self, bucket: str, path: str) -> bytes | None: ...
    async def delete_blob(self, bucket: str, path: str) -> None: ...
    async def delete_prefix(self, bucket: str, prefix: str) -> None: ...
    async def blob_exists(self, bucket: str, path: str) -> bool: ...
    async def signed_url(self, bucket: str, path: str, ttl_s: int) -> str: ...
    async def signed_upload(self, bucket: str, path: str) -> SignedUpload: ...
