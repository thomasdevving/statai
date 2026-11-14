"""create_app(): routers, CORS, error handlers, static mount of ../web."""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.auth import require_demo_key
from app.config import get_settings
from app.deps import get_store
from app.errors import install_error_handlers
from app.guard import GuardMiddleware
from app.jobs import ingest
from app.logs import setup_logging
from app.request_ctx import request_base_url
from app.routers import frames, health, latest_frame, live, local, recipes, sessions, steps
from app.seed import seed_fixture

log = logging.getLogger("ghostchef")


DEFAULT_DEMO_KEY = "dev-key"


def check_deploy_settings() -> None:
    """Fail closed on a public deployment still using the public default demo key.

    Railway injects RAILWAY_ENVIRONMENT_* variables into every deployment; locally they are absent.
    """
    on_railway = any(
        os.environ.get(v)
        for v in ("RAILWAY_ENVIRONMENT", "RAILWAY_ENVIRONMENT_NAME", "RAILWAY_ENVIRONMENT_ID")
    )
    if on_railway:
        key = get_settings().demo_api_key.get_secret_value()
        if not key.strip() or key == DEFAULT_DEMO_KEY:
            raise RuntimeError(
                "DEMO_API_KEY is unset or the default 'dev-key' on Railway: set a long random "
                "DEMO_API_KEY in the service variables"
            )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    check_deploy_settings()
    settings = get_settings()
    store = get_store()
    if settings.storage == "memory":
        await seed_fixture(store)
    yield
    await ingest.cancel_all()


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging()
    # No /docs or /openapi.json: contract §1 leaves only /health open. The schema is exported
    # to backend/openapi.json instead.
    app = FastAPI(
        title="Ghost Chef API",
        version="2.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    # Added first = innermost: CORS (outer) answers preflights and decorates our 401/413s.
    app.add_middleware(GuardMiddleware)
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
    app.include_router(latest_frame.router)  # token-authorised, see the module
    for module in (recipes, steps, frames, sessions, live):
        app.include_router(module.router, dependencies=auth)
    if settings.storage == "memory":
        app.include_router(local.router)

    if settings.web_path.is_dir():
        app.mount("/app", StaticFiles(directory=settings.web_path, html=True), name="web")
    return app


app = create_app()
