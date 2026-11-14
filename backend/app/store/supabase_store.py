"""SupabaseStore: rows in Supabase Postgres, blobs in private Supabase Storage (API-CONTRACT §6).

The backend uses the service role key, which bypasses Row Level Security. The supabase client is
synchronous, so every call runs in a worker thread (asyncio.to_thread) and never blocks the event
loop. Any Supabase failure becomes ApiError(500, "internal"); log lines carry the error type and
code, never the key, a token, or a signed URL.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from collections.abc import Callable
from dataclasses import fields as dc_fields
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, TypeVar
from urllib.parse import urlparse

import httpx
from postgrest.exceptions import APIError as PostgrestError
from storage3.exceptions import StorageApiError
from storage3.utils import StorageException
from supabase import Client, ClientOptions, create_client  # ClientOptions = SyncClientOptions

from app.errors import ApiError
from app.store.base import BlobTooLarge, Event, Recipe, Session, SignedUpload, Step, utcnow
from app.store.paths import check_blob_path, check_prefix

log = logging.getLogger("ghostchef.store.supabase")

T = TypeVar("T")

# Supabase documents signed upload URLs as valid for 2 hours (checked 2026-11-14,
# reference/python/storage-from-createsigneduploadurl). The API takes no expiry parameter.
UPLOAD_TTL = timedelta(hours=2)
_LIST_PAGE = 1000  # Storage list() page size
_REMOVE_CHUNK = 1000  # Storage remove() accepts up to 1000 paths per call
_URL_CACHE_MAX = 4096
_DOWNLOAD_URL_TTL_S = 600
_DOWNLOAD_CHUNK = 1024 * 1024
_DOWNLOAD_TIMEOUT = httpx.Timeout(60.0, connect=10.0)  # read timeout is per chunk
_FK_VIOLATION = "23503"
_SECRETISH = re.compile(r"(token|signature|apikey|authorization)=[^&\s'\"]+", re.IGNORECASE)

_RECIPE_FIELDS = {f.name for f in dc_fields(Recipe)}
_STEP_FIELDS = {f.name for f in dc_fields(Step)}
_SESSION_FIELDS = {f.name for f in dc_fields(Session)}


def _is_uuid(value: str | None) -> bool:
    if not value:
        return False
    try:
        uuid.UUID(str(value))
    except ValueError:
        return False
    return True


def _ts(value: Any) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _num(value: Any) -> float | None:
    return None if value is None else float(value)


def _db(value: Any) -> Any:
    """Python value -> JSON-safe value for PostgREST."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict | list):
        return json.loads(json.dumps(value, default=str))
    return value


def _row(obj: Any, names: set[str]) -> dict[str, Any]:
    return {n: _db(getattr(obj, n)) for n in names}


def _check_fields(given: dict[str, Any], allowed: set[str]) -> None:
    unknown = set(given) - allowed
    if unknown:
        raise TypeError(f"unknown fields: {sorted(unknown)}")


def _recipe(r: dict[str, Any]) -> Recipe:
    return Recipe(
        id=str(r["id"]),
        title=r["title"],
        status=r["status"],
        chef_name=r.get("chef_name"),
        video_path=r.get("video_path"),
        transcript=r.get("transcript"),
        step_marks_s=[float(x) for x in (r.get("step_marks_s") or [])],
        error=r.get("error"),
        consent_at=_ts(r.get("consent_at")),
        created_at=_ts(r["created_at"]) or utcnow(),
    )


def _step(r: dict[str, Any]) -> Step:
    return Step(
        id=str(r["id"]),
        recipe_id=str(r["recipe_id"]),
        idx=int(r["idx"]),
        title=r["title"],
        key_line=r["key_line"],
        instruction=r["instruction"],
        timestamp_s=float(r["timestamp_s"]),
        chef_quote=r.get("chef_quote"),
        clip_start_s=_num(r.get("clip_start_s")),
        clip_end_s=_num(r.get("clip_end_s")),
        success_criteria=list(r.get("success_criteria") or []),
        watch_fors=list(r.get("watch_fors") or []),
        ref_image_path=r.get("ref_image_path"),
        clip_path=r.get("clip_path"),
        timer_s=r.get("timer_s"),
    )


