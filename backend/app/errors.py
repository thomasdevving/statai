"""ApiError, the error envelope (API-CONTRACT §1.1), and exception → HTTP mapping."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import ai

log = logging.getLogger("ghostchef.errors")


class ApiError(Exception):
    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        retryable: bool = False,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.retryable = retryable
        self.request_id = request_id


def not_found(what: str) -> ApiError:
    return ApiError(404, "not_found", f"{what} not found")


def envelope(
    status: int, code: str, message: str, retryable: bool = False, request_id: str | None = None
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "code": code,
                "message": message,
                "retryable": retryable,
                "request_id": request_id,
            }
        },
    )


_HTTP_CODES = {
    401: "unauthorized",
    404: "not_found",
    405: "method_not_allowed",
    413: "payload_too_large",
    415: "unsupported_media",
    422: "validation_error",
}


def _ai_error_mapping() -> list[tuple[type[Exception], int, str, bool]]:
    if not ai.available():
        return []
    g = ai.get()
    return [
        (g.AITimeout, 504, "model_timeout", True),
        (g.AIQuotaError, 429, "quota_exhausted", True),
        (g.AIUnavailable, 503, "model_unavailable", True),
        (g.AIInvalidOutput, 503, "model_unavailable", True),
    ]


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError) -> JSONResponse:
        return envelope(
            exc.status, exc.code, exc.message, exc.retryable, exc.request_id or _request_id(request)
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        parts = []
        for err in exc.errors()[:5]:
            loc = ".".join(str(x) for x in err.get("loc", ()) if x not in ("body", "query"))
            parts.append(f"{loc}: {err.get('msg', 'invalid')}" if loc else err.get("msg", ""))
        return envelope(422, "validation_error", "; ".join(parts) or "invalid request")

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _HTTP_CODES.get(exc.status_code, "internal" if exc.status_code >= 500 else "error")
        message = exc.detail if isinstance(exc.detail, str) else "request failed"
        return envelope(exc.status_code, code, message)

    for exc_type, status, code, retryable in _ai_error_mapping():

        async def _ai(
            request: Request, exc: Exception, _s=status, _c=code, _r=retryable
        ) -> JSONResponse:
            log.warning("AI error %s: %s", type(exc).__name__, exc)
            return envelope(_s, _c, str(exc) or _c, _r, _request_id(request))

        app.add_exception_handler(exc_type, _ai)

    @app.exception_handler(Exception)
    async def _internal(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error on %s %s", request.method, request.url.path)
        return envelope(500, "internal", "internal server error", True, _request_id(request))
