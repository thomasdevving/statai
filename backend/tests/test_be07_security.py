"""BE-07.3: auth coverage of every route, /local-files traversal, log redaction."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid

import pytest
from fastapi.routing import APIRoute

from app.deps import get_store
from app.logs import JsonFormatter, RedactQueryFilter, redact

OPEN_PATH = re.compile(
    r"^(/health|/local-files/.*|/local-upload/.*|/sessions/[^/]+/latest-frame\.jpg)$"
)


def _fill(path: str) -> str:
    return re.sub(r"\{[^}]+\}", lambda m: str(uuid.uuid4()), path)


def _api_routes(routes, prefix=""):
    """Flattens FastAPI's lazily included routers into (method, full path) pairs."""
    for route in routes:
        if isinstance(route, APIRoute):
            for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
                yield method, prefix + route.path
        elif hasattr(route, "original_router"):
            yield from _api_routes(
                route.original_router.routes, prefix + route.include_context.prefix
            )


def _routes(app):
    return _api_routes(app.routes)


def test_every_route_but_the_open_ones_needs_the_key(client, app):
    checked = open_ = 0
    for method, path in _routes(app):
        url = _fill(path)
        if OPEN_PATH.match(url):
            open_ += 1
            continue
        for headers in ({}, {"X-Demo-Key": "wrong"}, {"X-Demo-Key": ""}):
            r = client.request(method, url, headers=headers)
            assert r.status_code == 401, (method, path, headers, r.status_code)
            assert r.json()["error"]["code"] == "unauthorized"
        checked += 1
    assert checked >= 15
    assert open_ >= 4  # health, local-files, local-upload, latest-frame


def test_open_routes_are_exactly_the_documented_ones(app):
    open_paths = sorted(p for _, p in _routes(app) if OPEN_PATH.match(_fill(p)))
    assert open_paths == [
        "/health",
        "/local-files/{bucket}/{path:path}",
        "/local-upload/{bucket}/{path:path}",
        "/sessions/{session_id}/latest-frame.jpg",
    ]


def test_unknown_paths_and_docs_are_not_open(client):
    for path in ("/", "/docs", "/openapi.json", "/redoc", "/nope", "/sessions", "/%2e%2e/etc"):
        assert client.get(path).status_code == 401, path


def test_local_routes_absent_in_supabase_mode(monkeypatch):
    from app.config import get_settings
    from app.main import create_app

    monkeypatch.setenv("STORAGE", "supabase")
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "k" * 20)
    get_settings.cache_clear()
    paths = {p for _, p in _routes(create_app())}
    assert not any(p.startswith(("/local-files", "/local-upload")) for p in paths)


# ----------------------------------------------------------------------------- traversal


@pytest.mark.parametrize(
    "url",
    [
        "/local-files/media/../config.py",
        "/local-files/media/%2e%2e/%2e%2e/app/config.py",
        "/local-files/media/%2E%2E%2F%2E%2E%2Fapp%2Fconfig.py",
        "/local-files/media/r/..%2F..%2Fsecret",
        "/local-files/media//etc/passwd",
        "/local-files/media/%2Fetc%2Fpasswd",
        "/local-files/media/..\\..\\app\\config.py",
        "/local-files/media/r%5C..%5C..%5Csecret",
        "/local-files/media/r/..%5C..%5Csecret",
        "/local-files/%2e%2e/%2e%2e/etc/passwd",
        "/local-files/..%2Fmedia/x.jpg",
        "/local-files/media/.hidden",
        "/local-files/media/a%00b",
        "/local-files/frames/./x",
        "/local-files/nope/x.jpg",
    ],
)
def test_local_files_traversal_never_serves(client, url):
    r = client.get(url)
    assert r.status_code in (404, 422), (url, r.status_code)
    assert b"root:" not in r.content and b"def " not in r.content


def test_local_files_symlink_escape_is_refused(client, tmp_path):
    store = get_store()
    asyncio.run(store.put_blob("media", "r/ok.jpg", b"\xff\xd8ok", "image/jpeg"))
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP SECRET")
    link = store.data_dir / "media" / "r" / "link.txt"
    link.symlink_to(secret)
    assert client.get("/local-files/media/r/ok.jpg").status_code == 200
    r = client.get("/local-files/media/r/link.txt")
    assert r.status_code == 404 and b"TOP SECRET" not in r.content