def _session(r: dict[str, Any]) -> Session:
    return Session(
        id=str(r["id"]),
        recipe_id=str(r["recipe_id"]),
        client=r["client"],
        device_label=r.get("device_label"),
        started_at=_ts(r["started_at"]) or utcnow(),
        finished_at=_ts(r.get("finished_at")),
    )


def _event(r: dict[str, Any]) -> Event:
    return Event(
        id=str(r["id"]),
        session_id=str(r["session_id"]),
        kind=r["kind"],
        step_id=str(r["step_id"]) if r.get("step_id") else None,
        request_id=str(r["request_id"]) if r.get("request_id") else None,
        payload=dict(r.get("payload") or {}),
        created_at=_ts(r["created_at"]) or utcnow(),
    )


def _event_row(e: Event) -> dict[str, Any]:
    return {
        "id": e.id,
        "session_id": e.session_id,
        "kind": e.kind,
        "step_id": e.step_id,
        "request_id": e.request_id,
        "payload": _db(e.payload),
        "created_at": _db(e.created_at),
    }


def _not_found(exc: StorageApiError) -> bool:
    return str(exc.status) == "404" or exc.code in ("not_found", "NoSuchKey")


def _describe(exc: BaseException) -> str:
    """Short, secret-free description of a Supabase failure for the log."""
    if isinstance(exc, PostgrestError):
        detail = f"code={exc.code} {exc.message or ''}"
    elif isinstance(exc, StorageApiError):
        detail = f"status={exc.status} code={exc.code} {exc.message or ''}"
    elif isinstance(exc, httpx.HTTPStatusError):
        detail = f"status={exc.response.status_code}"
    else:
        detail = ""
    detail = _SECRETISH.sub(r"\1=<redacted>", detail)[:200]
    return f"{type(exc).__name__} {detail}".strip()


def resumable_endpoint_for(supabase_url: str) -> str:
    """https://<ref>.supabase.co -> https://<ref>.storage.supabase.co/storage/v1/upload/resumable.

    Supabase's resumable-upload guide recommends the direct storage hostname. Any other host
    (custom domain, local stack) falls back to the API URL itself.
    """
    parsed = urlparse(supabase_url)
    host = parsed.hostname or ""
    if host.endswith(".supabase.co") and host.count(".") == 2:
        ref = host.split(".", 1)[0]
        return f"https://{ref}.storage.supabase.co/storage/v1/upload/resumable"
    return f"{supabase_url.rstrip('/')}/storage/v1/upload/resumable"


