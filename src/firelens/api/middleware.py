"""Anonymous-request bounds, response security headers, and error handlers."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from firelens.api.responses import error_response
from firelens.contracts import ErrorEnvelope
from firelens.request_guard import AnonymousRequestGuard

_GUARDED_ROUTES = frozenset(
    {
        "/api/v1/ask",
        "/api/v1/live/map",
        "/api/v1/live/nearby",
        "/api/v1/feedback",
    }
)


def _apply_security_headers(request: Request, response: Response) -> Response:
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; connect-src 'self'; "
        "font-src 'self' data:; object-src 'none'; base-uri 'self'; "
        "frame-ancestors 'none'; form-action 'self'"
    )
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(self)"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    content_type = response.headers.get("content-type", "").lower()
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    elif content_type.startswith("text/html"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


def install_middlewares(
    app: FastAPI,
    request_guard: AnonymousRequestGuard,
) -> None:
    @app.middleware("http")
    async def bounded_anonymous_requests(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if request.url.path not in _GUARDED_ROUTES:
            return await call_next(request)
        declared_length = request.headers.get("content-length")
        if declared_length is not None:
            try:
                declared_bytes = int(declared_length)
            except ValueError:
                return error_response(
                    400,
                    trace_id=uuid4().hex,
                    error_kind="invalid_request",
                    message="The Content-Length header was invalid.",
                )
            if declared_bytes < 0 or declared_bytes > request_guard.max_body_bytes:
                return error_response(
                    413,
                    trace_id=uuid4().hex,
                    error_kind="request_too_large",
                    message="The request exceeded the FireLens public API size limit.",
                )
        decision = await request_guard.check(request_guard.anonymous_key(request))
        if not decision.allowed:
            limited = error_response(
                429,
                trace_id=uuid4().hex,
                error_kind="rate_limit",
                message="The anonymous FireLens request limit was reached. Try again shortly.",
                retryable=True,
            )
            limited.headers["Retry-After"] = str(decision.retry_after_seconds)
            limited.headers["X-RateLimit-Limit"] = str(request_guard.limit)
            limited.headers["X-RateLimit-Remaining"] = "0"
            limited.headers["X-RateLimit-Scope"] = "instance-local"
            return limited
        bounded_body = bytearray()
        async for chunk in request.stream():
            if len(bounded_body) + len(chunk) > request_guard.max_body_bytes:
                return error_response(
                    413,
                    trace_id=uuid4().hex,
                    error_kind="request_too_large",
                    message="The request exceeded the FireLens public API size limit.",
                )
            bounded_body.extend(chunk)
        request._body = bytes(bounded_body)
        guarded = await call_next(request)
        guarded.headers["X-RateLimit-Limit"] = str(request_guard.limit)
        guarded.headers["X-RateLimit-Remaining"] = str(decision.remaining)
        guarded.headers["X-RateLimit-Scope"] = "instance-local"
        return guarded

    @app.middleware("http")
    async def security_headers(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        return _apply_security_headers(request, await call_next(request))


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        details = [
            {key: value for key, value in error.items() if key != "ctx"}
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=422 if request.url.path == "/api/v1/feedback" else 400,
            content={
                **ErrorEnvelope(
                    trace_id=uuid4().hex,
                    error_kind="invalid_request",
                    message="The request did not match the FireLens API contract.",
                ).model_dump(),
                "details": details,
            },
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(_request: Request, _exc: Exception) -> JSONResponse:
        return error_response(
            500,
            trace_id=uuid4().hex,
            error_kind="internal_error",
            message="FireLens encountered an unexpected internal error.",
        )
