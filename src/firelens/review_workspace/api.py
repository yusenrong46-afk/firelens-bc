"""Loopback-only API for the blinded human-review coordinator.

The API deliberately has no CORS support, no actor selector, and no public bind
configuration.  A caller's bearer capability determines the only actor whose
state it can observe or mutate.  The CLI that serves this app is responsible for
binding uvicorn to a loopback address; this module independently rejects
non-loopback peers, unexpected Host values, and cross-origin writes.

This surface does not turn a review session into release-qualifying evidence.
It only exposes the receipt-bound state machine without leaking model/ranking
outputs that were excluded by the input importer.
"""

from __future__ import annotations

import ipaddress
import secrets
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from firelens.review_workspace.models import Identifier, ReviewActor
from firelens.review_workspace.session import (
    ActorProgress,
    BlindReviewSession,
    ReviewDecision,
    ReviewerLockReceipt,
    ReviewPresentation,
    ReviewSessionError,
    SessionFinalizationReceipt,
)

DEFAULT_ALLOWED_HOSTS = ("127.0.0.1", "localhost", "::1")
MAX_REVIEW_BODY_BYTES = 64 * 1024
_WEB_ROOT = Path(__file__).resolve().parent / "web"


class _StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PresentationRequest(_StrictRequest):
    presentation_id: Identifier


class DecisionRequest(PresentationRequest):
    decision: ReviewDecision


class EventConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_type: str
    sequence: int = Field(ge=1, strict=True)
    event_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class ReviewApiError(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    error: str
    message: str


class ReviewApiContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    context_version: Literal["firelens_review_api_context.v1"]
    implementation_status: Literal["nonqualifying_backend_scaffold"]
    qualification_eligible: Literal[False]
    session_id: str
    review_kind: str
    suite_kind: str
    actor_id: str
    actor_display_name: str
    actor_role: str


def _host_name(raw_host: str) -> str | None:
    """Return a normalized hostname while rejecting userinfo and malformed ports."""

    try:
        parsed = urlsplit(f"//{raw_host}")
        _ = parsed.port
    except ValueError:
        return None
    if parsed.username is not None or parsed.password is not None:
        return None
    return parsed.hostname.casefold() if parsed.hostname else None


def _security_headers(response: Response) -> Response:
    headers = response.headers
    headers["Cache-Control"] = "no-store, max-age=0"
    headers["Pragma"] = "no-cache"
    headers["Content-Security-Policy"] = (
        "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
        "frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
    )
    headers["Cross-Origin-Opener-Policy"] = "same-origin"
    headers["Cross-Origin-Resource-Policy"] = "same-origin"
    headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    headers["Referrer-Policy"] = "no-referrer"
    headers["X-Content-Type-Options"] = "nosniff"
    headers["X-Frame-Options"] = "DENY"
    return response


def _error(status_code: int, error: str, message: str) -> JSONResponse:
    response = JSONResponse(
        status_code=status_code,
        content=ReviewApiError(error=error, message=message).model_dump(),
    )
    _security_headers(response)
    return response


def _validate_capabilities(
    session: BlindReviewSession,
    actor_tokens: Mapping[str, str],
) -> tuple[tuple[str, str], ...]:
    actor_ids = {actor.actor_id for actor in session.session.actors}
    if set(actor_tokens) != actor_ids:
        raise ValueError("actor capability roster must exactly match the review session")
    capabilities: list[tuple[str, str]] = []
    observed_tokens: set[str] = set()
    for actor_id in sorted(actor_ids):
        token = actor_tokens[actor_id]
        if not isinstance(token, str) or len(token.encode("utf-8")) < 32:
            raise ValueError("actor capabilities must contain at least 32 UTF-8 bytes")
        if token in observed_tokens:
            raise ValueError("actor capabilities must be unique")
        observed_tokens.add(token)
        capabilities.append((actor_id, token))
    return tuple(capabilities)


def create_review_workspace_app(
    session: BlindReviewSession,
    *,
    actor_tokens: Mapping[str, str],
    allowed_origins: Sequence[str],
    allowed_hosts: Sequence[str] = DEFAULT_ALLOWED_HOSTS,
    max_body_bytes: int = MAX_REVIEW_BODY_BYTES,
) -> FastAPI:
    """Create the local API around one already-created or resumed session."""

    capabilities = _validate_capabilities(session, actor_tokens)
    normalized_hosts = frozenset(host.strip("[]").casefold() for host in allowed_hosts)
    if not normalized_hosts:
        raise ValueError("allowed_hosts must not be empty")
    for host in normalized_hosts:
        if host == "localhost":
            continue
        try:
            if not ipaddress.ip_address(host).is_loopback:
                raise ValueError("allowed hosts must be loopback addresses")
        except ValueError as exc:
            raise ValueError("allowed hosts must use localhost or loopback IPs") from exc
    normalized_origins = frozenset(origin.rstrip("/") for origin in allowed_origins)
    if not normalized_origins:
        raise ValueError("at least one exact same-origin review origin is required")
    for origin in normalized_origins:
        parsed = urlsplit(origin)
        if parsed.scheme != "http" or parsed.hostname is None or parsed.path not in {"", "/"}:
            raise ValueError("review origins must be exact loopback HTTP origins")
        try:
            if (
                not ipaddress.ip_address(parsed.hostname).is_loopback
                and parsed.hostname != "localhost"
            ):
                raise ValueError("review origins must resolve syntactically to loopback")
        except ValueError as exc:
            if parsed.hostname != "localhost":
                raise ValueError(
                    "review origins must use localhost or a loopback address"
                ) from exc
    if max_body_bytes < 1 or max_body_bytes > 1024 * 1024:
        raise ValueError("review API body limit is out of bounds")

    app = FastAPI(
        title="FireLens blind human review",
        version="1.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @app.middleware("http")
    async def enforce_local_capability_boundary(request: Request, call_next):
        peer = request.client.host if request.client is not None else ""
        try:
            peer_is_loopback = ipaddress.ip_address(peer).is_loopback
        except ValueError:
            peer_is_loopback = False
        if not peer_is_loopback:
            return _error(
                403, "local_only", "The review service accepts loopback clients only."
            )

        host = _host_name(request.headers.get("host", ""))
        if host not in normalized_hosts:
            return _error(403, "invalid_host", "The review request used an unapproved host.")

        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin", "").rstrip("/")
            if origin not in normalized_origins:
                return _error(
                    403,
                    "invalid_origin",
                    "Review changes require the exact local review origin.",
                )
            fetch_site = request.headers.get("sec-fetch-site")
            if fetch_site not in {None, "same-origin"}:
                return _error(
                    403,
                    "cross_site_request",
                    "Cross-site review changes are refused.",
                )
            content_type = request.headers.get("content-type", "").split(";", 1)[0].strip()
            if content_type != "application/json":
                return _error(415, "invalid_media_type", "Review changes require JSON.")

        declared_length = request.headers.get("content-length")
        if declared_length is not None:
            try:
                declared_bytes = int(declared_length)
            except ValueError:
                return _error(400, "invalid_request", "Content-Length is invalid.")
            if declared_bytes < 0 or declared_bytes > max_body_bytes:
                return _error(413, "request_too_large", "The review request is too large.")

        if request.method not in {"GET", "HEAD"}:
            body = bytearray()
            async for chunk in request.stream():
                if len(body) + len(chunk) > max_body_bytes:
                    return _error(413, "request_too_large", "The review request is too large.")
                body.extend(chunk)
            request._body = bytes(body)

        response = await call_next(request)
        return _security_headers(response)

    @app.exception_handler(RequestValidationError)
    async def invalid_request_handler(_request: Request, _exc: RequestValidationError):
        return _error(400, "invalid_request", "The review request did not match its contract.")

    @app.exception_handler(ReviewSessionError)
    async def invalid_transition_handler(_request: Request, _exc: ReviewSessionError):
        return _error(409, "invalid_transition", "The review transition is not permitted.")

    @app.exception_handler(Exception)
    async def unexpected_error_handler(_request: Request, _exc: Exception):
        return _error(500, "internal_error", "The local review service could not continue.")

    def current_actor(request: Request) -> ReviewActor:
        authorization = request.headers.get("authorization", "")
        scheme, separator, supplied = authorization.partition(" ")
        if separator != " " or scheme.casefold() != "bearer" or not supplied:
            # Raising a ReviewSessionError would incorrectly classify authentication
            # as a workflow conflict, so return a deliberately generic 401 response
            # through a private exception handled below.
            raise _ReviewAuthenticationError
        matched_actor_id: str | None = None
        for actor_id, expected in capabilities:
            if secrets.compare_digest(supplied, expected):
                matched_actor_id = actor_id
        if matched_actor_id is None:
            raise _ReviewAuthenticationError
        return next(
            actor for actor in session.session.actors if actor.actor_id == matched_actor_id
        )

    @app.exception_handler(_ReviewAuthenticationError)
    async def authentication_handler(_request: Request, _exc: _ReviewAuthenticationError):
        response = _error(401, "unauthorized", "A valid actor capability is required.")
        response.headers["WWW-Authenticate"] = "Bearer"
        return response

    @app.get("/review", include_in_schema=False)
    async def reviewer_client() -> FileResponse:
        return FileResponse(_WEB_ROOT / "review.html", media_type="text/html")

    @app.get("/review/review.css", include_in_schema=False)
    async def reviewer_styles() -> FileResponse:
        return FileResponse(_WEB_ROOT / "review.css", media_type="text/css")

    @app.get("/review/review.js", include_in_schema=False)
    async def reviewer_script() -> FileResponse:
        return FileResponse(_WEB_ROOT / "review.js", media_type="text/javascript")

    @app.get("/api/v1/review/context", response_model=ReviewApiContext)
    async def context(request: Request) -> ReviewApiContext:
        actor = current_actor(request)
        return ReviewApiContext(
            context_version="firelens_review_api_context.v1",
            implementation_status="nonqualifying_backend_scaffold",
            qualification_eligible=False,
            session_id=session.session.session_id,
            review_kind=session.session.review_kind,
            suite_kind=session.suite.suite_kind,
            actor_id=actor.actor_id,
            actor_display_name=actor.display_name,
            actor_role=actor.role,
        )

    @app.get("/api/v1/review/progress", response_model=ActorProgress)
    async def progress(request: Request) -> ActorProgress:
        actor = current_actor(request)
        return session.progress(actor.actor_id)

    @app.post("/api/v1/review/present", response_model=ReviewPresentation)
    async def present(payload: _StrictRequest, request: Request) -> ReviewPresentation:
        del payload
        actor = current_actor(request)
        return session.present_next(actor.actor_id)

    @app.get("/api/v1/review/current", response_model=ReviewPresentation)
    async def current(request: Request) -> ReviewPresentation:
        actor = current_actor(request)
        return session.current_presentation(actor.actor_id)

    @app.post("/api/v1/review/acknowledge", response_model=EventConfirmation)
    async def acknowledge(
        payload: PresentationRequest,
        request: Request,
    ) -> EventConfirmation:
        actor = current_actor(request)
        event = session.acknowledge_display(actor.actor_id, payload.presentation_id)
        return EventConfirmation(
            event_type=event.event_type,
            sequence=event.sequence,
            event_hash=event.event_hash,
        )

    @app.post("/api/v1/review/decision", response_model=EventConfirmation)
    async def decision(payload: DecisionRequest, request: Request) -> EventConfirmation:
        actor = current_actor(request)
        event = session.record_decision(
            actor.actor_id,
            payload.presentation_id,
            payload.decision,
        )
        return EventConfirmation(
            event_type=event.event_type,
            sequence=event.sequence,
            event_hash=event.event_hash,
        )

    @app.post("/api/v1/review/lock", response_model=ReviewerLockReceipt)
    async def lock(payload: _StrictRequest, request: Request) -> ReviewerLockReceipt:
        del payload
        actor = current_actor(request)
        return session.lock_reviewer(actor.actor_id)

    @app.post("/api/v1/review/finalize", response_model=SessionFinalizationReceipt)
    async def finalize(
        payload: _StrictRequest,
        request: Request,
    ) -> SessionFinalizationReceipt:
        del payload
        actor = current_actor(request)
        return session.finalize_adjudication(actor.actor_id)

    return app


class _ReviewAuthenticationError(Exception):
    """Private sentinel that prevents credentials from entering error text."""
