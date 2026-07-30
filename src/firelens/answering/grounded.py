"""Bounded grounded generation, repair, validation, and public citations."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Protocol

from pydantic import HttpUrl

from firelens.answering.generate import (
    draft_schema,
    generation_messages,
    repair_generation_messages,
)
from firelens.answering.validate import salvage_valid_grounded_claims, validate_draft
from firelens.contracts import (
    AskResponse,
    ClaimSupport,
    EvidencePacket,
    EvidenceQuoteCandidate,
    EvidenceStatus,
    GroundedDraft,
    PublicClaim,
    PublicEvidence,
    ReasonCode,
    ResponseMode,
    ResponseStatus,
    TemporalClass,
    ValidationReport,
)
from firelens.errors import ProviderError
from firelens.providers.base import AIProvider

MAX_REPAIR_COUNT = 1


@dataclass(frozen=True)
class GenerationObservation:
    stage: str
    model: str | None
    usage: dict[str, Any]
    attempts: int
    latency_ms: float
    validation: ValidationReport | None = None
    error_kind: str | None = None


class GenerationObserver(Protocol):
    generations: list[GenerationObservation]


@dataclass(frozen=True)
class GroundedOutcome:
    response: AskResponse
    observations: tuple[GenerationObservation, ...]
    validation: ValidationReport | None
    repair_count: int
    model: str | None
    usage: dict[str, Any]
    attempts: int
    latency_ms: float
    cited_evidence_ids: tuple[str, ...] = ()


def _unique_claim_supports(
    quote_ids: Sequence[str], quote_candidates: Mapping[str, EvidenceQuoteCandidate]
) -> list[ClaimSupport]:
    supports: list[ClaimSupport] = []
    seen: set[tuple[str, str]] = set()
    for quote_id in quote_ids:
        candidate = quote_candidates[quote_id]
        pair = (candidate.evidence_id, candidate.text)
        if pair not in seen:
            seen.add(pair)
            supports.append(
                ClaimSupport(evidence_id=candidate.evidence_id, quote=candidate.text)
            )
    return supports


def _validation_failure(message: str) -> ValidationReport:
    return ValidationReport(
        accepted=False,
        schema_valid=False,
        citation_ids_valid=False,
        quotes_exact=False,
        claim_support_valid=False,
        policy_valid=False,
        errors=[message],
    )


class GroundedAnswerEngine:
    """Generate once, repair at most once, and expose only validated claims."""

    def __init__(self, provider: AIProvider) -> None:
        self.provider = provider

    async def answer(
        self,
        question: str,
        evidence_packet: EvidencePacket,
        observer: GenerationObserver | None = None,
        *,
        trace_id: str,
        force_partial: bool = False,
    ) -> GroundedOutcome:
        observations: list[GenerationObservation] = []
        repair_count = 0
        total_latency_ms = 0.0
        model: str | None = None
        usage: dict[str, Any] = {}
        attempts = 0

        started = perf_counter()
        try:
            generated = await self.provider.generate_grounded(
                generation_messages(evidence_packet, original_question=question),
                output_schema=draft_schema(evidence_packet),
            )
        except ProviderError as exc:
            latency_ms = (perf_counter() - started) * 1_000
            observations.append(
                GenerationObservation(
                    stage="grounded_generation",
                    model=None,
                    usage={},
                    attempts=0,
                    latency_ms=latency_ms,
                    error_kind=exc.kind.value,
                )
            )
            response = AskResponse(
                status=ResponseStatus.ABSTENTION,
                trace_id=trace_id,
                response_mode=ResponseMode.ABSTENTION,
                answer="FireLens could not produce a validated answer from the available evidence.",
                reason_code=ReasonCode.GENERATION_UNAVAILABLE,
                error_kind=exc.kind.value,
                limitations=list(evidence_packet.limitations),
            )
            return self._outcome(
                response,
                observations,
                observer,
                validation=None,
                repair_count=repair_count,
                model=model,
                usage=usage,
                attempts=attempts,
                latency_ms=latency_ms,
            )

        generation_ms = (perf_counter() - started) * 1_000
        total_latency_ms = generation_ms
        model = generated.model
        usage = generated.usage
        attempts = generated.attempts
        active_draft = generated.draft if isinstance(generated.draft, GroundedDraft) else None
        validation = (
            validate_draft(active_draft, evidence_packet)
            if active_draft is not None
            else _validation_failure("generation did not return a grounded draft")
        )
        observations.append(
            GenerationObservation(
                stage="grounded_generation",
                model=model,
                usage=usage,
                attempts=attempts,
                latency_ms=generation_ms,
                validation=validation,
            )
        )

        if active_draft is None:
            response = self._abstention(
                trace_id,
                "The generated answer did not match the grounded-answer format.",
                evidence_packet,
                validation,
            )
            return self._outcome(
                response,
                observations,
                observer,
                validation=validation,
                repair_count=repair_count,
                model=model,
                usage=usage,
                attempts=attempts,
                latency_ms=total_latency_ms,
            )

        salvaged = False
        if not validation.accepted:
            original_draft = active_draft
            original_validation = validation
            repaired_draft: GroundedDraft | None = None
            repair_validation: ValidationReport | None = None
            repair_started = perf_counter()
            repair_count = MAX_REPAIR_COUNT
            try:
                repaired = await self.provider.generate_grounded(
                    repair_generation_messages(
                        evidence_packet,
                        original_question=question,
                        validation_errors=validation.errors,
                    ),
                    output_schema=draft_schema(evidence_packet),
                )
            except ProviderError as exc:
                repair_ms = (perf_counter() - repair_started) * 1_000
                observations.append(
                    GenerationObservation(
                        stage="grounded_repair",
                        model=None,
                        usage={},
                        attempts=0,
                        latency_ms=repair_ms,
                        error_kind=exc.kind.value,
                    )
                )
            else:
                repair_ms = (perf_counter() - repair_started) * 1_000
                total_latency_ms += repair_ms
                repaired_draft = (
                    repaired.draft if isinstance(repaired.draft, GroundedDraft) else None
                )
                repair_validation = (
                    validate_draft(repaired_draft, evidence_packet)
                    if repaired_draft is not None
                    else _validation_failure("repair did not return a grounded draft")
                )
                observations.append(
                    GenerationObservation(
                        stage="grounded_repair",
                        model=repaired.model,
                        usage=repaired.usage,
                        attempts=repaired.attempts,
                        latency_ms=repair_ms,
                        validation=repair_validation,
                    )
                )
                if repair_validation.accepted and repaired_draft is not None:
                    generated = repaired
                    active_draft = repaired_draft
                    validation = repair_validation
                    model = repaired.model
                    usage = repaired.usage
                    attempts = repaired.attempts

            if not validation.accepted:
                salvage = (
                    salvage_valid_grounded_claims(repaired_draft, evidence_packet)
                    if repaired_draft is not None
                    else None
                ) or salvage_valid_grounded_claims(original_draft, evidence_packet)
                if salvage is not None:
                    active_draft, validation = salvage
                    salvaged = True
                else:
                    validation = repair_validation or original_validation
                    response = self._abstention(
                        trace_id,
                        "The generated answer did not pass FireLens validation.",
                        evidence_packet,
                        validation,
                    )
                    return self._outcome(
                        response,
                        observations,
                        observer,
                        validation=validation,
                        repair_count=repair_count,
                        model=model,
                        usage=usage,
                        attempts=attempts,
                        latency_ms=total_latency_ms,
                    )

        quote_candidates = {
            candidate.quote_id: candidate for candidate in evidence_packet.quote_candidates
        }
        public_claims = [
            PublicClaim(
                claim_id=f"C{claim_index}",
                text=claim.text,
                evidence_status=EvidenceStatus.VERIFIED_CORPUS,
                supports=_unique_claim_supports(claim.evidence_quote_ids, quote_candidates),
            )
            for claim_index, claim in enumerate(active_draft.claims, start=1)
        ]
        cited_ids = {
            support.evidence_id for claim in public_claims for support in claim.supports
        }
        evidence = [
            PublicEvidence(
                evidence_id=item.evidence_id,
                title=item.title,
                publisher=item.publisher,
                canonical_url=HttpUrl(item.canonical_url),
                locator=item.locator,
                temporal_class=TemporalClass.STABLE_GUIDANCE,
                review_provenance=item.review_provenance,
                primary_text=item.primary_text,
                context_text=item.context_text,
            )
            for item in evidence_packet.items
            if item.evidence_id in cited_ids
        ]
        response = AskResponse(
            status=ResponseStatus.ANSWER,
            trace_id=trace_id,
            response_mode=(
                ResponseMode.PARTIAL if force_partial or salvaged else ResponseMode.GROUNDED
            ),
            answer=" ".join(claim.text.strip() for claim in public_claims),
            claims=public_claims,
            evidence=evidence,
            limitations=[
                *evidence_packet.limitations,
                *(
                    ["Unsupported generated statements were omitted after validation."]
                    if salvaged
                    else []
                ),
            ],
            validation=validation,
        )
        return self._outcome(
            response,
            observations,
            observer,
            validation=validation,
            repair_count=repair_count,
            model=model,
            usage=usage,
            attempts=attempts,
            latency_ms=total_latency_ms,
            cited_evidence_ids=tuple(sorted(cited_ids)),
        )

    @staticmethod
    def _abstention(
        trace_id: str,
        answer: str,
        evidence_packet: EvidencePacket,
        validation: ValidationReport,
    ) -> AskResponse:
        return AskResponse(
            status=ResponseStatus.ABSTENTION,
            trace_id=trace_id,
            response_mode=ResponseMode.ABSTENTION,
            answer=answer,
            reason_code=ReasonCode.DRAFT_VALIDATION_FAILED,
            limitations=list(evidence_packet.limitations),
            validation=validation,
        )

    @staticmethod
    def _outcome(
        response: AskResponse,
        observations: list[GenerationObservation],
        observer: GenerationObserver | None,
        *,
        validation: ValidationReport | None,
        repair_count: int,
        model: str | None,
        usage: dict[str, Any],
        attempts: int,
        latency_ms: float,
        cited_evidence_ids: tuple[str, ...] = (),
    ) -> GroundedOutcome:
        if observer is not None:
            observer.generations.extend(observations)
        return GroundedOutcome(
            response=response,
            observations=tuple(observations),
            validation=validation,
            repair_count=repair_count,
            model=model,
            usage=usage,
            attempts=attempts,
            latency_ms=latency_ms,
            cited_evidence_ids=cited_evidence_ids,
        )
