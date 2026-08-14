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
    RelatedLink,
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

    @staticmethod
    def source_handoff(
        trace_id: str,
        evidence_packet: EvidencePacket,
        *,
        answer: str,
        reason_code: ReasonCode,
        extra_limitation: str,
        validation: ValidationReport | None = None,
        error_kind: str | None = None,
    ) -> AskResponse:
        links: list[RelatedLink] = []
        seen_urls: set[str] = set()
        for item in evidence_packet.items:
            if item.canonical_url in seen_urls:
                continue
            seen_urls.add(item.canonical_url)
            links.append(
                RelatedLink(
                    title=item.title,
                    url=HttpUrl(item.canonical_url),
                    description=(f"Reviewed {item.publisher} source related to this question."),
                )
            )
            if len(links) == 3:
                break
        return AskResponse(
            status=ResponseStatus.ANSWER,
            trace_id=trace_id,
            response_mode=ResponseMode.SCOPE_REDIRECT,
            answer=answer,
            reason_code=reason_code,
            error_kind=error_kind,
            validation=validation,
            limitations=[
                *evidence_packet.limitations,
                extra_limitation,
            ],
            related_links=links,
        )

    @classmethod
    def _validation_handoff(
        cls,
        trace_id: str,
        evidence_packet: EvidencePacket,
        validation: ValidationReport,
    ) -> AskResponse:
        return cls.source_handoff(
            trace_id,
            evidence_packet,
            answer=(
                "FireLens found reviewed sources related to this question, but the generated "
                "summary did not pass claim-support validation. Open the official sources "
                "below instead of relying on an unsupported answer."
            ),
            reason_code=ReasonCode.DRAFT_VALIDATION_FAILED,
            validation=validation,
            extra_limitation=(
                "No generated material claim was published from the rejected draft."
            ),
        )

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
            response = self.source_handoff(
                trace_id,
                evidence_packet,
                answer=(
                    "FireLens found reviewed sources related to this question, but the "
                    "language service is temporarily unavailable. Open the official sources "
                    "below for the reviewed information."
                ),
                reason_code=ReasonCode.GENERATION_UNAVAILABLE,
                error_kind=exc.kind.value,
                extra_limitation=(
                    "No generated material claim was published while the language service "
                    "was unavailable."
                ),
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
            response = self._validation_handoff(trace_id, evidence_packet, validation)
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
        salvaged_claim_count = 0
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
                salvage = None
                salvage_source: GroundedDraft | None = None
                for candidate in (repaired_draft, original_draft):
                    if candidate is None:
                        continue
                    salvage = salvage_valid_grounded_claims(candidate, evidence_packet)
                    if salvage is not None:
                        salvage_source = candidate
                        break
                if salvage is not None:
                    active_draft, validation = salvage
                    salvaged = True
                    assert salvage_source is not None
                    salvaged_claim_count = len(salvage_source.claims) - len(active_draft.claims)
                else:
                    validation = repair_validation or original_validation
                    response = self._validation_handoff(trace_id, evidence_packet, validation)
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
                    [
                        "This answer is incomplete: "
                        f"{salvaged_claim_count} generated "
                        f"{'item was' if salvaged_claim_count == 1 else 'items were'} "
                        "omitted after validation. Do not treat the remaining items "
                        "as a complete list."
                    ]
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
