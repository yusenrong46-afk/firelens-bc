"""Stable error types shared by FireLens adapters and domain services."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ProviderErrorKind(StrEnum):
    AUTHENTICATION = "authentication"
    CREDITS = "credits"
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    UNAVAILABLE = "unavailable"
    MODEL_UNAVAILABLE = "model_unavailable"
    INVALID_REQUEST = "invalid_request"
    INVALID_RESPONSE = "invalid_response"
    SAFETY = "safety"
    UNKNOWN = "unknown"


@dataclass(eq=False)
class ProviderError(RuntimeError):
    """A sanitized external-provider failure safe to expose through the API."""

    kind: ProviderErrorKind
    message: str
    status_code: int | None = None
    retryable: bool = False
    retry_after_seconds: float | None = None
    zdr_report: object | None = None

    def __str__(self) -> str:
        return self.message


class IndexValidationError(ValueError):
    """The local vector index cannot be trusted for the current corpus."""


class CorpusValidationError(ValueError):
    """The static corpus does not match its governed manifest."""