def test_upload_path_traversal_refused_even_with_a_valid_token(client):
    up = asyncio.run(get_store().signed_upload("videos", "r1/source.mp4"))
    token = up["upload_token"]
    for url in (
        f"/local-upload/videos/r1/../r2/source.mp4?token={token}",
        f"/local-upload/videos/r1%2F..%2Fr2%2Fsource.mp4?token={token}",
        f"/local-upload/videos/r1/other.mp4?token={token}",
        f"/local-upload/media/r1/source.mp4?token={token}",
    ):
        r = client.put(url, content=b"x")
        assert r.status_code in (403, 404), (url, r.status_code)
    assert not asyncio.run(get_store().blob_exists("videos", "r2/source.mp4"))
    assert not asyncio.run(get_store().blob_exists("videos", "r1/other.mp4"))


# ----------------------------------------------------------------------------- logs


def _format(msg: str, *args, exc: BaseException | None = None) -> dict:
    record = logging.LogRecord("ghostchef.t", logging.ERROR, __file__, 1, msg, args, None)
    if exc is not None:
        try:
            raise exc
        except BaseException:  # noqa: BLE001
            import sys

            record.exc_info = sys.exc_info()
    return json.loads(JsonFormatter().format(record))


JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJhYmMifQ.c2lnbmF0dXJlLXNlY3JldA"


def test_json_log_redacts_urls_tokens_and_keys():
    url = f"https://x.supabase.co/storage/v1/object/upload/sign/videos/r/source.mp4?token={JWT}"
    google = "AIza" + "B" * 35
    line = _format(
        "failed for url '%s' key=%s",
        url,
        google,
        exc=RuntimeError(f"Client error for url '{url}&signature=abcdef' {google}"),
    )
    blob = json.dumps(line)
    for leaked in (JWT, google, "abcdef"):
        assert leaked not in blob


def test_json_log_redacts_configured_secrets(monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("DEMO_API_KEY", "super-secret-demo-key")
    monkeypatch.setenv("GEMINI_API_KEY", "gem-secret-value-123")
    get_settings.cache_clear()
    out = redact("header X-Demo-Key: super-secret-demo-key / gem-secret-value-123")
    assert "super-secret-demo-key" not in out and "gem-secret-value-123" not in out


def test_access_log_redacts_latest_frame_token_and_upload_token():
    f = RedactQueryFilter()
    rec = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        1,
        '%s - "%s %s HTTP/%s" %d',
        ("1.2.3.4:5", "GET", "/sessions/x/latest-frame.jpg?t=SECRETTOKEN&a=1", "1.1", 200),
        None,
    )
    f.filter(rec)
    assert "SECRETTOKEN" not in rec.getMessage()
    rec2 = logging.LogRecord(
        "uvicorn.access", logging.INFO, __file__, 1, "%s", ("/local-upload/v/p?token=TOK123",), None
    )
    f.filter(rec2)
    assert "TOK123" not in rec2.getMessage()


def test_live_token_and_demo_key_never_logged(client, auth, caplog):
    from app.seed import SEED_RECIPE_ID

    asyncio.run(get_store().update_recipe(SEED_RECIPE_ID, status="published"))
    with caplog.at_level(logging.DEBUG):
        r = client.get(f"/live-token?recipe_id={SEED_RECIPE_ID}", headers=auth)
        client.get("/recipes", headers={"X-Demo-Key": "wrong-key-value"})
    assert r.status_code == 200
    token = r.json()["token"]
    text = caplog.text + "".join(str(getattr(rec, "fields", "")) for rec in caplog.records)
    assert token not in text
    assert "test-key" not in text and "wrong-key-value" not in text


def test_redaction_leaves_plain_t_equals_text_alone():
    # A bare "t=" outside a query string is ordinary text (e.g. a timeout), not a token.
    assert redact("timeout t=2.5s") == "timeout t=2.5s"
    assert redact("GET /x?t=abc&y=1") == "GET /x?t=***&y=1"
    assert redact("a&t=zzz") == "a&t=***"
