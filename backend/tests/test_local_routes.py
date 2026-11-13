from __future__ import annotations

from app.deps import get_store


def test_local_file_served(client):
    import asyncio

    store = get_store()
    asyncio.run(store.put_blob("media", "r/steps/1/ref.jpg", b"\xff\xd8\xff jpeg", "image/jpeg"))
    r = client.get("/local-files/media/r/steps/1/ref.jpg")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"
    assert r.content == b"\xff\xd8\xff jpeg"


def test_local_file_traversal_rejected(client):
    for url in (
        "/local-files/media/../config.py",
        "/local-files/media/%2e%2e/%2e%2e/app/config.py",
        "/local-files/media/r/..%2F..%2Fsecret",
        "/local-files/nope/x.jpg",
        "/local-files/media/missing.jpg",
    ):
        r = client.get(url)
        assert r.status_code == 404, url


def _upload_url(path="r1/source.mp4"):
    import asyncio

    up = asyncio.run(get_store().signed_upload("videos", path))
    return up["upload_url"].replace("http://testserver", "")


def test_local_upload_round_trip(client):
    url = _upload_url()
    r = client.put(
        url,
        content=b"\x00\x00\x00\x18ftypmp42" + b"x" * 5000,
        headers={"Content-Type": "video/mp4"},
    )
    assert r.status_code == 200
    import asyncio

    assert asyncio.run(get_store().blob_exists("videos", "r1/source.mp4"))
    # single use
    assert client.put(url, content=b"again").status_code == 403


def test_local_upload_wrong_token(client):
    url = _upload_url()
    bad = url.split("?token=")[0] + "?token=wrong"
    r = client.put(bad, content=b"abc")
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "forbidden"
    # token bound to its path
    other = url.replace("r1/source.mp4", "r2/source.mp4")
    assert client.put(other, content=b"abc").status_code == 403


def test_local_upload_too_large(client, monkeypatch):
    from app.config import get_settings

    url = _upload_url()
    monkeypatch.setenv("MAX_VIDEO_MB", "1")
    get_settings.cache_clear()

    def body():
        for _ in range(3):
            yield b"x" * (600 * 1024)

    r = client.put(url, content=body())
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "payload_too_large"
    import asyncio

    store = get_store()
    assert not asyncio.run(store.blob_exists("videos", "r1/source.mp4"))
    assert not list((store.data_dir / "videos" / "r1").glob("*.part"))
    # a failed upload does not burn the token: retry with the same URL works
    monkeypatch.setenv("MAX_VIDEO_MB", "5")
    get_settings.cache_clear()
    assert client.put(url, content=b"x" * 1000).status_code == 200
    assert asyncio.run(store.blob_exists("videos", "r1/source.mp4"))