class SupabaseStore:
    def __init__(self, url: str, service_key: str, client: Client | None = None) -> None:
        self.url = url.rstrip("/")
        self._resumable = resumable_endpoint_for(self.url)
        # Our own HTTP/1.1 client: supabase-py defaults to http2=True, and one HTTP/2 connection
        # shared by the worker threads of asyncio.to_thread fails under concurrent calls
        # (RemoteProtocolError, seen in this batch). httpx's HTTP/1.1 pool is thread-safe.
        self._http = httpx.Client(
            http2=False,
            timeout=httpx.Timeout(30.0, connect=10.0),
            follow_redirects=False,  # never forward the apikey header elsewhere
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
        self._client: Client = client or create_client(
            self.url,
            service_key,
            options=ClientOptions(
                auto_refresh_token=False,
                persist_session=False,
                httpx_client=self._http,
            ),
        )
        # (bucket, path, ttl) -> (signed url, monotonic time after which it is not reused)
        self._url_cache: dict[tuple[str, str, int], tuple[str, float]] = {}

    # ------------------------------------------------------------------ plumbing
    async def _run(self, what: str, fn: Callable[[], T]) -> T:
        try:
            return await asyncio.to_thread(fn)
        except ApiError:
            raise
        except (PostgrestError, StorageException, httpx.HTTPError, OSError) as exc:
            log.error("supabase %s failed: %s", what, _describe(exc))
            raise ApiError(500, "internal", "storage error") from None

    def _table(self, name: str):  # noqa: ANN202 - postgrest builder type
        return self._client.table(name)

    def _bucket(self, bucket: str):  # noqa: ANN202 - storage3 bucket proxy
        return self._client.storage.from_(bucket)

    # ------------------------------------------------------------------ recipes
    async def list_recipes(self, status: str | None = None) -> list[Recipe]:
        def q() -> list[dict[str, Any]]:
            b = self._table("recipes").select("*")
            if status is not None:
                b = b.eq("status", status)
            return b.order("created_at", desc=True).execute().data

        return [_recipe(r) for r in await self._run("list_recipes", q)]

    async def get_recipe(self, recipe_id: str) -> Recipe | None:
        if not _is_uuid(recipe_id):
            return None
        rows = await self._run(
            "get_recipe",
            lambda: self._table("recipes").select("*").eq("id", recipe_id).limit(1).execute().data,
        )
        return _recipe(rows[0]) if rows else None

    async def create_recipe(self, recipe: Recipe) -> Recipe:
        row = _row(recipe, _RECIPE_FIELDS)
        rows = await self._run(
            "create_recipe", lambda: self._table("recipes").insert(row).execute().data
        )
        return _recipe(rows[0])

    async def update_recipe(self, recipe_id: str, **fields: Any) -> Recipe | None:
        _check_fields(fields, _RECIPE_FIELDS - {"id"})
        if not _is_uuid(recipe_id):
            return None
        if not fields:
            return await self.get_recipe(recipe_id)
        data = {k: _db(v) for k, v in fields.items()}
        rows = await self._run(
            "update_recipe",
            lambda: self._table("recipes").update(data).eq("id", recipe_id).execute().data,
        )
        return _recipe(rows[0]) if rows else None

    async def delete_recipe(self, recipe_id: str) -> bool:
        """Rows only: steps, sessions and events go with `on delete cascade`.

        Blobs are removed by app.store.ops.purge_recipe, which the DELETE route and the seed
        script use for both stores.
        """
        if not _is_uuid(recipe_id):
            return False
        rows = await self._run(
            "delete_recipe",
            lambda: self._table("recipes").delete().eq("id", recipe_id).execute().data,
        )
        return bool(rows)

    # ------------------------------------------------------------------ steps
    async def get_step(self, step_id: str) -> Step | None:
        if not _is_uuid(step_id):
            return None
        rows = await self._run(
            "get_step",
            lambda: self._table("steps").select("*").eq("id", step_id).limit(1).execute().data,
        )
        return _step(rows[0]) if rows else None

    async def list_steps(self, recipe_id: str) -> list[Step]:
        if not _is_uuid(recipe_id):
            return []
        rows = await self._run(
            "list_steps",
            lambda: (
                self._table("steps")
                .select("*")
                .eq("recipe_id", recipe_id)
                .order("idx")
                .execute()
                .data
            ),
        )
        return [_step(r) for r in rows]

    async def replace_steps(self, recipe_id: str, steps: list[Step]) -> list[Step]:
        """Deletes the recipe's steps, then inserts the new ones (in idx order).

        Not one transaction: a failure between the two leaves the recipe without steps, and the
        caller sees a 500. Events pointing at the old steps get step_id = null (FK rule).
        """
        idxs = [s.idx for s in steps]
        if len(set(idxs)) != len(idxs):
            raise ValueError("duplicate step idx")
        rows = [
            {**_row(s, _STEP_FIELDS), "recipe_id": recipe_id}
            for s in sorted(steps, key=lambda s: s.idx)
        ]

        def q() -> None:
            self._table("steps").delete().eq("recipe_id", recipe_id).execute()
            if rows:
                self._table("steps").insert(rows).execute()

        await self._run("replace_steps", q)
        return await self.list_steps(recipe_id)

    async def update_step(self, step_id: str, **fields: Any) -> Step | None:
        _check_fields(fields, _STEP_FIELDS - {"id"})
        if not _is_uuid(step_id):
            return None
        if not fields:
            return await self.get_step(step_id)
        data = {k: _db(v) for k, v in fields.items()}
        rows = await self._run(
            "update_step",
            lambda: self._table("steps").update(data).eq("id", step_id).execute().data,
        )
        return _step(rows[0]) if rows else None

    # ------------------------------------------------------------------ sessions
    async def create_session(self, session: Session) -> Session:
        row = _row(session, _SESSION_FIELDS)
        rows = await self._run(
            "create_session", lambda: self._table("sessions").insert(row).execute().data
        )
        return _session(rows[0])

    async def get_session(self, session_id: str) -> Session | None:
        if not _is_uuid(session_id):
            return None
        rows = await self._run(
            "get_session",
            lambda: (
                self._table("sessions").select("*").eq("id", session_id).limit(1).execute().data
            ),
        )
        return _session(rows[0]) if rows else None

    async def update_session(self, session_id: str, **fields: Any) -> Session | None:
        _check_fields(fields, _SESSION_FIELDS - {"id"})
        if not _is_uuid(session_id):
            return None
        if not fields:
            return await self.get_session(session_id)
        data = {k: _db(v) for k, v in fields.items()}
        rows = await self._run(
            "update_session",
            lambda: self._table("sessions").update(data).eq("id", session_id).execute().data,
        )
        return _session(rows[0]) if rows else None

    async def list_sessions(
        self, *, active: bool | None = None, limit: int = 20, recipe_id: str | None = None
    ) -> list[Session]:
        if limit <= 0 or (recipe_id is not None and not _is_uuid(recipe_id)):
            return []

        def q() -> list[dict[str, Any]]:
            b = self._table("sessions").select("*")
            if active is True:
                b = b.is_("finished_at", "null")
            elif active is False:
                b = b.not_.is_("finished_at", "null")
            if recipe_id is not None:
                b = b.eq("recipe_id", recipe_id)
            # PostgREST caps a response at its max-rows setting (1000 by default).
            return b.order("started_at", desc=True).limit(limit).execute().data

        return [_session(r) for r in await self._run("list_sessions", q)]

    async def append_event(self, event: Event) -> Event:
        if not _is_uuid(event.session_id):
            raise KeyError(event.session_id)
        row = _event_row(event)

        def q() -> list[dict[str, Any]]:
            try:
                return self._table("session_events").insert(row).execute().data
            except PostgrestError as exc:
                if exc.code != _FK_VIOLATION:
                    raise
                # Unknown session -> KeyError (as MemoryStore). Unknown step -> keep the event
                # with step_id = null, the same state "on delete set null" leaves behind.
                exists = (
                    self._table("sessions")
                    .select("id")
                    .eq("id", row["session_id"])
                    .limit(1)
                    .execute()
                    .data
                )
                if not exists:
                    raise KeyError(row["session_id"]) from None
                if row["step_id"] is None:
                    raise
                return self._table("session_events").insert({**row, "step_id": None}).execute().data

        rows = await self._run("append_event", q)
        return _event(rows[0])

    async def list_events(self, session_id: str) -> list[Event]:
        if not _is_uuid(session_id):
            return []
        rows = await self._run(
            "list_events",
            lambda: (
                self._table("session_events")
                .select("*")
                .eq("session_id", session_id)
                .order("created_at")
                .execute()
                .data
            ),
        )
        return [_event(r) for r in rows]

    # ------------------------------------------------------------------ blobs
    def _forget_url(self, bucket: str, path: str) -> None:
        for key in [k for k in self._url_cache if k[0] == bucket and k[1] == path]:
            del self._url_cache[key]

    def _forget_prefix(self, bucket: str, prefix: str) -> None:
        start = prefix.rstrip("/") + "/"
        for key in [k for k in self._url_cache if k[0] == bucket and k[1].startswith(start)]:
            del self._url_cache[key]

    async def put_blob(self, bucket: str, path: str, data: bytes, content_type: str) -> None:
        check_blob_path(bucket, path)
        await self._run(
            "put_blob",
            lambda: self._bucket(bucket).upload(
                path, data, {"content-type": content_type, "upsert": "true"}
            ),
        )
        self._forget_url(bucket, path)

    async def get_blob(self, bucket: str, path: str) -> bytes | None:
        check_blob_path(bucket, path)

        def q() -> bytes | None:
            try:
                return self._bucket(bucket).download(path)
            except StorageApiError as exc:
                if _not_found(exc):
                    return None
                raise

        return await self._run("get_blob", q)

    async def download_to_file(self, bucket: str, path: str, dest: Path, max_bytes: int) -> bool:
        check_blob_path(bucket, path)

        def q() -> bool:
            try:
                # Not signed_url(): a cached URL may have little life left for a long download.
                url = self._bucket(bucket).create_signed_url(path, _DOWNLOAD_URL_TTL_S)["signedURL"]
            except StorageApiError as exc:
                if _not_found(exc):
                    return False
                raise
            if not url:
                raise OSError("empty signed URL")
            try:
                with self._http.stream("GET", url, timeout=_DOWNLOAD_TIMEOUT) as resp:
                    if resp.status_code == 404:
                        return False
                    resp.raise_for_status()
                    declared = resp.headers.get("content-length")
                    if declared and declared.isdigit() and int(declared) > max_bytes:
                        raise BlobTooLarge
                    written = 0
                    with dest.open("wb") as out:
                        for chunk in resp.iter_bytes(_DOWNLOAD_CHUNK):
                            written += len(chunk)
                            if written > max_bytes:
                                raise BlobTooLarge
                            out.write(chunk)
            except BaseException:
                dest.unlink(missing_ok=True)
                raise
            return True

        return await self._run("download_to_file", q)

    async def delete_blob(self, bucket: str, path: str) -> None:
        check_blob_path(bucket, path)
        await self._run("delete_blob", lambda: self._bucket(bucket).remove([path]))
        self._forget_url(bucket, path)

    def _list_all(self, bucket: str, folder: str) -> list[str]:
        """Every object path under folder (recursive). Runs in a worker thread."""
        out: list[str] = []
        pending = [folder]
        b = self._bucket(bucket)
        while pending:
            current = pending.pop()
            offset = 0
            while True:
                page = b.list(current, {"limit": _LIST_PAGE, "offset": offset})
                for item in page:
                    name = item.get("name")
                    if not name or name == ".emptyFolderPlaceholder":
                        continue
                    full = f"{current}/{name}"
                    if item.get("id") is None:  # a folder
                        pending.append(full)
                    else:
                        out.append(full)
                if len(page) < _LIST_PAGE:
                    break
                offset += _LIST_PAGE
        return out

    async def delete_prefix(self, bucket: str, prefix: str) -> None:
        bucket, prefix = check_prefix(bucket, prefix)

        def q() -> None:
            paths = self._list_all(bucket, prefix)
            for i in range(0, len(paths), _REMOVE_CHUNK):
                self._bucket(bucket).remove(paths[i : i + _REMOVE_CHUNK])

        await self._run("delete_prefix", q)
        self._forget_prefix(bucket, prefix)

    async def blob_exists(self, bucket: str, path: str) -> bool:
        check_blob_path(bucket, path)
        return await self._run("blob_exists", lambda: self._bucket(bucket).exists(path))

    async def signed_url(self, bucket: str, path: str, ttl_s: int) -> str | None:
        """None when the object does not exist (Supabase refuses to sign it)."""
        check_blob_path(bucket, path)
        key = (bucket, path, ttl_s)
        now = time.monotonic()
        hit = self._url_cache.get(key)
        if hit and hit[1] > now:
            return hit[0]

        def q() -> str | None:
            try:
                return self._bucket(bucket).create_signed_url(path, ttl_s)["signedURL"]
            except StorageApiError as exc:
                if _not_found(exc):
                    return ""
                raise

        url = await self._run("signed_url", q)
        if url == "":
            log.warning("signed_url: missing object in bucket %s", bucket)
            return None
        if not url:
            log.error("supabase signed_url failed: empty URL")
            raise ApiError(500, "internal", "storage error")
        if len(self._url_cache) >= _URL_CACHE_MAX:
            for k in [k for k, (_, until) in self._url_cache.items() if until <= now]:
                del self._url_cache[k]
            if len(self._url_cache) >= _URL_CACHE_MAX:
                self._url_cache.clear()
        # Reused for half its lifetime, so a cached URL always has >= ttl/2 left.
        self._url_cache[key] = (url, now + ttl_s / 2)
        return url

    async def signed_upload(self, bucket: str, path: str) -> SignedUpload:
        check_blob_path(bucket, path)
        expires_at = utcnow() + UPLOAD_TTL
        res = await self._run(
            "signed_upload", lambda: self._bucket(bucket).create_signed_upload_url(path)
        )
        return {
            "upload_url": res["signed_url"],
            "upload_token": res["token"],
            "resumable_endpoint": self._resumable,
            "expires_at": expires_at,
        }
