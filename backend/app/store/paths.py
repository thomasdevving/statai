"""Validation of storage bucket/path pairs. Rejects anything that could escape DATA_DIR."""

from __future__ import annotations

import re

from app.store.base import BUCKETS

_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class BadPath(ValueError):
    pass


def check_blob_path(bucket: str, path: str) -> tuple[str, str]:
    if bucket not in BUCKETS:
        raise BadPath(f"unknown bucket {bucket!r}")
    if not path or len(path) > 512 or path.startswith("/"):
        raise BadPath("bad path")
    parts = path.split("/")
    for part in parts:
        if part in ("", ".", "..") or not _SEGMENT.match(part):
            raise BadPath("bad path")
    return bucket, path


def check_prefix(bucket: str, prefix: str) -> tuple[str, str]:
    return check_blob_path(bucket, prefix.rstrip("/"))
