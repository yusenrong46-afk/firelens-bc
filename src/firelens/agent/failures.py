"""Classify public-agent failures without recording request content."""

from __future__ import annotations

import logging
from typing import Any

from firelens.agent.packet import AgentPacket
from firelens.errors import (
    CorpusValidationError,
    DeadlineExhausted,
    FireLensDomainError,
    IndexValidationError,
    OfficialSourceUnavailable,
    ProviderError,
    ProviderStageUnavailable,
    ReviewedRetrievalUnavailable,
    UnexpectedProgrammingError,
)
from firelens.live import LiveDataUnavailable

LOGGER = logging.getLogger("firelens.agent")

EXPECTED_TOOL_FAILURES = (
    FireLensDomainError,
    LiveDataUnavailable,
    ProviderError,
    IndexValidationError,
    CorpusValidationError,
    TimeoutError,
)


def classify_failure(exc: BaseException) -> FireLensDomainError:
    if isinstance(exc, FireLensDomainError):
        return exc
    if isinstance(exc, LiveDataUnavailable):
        return OfficialSourceUnavailable()
    if isinstance(exc, ProviderError):
        return ProviderStageUnavailable()
    if isinstance(exc, (IndexValidationError, CorpusValidationError)):
        return ReviewedRetrievalUnavailable()
    if isinstance(exc, TimeoutError):
        return DeadlineExhausted()
    return UnexpectedProgrammingError()


def record_expected_failure(packet: AgentPacket, exc: BaseException) -> dict[str, Any]:
    classified = classify_failure(exc)
    if isinstance(classified, UnexpectedProgrammingError):
        raise classified from exc
    packet.policy.fallback_reason = classified.public_kind
    return {"error": classified.public_kind}


def shout_unexpected(exc: BaseException, *, environment: str) -> UnexpectedProgrammingError:
    classified = (
        exc if isinstance(exc, UnexpectedProgrammingError) else UnexpectedProgrammingError()
    )
    LOGGER.error(
        "unexpected programming error in public request",
        extra={
            "call_site": "public_exception_handler",
            "deployment_environment": environment,
            "exception_class": type(exc).__name__,
            "failure_category": classified.public_kind,
        },
    )
    return classified
