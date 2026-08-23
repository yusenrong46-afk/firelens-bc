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


class FireLensDomainError(Exception):
    """Typed public-agent failure with a sanitized, content-free kind."""

    public_kind: str = "domain_error"
    public_message: str = "FireLens could not complete the request."
    retryable: bool = False

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.public_message)


class ToolInputError(FireLensDomainError):
    public_kind = "tool_input_error"
    public_message = "A tool received arguments that FireLens cannot execute."


class OfficialSourceUnavailable(FireLensDomainError):
    public_kind = "official_source_unavailable"
    public_message = "An official source is temporarily unavailable."
    retryable = True


class ReviewedRetrievalUnavailable(FireLensDomainError):
    public_kind = "reviewed_retrieval_unavailable"
    public_message = "Reviewed guidance could not be retrieved from the local corpus."


class ProviderStageUnavailable(FireLensDomainError):
    public_kind = "provider_stage_unavailable"
    public_message = "A required model stage is unavailable."
    retryable = True


class DeadlineExhausted(FireLensDomainError):
    public_kind = "deadline_exhausted"
    public_message = "FireLens could not complete the request within its public deadline."
    retryable = True


class CandidateConfigurationError(FireLensDomainError):
    public_kind = "candidate_configuration_error"
    public_message = "The runtime candidate configuration is invalid."


class UnexpectedProgrammingError(FireLensDomainError):
    public_kind = "unexpected_programming_error"
    public_message = "FireLens encountered an unexpected internal error."
