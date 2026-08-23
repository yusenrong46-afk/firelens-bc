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
    ToolInputError,
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
    ValueError,
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
    if isinstance(exc, (TypeError, ValueError, KeyError)):
        return ToolInputError()
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
    if environment in {"local", "test"}:
        LOGGER.exception("unexpected programming error in public Ask")
    return classified
