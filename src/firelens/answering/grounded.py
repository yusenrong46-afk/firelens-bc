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
from firelens.answering.intent import reviewed_guidance_intent
from firelens.answering.risk_policy import RiskTier
from firelens.answering.typed_snapshot import classify_text
from firelens.answering.validate import salvage_valid_grounded_claims, validate_draft
from firelens.claim_trust import corpus_claim_trust
from firelens.contracts import (
    RELATED_LINK_DESCRIPTION_MAX_CHARS,
    RELATED_LINK_TITLE_MAX_CHARS,
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
    render_claim_texts,
)
from firelens.errors import ProviderError
from firelens.providers.base import AIProvider
from firelens.publication.compiler import (
    compile_high_risk_answer,
    packet_requires_structured,
)
from firelens.publication.fallback import explanation_authority, official_handoff_response

MAX_REPAIR_COUNT = 1


def _bounded_display_text(text: str, *, limit: int, fallback: str) -> str:
    """Bound presentation metadata without changing source identity or evidence."""

    normalized = " ".join(text.split()) or fallback
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."


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


def _force_partial_response(response: AskResponse) -> AskResponse:
    """Rebuild a compiled response when support coverage is known to be partial.

    ``AskResponse`` derives ``history_text`` from the public response mode and
    limitations.  Pydantic's ``model_copy`` deliberately skips validation, so
    changing the mode in place could leave a grounded authority label in the
    next-turn history.  Clear that derived field and run the complete public
    contract again instead.
    """

    if response.response_mode != ResponseMode.GROUNDED:
        return response
    payload = response.model_dump(mode="python")
    payload.update(
        response_mode=ResponseMode.PARTIAL,
        history_text=None,
    )
    return AskResponse.model_validate(payload)


def compile_without_generation(
    question: str,
    packet: EvidencePacket | None,
    *,
    trace_id: str,
    supported_aspects: Sequence[str] = (),
    force_partial: bool = False,
) -> AskResponse | None:
    """Compile a high-risk answer or handoff instead of calling a generator."""

    if packet is None:
        return (
            official_handoff_response(trace_id) if reviewed_guidance_intent(question) else None
        )
    if not packet_requires_structured(packet, question) and not reviewed_guidance_intent(
        question
    ):
        return None
    response = compile_high_risk_answer(
        question,
        packet,
        trace_id=trace_id,
        supported_aspects=supported_aspects,
    )
    return _force_partial_response(response) if force_partial else response


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
            title = _bounded_display_text(
                item.title,
                limit=RELATED_LINK_TITLE_MAX_CHARS,
                fallback="Official source",
            )
            publisher = " ".join(item.publisher.split()) or "official publisher"
            description = _bounded_display_text(
                f"Reviewed {publisher} source related to this question.",
                limit=RELATED_LINK_DESCRIPTION_MAX_CHARS,
                fallback="Reviewed official source related to this question.",
            )
            links.append(
                RelatedLink(
                    title=title,
                    url=HttpUrl(item.canonical_url),
                    description=description,
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
        supported_aspects: Sequence[str] = (),
    ) -> GroundedOutcome:
        observations: list[GenerationObservation] = []
        repair_count = 0
        total_latency_ms = 0.0
        model: str | None = None
        usage: dict[str, Any] = {}
        attempts = 0

        if packet_requires_structured(evidence_packet, question):
            response = compile_high_risk_answer(
                question,
                evidence_packet,
                trace_id=trace_id,
                supported_aspects=supported_aspects,
            )
            if force_partial:
                response = _force_partial_response(response)
            return self._outcome(
                response,
                observations,
                observer,
                validation=response.validation,
                repair_count=0,
                model=model,
                usage=usage,
                attempts=attempts,
                latency_ms=0.0,
            )

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
                for candidate in (repaired_draft, original_draft):
                    if candidate is None:
                        continue
                    salvage = salvage_valid_grounded_claims(candidate, evidence_packet)
                    if salvage is not None:
                        break
                if salvage is not None:
                    active_draft, validation = salvage
                    salvaged = True
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
        evidence_by_id = {item.evidence_id: item for item in evidence_packet.items}
        public_claims = []
        for claim_index, claim in enumerate(active_draft.claims, start=1):
            supports = _unique_claim_supports(claim.evidence_quote_ids, quote_candidates)
            cited = next((evidence_by_id.get(item.evidence_id) for item in supports), None)
            published_text = claim.text
            if classify_text(published_text) in {RiskTier.A, RiskTier.B}:
                continue
            public_claims.append(
                PublicClaim(
                    claim_id=f"C{claim_index}",
                    text=published_text,
                    evidence_status=EvidenceStatus.VERIFIED_CORPUS,
                    supports=supports,
                    trust=corpus_claim_trust(
                        authority=(
                            cited.authority_class.value
                            if cited is not None
                            else "recognized_wildfire_preparedness_program"
                        ),
                        review_provenance=(
                            cited.review_provenance if cited is not None else "native_text"
                        ),
                        conflicts=bool(evidence_packet.conflicts),
                    ),
                    publication=explanation_authority(),
                )
            )
        if not public_claims:
            response = self._validation_handoff(
                trace_id,
                evidence_packet,
                _validation_failure("high-risk generated claims cannot be published"),
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
            answer=render_claim_texts(public_claims),
            claims=public_claims,
            evidence=evidence,
            limitations=[
                *evidence_packet.limitations,
                *(
                    [
                        "This answer is incomplete: FireLens could verify only part of "
                        "the requested guidance from the selected sources. Do not treat "
                        "the remaining guidance as a complete list."
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
