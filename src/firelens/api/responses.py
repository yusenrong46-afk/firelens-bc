"""Stable public error envelopes and timeout responses."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi.responses import JSONResponse

from firelens.config import FireLensConfig
from firelens.contracts import ErrorEnvelope, ResponseMode, ResponseStatus
from firelens.operational_logging import log_operation

ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"model": ErrorEnvelope},
    413: {"model": ErrorEnvelope, "description": "Content Too Large"},
    429: {"model": ErrorEnvelope},
    404: {"model": ErrorEnvelope},
    500: {"model": ErrorEnvelope},
    502: {"model": ErrorEnvelope},
    503: {"model": ErrorEnvelope},
}


def provider_error_status(error_kind: str | None) -> int:
    return 502 if error_kind in {"invalid_request", "invalid_response"} else 503


def error_response(
    status_code: int,
    *,
    trace_id: str,
    error_kind: str,
    message: str,
    retryable: bool = False,
) -> JSONResponse:
    envelope = ErrorEnvelope(
        trace_id=trace_id,
        error_kind=error_kind,
        message=message,
        retryable=retryable,
    )
    return JSONResponse(status_code=status_code, content=envelope.model_dump())


def deadline_response(config: FireLensConfig, route: str) -> JSONResponse:
    trace_id = uuid4().hex
    log_operation(
        trace_id=trace_id,
        route=route,
        response_mode=ResponseMode.ABSTENTION.value,
        status=ResponseStatus.ERROR.value,
        latency_ms=config.public_request_deadline_seconds * 1_000,
        provider_stages=(),
        error_category="timeout",
        release_version=config.release_version,
        build_commit=config.build_commit,
        deployment_environment=config.deployment_environment,
    )
    return error_response(
        503,
        trace_id=trace_id,
        error_kind="timeout",
        message="FireLens could not complete the request within its public deadline.",
        retryable=True,
    )
