"""create_app(): routers, CORS, error handlers, static mount of ../web."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.auth import require_demo_key
from app.config import get_settings
from app.deps import get_store
from app.errors import install_error_handlers
from app.request_ctx import request_base_url
from app.routers import health, local
from app.seed import seed_fixture

log = logging.getLogger("ghostchef")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    store = get_store()
    if settings.storage == "memory":
        await seed_fixture(store)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Ghost Chef API", version="2.0", lifespan=lifespan)

    origins = settings.cors_origin_list
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["*"],
        allow_headers=["X-Demo-Key", "Content-Type"],
    )

    @app.middleware("http")
    async def _base_url(request: Request, call_next):  # type: ignore[no-untyped-def]
        token = request_base_url.set(str(request.base_url).rstrip("/"))
        try:
            return await call_next(request)
        finally:
            request_base_url.reset(token)

    install_error_handlers(app)

    auth = [Depends(require_demo_key)]
    app.include_router(health.router)
    # Authenticated routers are added here as they are implemented (BE-01.4 onward).
    _ = auth
    if settings.storage == "memory":
        app.include_router(local.router)

    if settings.web_path.is_dir():
        app.mount("/app", StaticFiles(directory=settings.web_path, html=True), name="web")
    return app


app = create_app()
