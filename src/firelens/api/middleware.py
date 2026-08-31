"""Anonymous-request bounds, response security headers, and error handlers."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from fastapi.responses import JSONResponse
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from firelens.agent.failures import shout_unexpected
from firelens.api.responses import error_response
from firelens.config import FireLensConfig
from firelens.contracts import ErrorEnvelope
from firelens.operational_logging import log_operation
from firelens.request_guard import AnonymousRequestGuard

_GUARDED_ROUTES = frozenset(
    {
        "/api/v1/ask",
        "/api/v1/live/map",
        "/api/v1/live/nearby",
        "/api/v1/feedback",
    }
)

_UNEXPECTED_ROUTE_LABELS = {
    "/api/v1/ask": "ask",
    "/api/v1/live/map": "live_map",
    "/api/v1/live/nearby": "live_nearby",
    "/api/v1/feedback": "feedback",
    "/api/v1/health/live": "health_live",
    "/api/v1/health/ready": "health_ready",
    "/": "frontend",
}


class BoundedAnonymousRequestMiddleware:
    """Bound guarded request bodies before replaying them to the application.

    The public API accepts a small set of anonymous write routes.  Buffering
    their body here lets the size guard reject a chunked request at the first
    overflowing frame, while the replay ``receive`` callable gives FastAPI a
    normal ASGI body stream.  In particular, this does not rely on Starlette's
    private ``Request._body`` cache, whose implementation is not an API
    contract for middleware.
    """

    def __init__(self, app: ASGIApp, *, request_guard: AnonymousRequestGuard) -> None:
        self.app = app
        self.request_guard = request_guard

    @staticmethod
    async def _send_error(
        response: JSONResponse,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        await response(scope, receive, send)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] not in _GUARDED_ROUTES:
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        declared_length = request.headers.get("content-length")
        if declared_length is not None:
            try:
                declared_bytes = int(declared_length)
            except ValueError:
                await self._send_error(
                    error_response(
                        400,
                        trace_id=uuid4().hex,
                        error_kind="invalid_request",
                        message="The Content-Length header was invalid.",
                    ),
                    scope,
                    receive,
                    send,
                )
                return
            if declared_bytes < 0 or declared_bytes > self.request_guard.max_body_bytes:
                await self._send_error(
                    error_response(
                        413,
                        trace_id=uuid4().hex,
                        error_kind="request_too_large",
                        message="The request exceeded the FireLens public API size limit.",
                    ),
                    scope,
                    receive,
                    send,
                )
                return

        decision = await self.request_guard.check(self.request_guard.anonymous_key(request))
        if not decision.allowed:
            limited = error_response(
                429,
                trace_id=uuid4().hex,
                error_kind="rate_limit",
                message="The anonymous FireLens request limit was reached. Try again shortly.",
                retryable=True,
            )
            limited.headers["Retry-After"] = str(decision.retry_after_seconds)
            limited.headers["X-RateLimit-Limit"] = str(self.request_guard.limit)
            limited.headers["X-RateLimit-Remaining"] = "0"
            limited.headers["X-RateLimit-Scope"] = "instance-local"
            await self._send_error(limited, scope, receive, send)
            return

        bounded_body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                # Preserve ASGI's disconnect signal rather than presenting a
                # truncated body to the downstream request parser.
                await self.app(scope, _disconnecting_receive, send)
                return
            if message["type"] != "http.request":
                continue
            chunk = message.get("body", b"")
            if len(bounded_body) + len(chunk) > self.request_guard.max_body_bytes:
                await self._send_error(
                    error_response(
                        413,
                        trace_id=uuid4().hex,
                        error_kind="request_too_large",
                        message="The request exceeded the FireLens public API size limit.",
                    ),
                    scope,
                    receive,
                    send,
                )
                return
            bounded_body.extend(chunk)
            if not message.get("more_body", False):
                break

        replay_receive = _body_replay_receive(bytes(bounded_body))

        async def send_with_rate_limit_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-RateLimit-Limit"] = str(self.request_guard.limit)
                headers["X-RateLimit-Remaining"] = str(decision.remaining)
                headers["X-RateLimit-Scope"] = "instance-local"
            await send(message)

        await self.app(scope, replay_receive, send_with_rate_limit_headers)


async def _disconnecting_receive() -> Message:
    return {"type": "http.disconnect"}


def _body_replay_receive(body: bytes) -> Receive:
    """Return a one-shot ASGI receive callable for an already bounded body."""

    sent = False

    async def receive() -> Message:
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    return receive


def _apply_security_headers(request: Request, response: Response) -> Response:
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data: https://*.tile.openstreetmap.org https://tile.openstreetmap.org; connect-src 'self'; "
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
    app.add_middleware(BoundedAnonymousRequestMiddleware, request_guard=request_guard)

    @app.middleware("http")
    async def security_headers(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        return _apply_security_headers(request, await call_next(request))


def install_exception_handlers(app: FastAPI, config: FireLensConfig) -> None:
    def unexpected_response(request: Request, exc: Exception) -> JSONResponse:
        """Return and record a content-free public error response.

        A dedicated response-validation handler calls this helper so malformed
        internal response data is consumed inside ``ExceptionMiddleware``.
        Letting it reach the server-wide fallback can cause an ASGI server to
        log the validation exception, whose diagnostics may contain rejected
        response values.
        """

        classified = shout_unexpected(exc, environment=config.deployment_environment)
        trace_id = uuid4().hex
        build_commit = config.build_commit
        if build_commit is None or not re.fullmatch(r"[0-9a-f]{40}", build_commit):
            build_commit = None
        log_operation(
            trace_id=trace_id,
            route=_UNEXPECTED_ROUTE_LABELS.get(request.url.path, "unmatched_route"),
            response_mode="abstention",
            status="error",
            latency_ms=0,
            error_category=classified.public_kind,
            fallback_category=classified.public_kind,
            release_version=config.release_version,
            build_commit=build_commit,
            deployment_environment=config.deployment_environment,
        )
        return error_response(
            500,
            trace_id=trace_id,
            error_kind=classified.public_kind,
            message=classified.public_message,
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        details = [
            {
                "type": str(error.get("type", "validation_error")),
                "loc": list(error.get("loc", ())),
            }
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

    @app.exception_handler(ResponseValidationError)
    async def response_validation_handler(
        request: Request, exc: ResponseValidationError
    ) -> JSONResponse:
        return unexpected_response(request, exc)

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
        return unexpected_response(request, exc)
