"""Memory mode only: serve stored blobs and accept the dev-only signed upload.

Mounted by create_app only when STORAGE=memory; each route checks again.
"""

from __future__ import annotations

import asyncio
import mimetypes
import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse, Response

from app.config import Settings, get_settings
from app.deps import get_store
from app.errors import ApiError
from app.store.memory import MemoryStore
from app.store.paths import BadPath

router = APIRouter(tags=["local (memory mode only)"], include_in_schema=False)

# (bucket, path) pairs with an upload running; one writer per target.
_in_flight: set[tuple[str, str]] = set()


def _memory_store(settings: Settings) -> MemoryStore:
    store = get_store()
    if settings.storage != "memory" or not isinstance(store, MemoryStore):
        raise ApiError(404, "not_found", "not found")
    return store


@router.get("/local-files/{bucket}/{path:path}")
async def local_file(
    bucket: str, path: str, settings: Annotated[Settings, Depends(get_settings)]
) -> FileResponse:
    store = _memory_store(settings)
    try:
        target = store.blob_file(bucket, path)
    except BadPath:
        raise ApiError(404, "not_found", "file not found") from None
    if not await asyncio.to_thread(target.is_file):
        raise ApiError(404, "not_found", "file not found")
    media_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    return FileResponse(target, media_type=media_type)


@router.put("/local-upload/{bucket}/{path:path}", status_code=200)
async def local_upload(
    bucket: str,
    path: str,
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    token: Annotated[str, Query(min_length=1, max_length=256)],
) -> Response:
    store = _memory_store(settings)
    try:
        target = store.blob_file(bucket, path)
    except BadPath:
        raise ApiError(404, "not_found", "not found") from None
    # The token is only consumed after the file is in place, so a dropped or oversized upload
    # can be retried with the same URL until it expires.
    if not store.check_upload_token(bucket, path, token):
        raise ApiError(403, "forbidden", "invalid or expired upload token")
    if (bucket, path) in _in_flight:
        raise ApiError(409, "upload_in_progress", "an upload to this path is already running")

    limit = settings.max_video_bytes
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit:
        raise ApiError(413, "payload_too_large", f"upload exceeds {settings.max_video_mb} MB")

    _in_flight.add((bucket, path))
    try:
        await asyncio.to_thread(target.parent.mkdir, parents=True, exist_ok=True)
        tmp = target.with_name(f"{target.name}.{secrets.token_hex(8)}.part")
        total = 0
        fh = await asyncio.to_thread(open, tmp, "wb")
        try:
            async for chunk in request.stream():
                total += len(chunk)
                if total > limit:
                    raise ApiError(
                        413, "payload_too_large", f"upload exceeds {settings.max_video_mb} MB"
                    )
                await asyncio.to_thread(fh.write, chunk)
        except BaseException:
            await asyncio.to_thread(fh.close)
            await asyncio.to_thread(tmp.unlink, True)
            raise
        await asyncio.to_thread(fh.close)
        # Re-check: the token may have expired or been revoked (recipe deleted) meanwhile.
        if not store.consume_upload_token(bucket, path, token):
            await asyncio.to_thread(tmp.unlink, True)
            raise ApiError(403, "forbidden", "invalid or expired upload token")
        await asyncio.to_thread(tmp.replace, target)
    finally:
        _in_flight.discard((bucket, path))
    return Response(status_code=200)
