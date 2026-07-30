"""Neighbor-aware evidence spans and conservative support decisions."""

from __future__ import annotations

import difflib
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field

from firelens.config import FireLensConfig
from firelens.contracts import (
    EvidenceConflict,
    EvidencePacket,
    EvidenceQuoteCandidate,
    EvidenceSpan,
    QueryPlan,
    QueryRoute,
    ReasonCode,
    RetrievalBundle,
    RetrievalHit,
    SupportDecision,
    SupportStatus,
)
from firelens.ingestion.chunking import ChunkRecord
from firelens.retrieval.bm25 import tokenize

_ASPECT_STOPWORDS = {
    "about",
    "after",
    "also",
    "and",
    "are",
    "can",
    "could",
    "do",
    "does",
    "for",
    "from",
    "how",
    "i",
    "in",
    "is",
    "it",
    "into",
    "me",
    "my",
    "our",
    "on",
    "possible",
    "should",
    "that",
    "the",
    "their",
    "this",
    "to",
    "user",
    "we",
    "what",
    "when",
    "where",
    "which",
    "who",
    "with",
    "would",
    "you",
    "your",
    "question",
    "say",
    "simpler",
    "difference",
    "information",
    "guidance",
    "word",
    "words",
}

_ADMINISTRATIVE_STEMS = (
    "apply",
    "application",
    "bylaw",
    "compensat",
    "certif",
    "deadline",
    "eligib",
    "fine",
    "penalt",
    "fee",
    "mandat",
    "permit",
    "policy",
    "register",
    "registration",
    "template",
)

_CONFLICT_CUES = frozenset({"is", "means", "must", "required", "shall", "should", "will"})


def _support_tokens(text: str) -> set[str]:
    """Normalize a small, domain-stable set of morphological equivalents."""

    normalized: set[str] = set()
    for token in tokenize(text):
        if token.startswith("prepar"):
            normalized.add("prepare")
        elif token.startswith("evacuat") or token in {"leave", "leaving"}:
            normalized.add("evacuate")
        elif token.startswith("famil") or token.startswith("household"):
            normalized.add("household")
        elif token.startswith("plan"):
            normalized.add("plan")
        elif token in {"bag", "bags", "kit", "kits"}:
            normalized.add("kit")
        elif token in {"phase", "phases", "stage", "stages"}:
            normalized.add("stage")
        elif token.endswith("s") and len(token) > 4:
            normalized.add(token[:-1])
        else:
            normalized.add(token)
    return normalized


def _aspect_supported(
    aspect: str, packet: EvidencePacket, *, minimum_ratio: float = 0.4
) -> bool:
    required = {
        token
        for token in _support_tokens(aspect)
        if token not in _ASPECT_STOPWORDS and len(token) > 1
    }
    if not required:
        return False
    minimum = 1 if len(required) == 1 else 2
    for item in packet.items:
        available = _support_tokens(item.primary_text)
        overlap = required & available
        if len(overlap) >= minimum and len(overlap) / len(required) >= minimum_ratio:
            return True
    return False


@dataclass(frozen=True)
class EvidenceIndex:
    """Immutable lookup tables constructed once with the service."""

    by_id: dict[str, ChunkRecord]
    by_parent_index: dict[tuple[str, int], ChunkRecord]

    @classmethod
    def from_chunks(cls, chunks: Sequence[ChunkRecord]) -> EvidenceIndex:
        return cls(
            by_id={chunk.chunk_id: chunk for chunk in chunks},
            by_parent_index={
                (chunk.parent_record_id, chunk.chunk_index): chunk for chunk in chunks
            },
        )


@dataclass
class EvidenceGroup:
    parent_record_id: str
    chunk_ids: set[str] = field(default_factory=set)
    primary_hits: list[RetrievalHit] = field(default_factory=list)


def _exact_quote_segments(text: str, *, max_chars: int = 500) -> list[str]:
    """Create bounded exact substrings without normalizing source whitespace."""

    segments: list[str] = []
    for paragraph in text.split("\n\n"):
        if not paragraph:
            continue
        if len(paragraph) <= max_chars:
            segments.append(paragraph)
            continue
        active = ""
        for line in paragraph.splitlines(keepends=True):
            while len(line) > max_chars:
                if active:
                    segments.append(active.rstrip("\n"))
                    active = ""
                segments.append(line[:max_chars])
                line = line[max_chars:]
            if active and len(active) + len(line) > max_chars:
                segments.append(active.rstrip("\n"))
                active = ""
            active += line
        if active:
            segments.append(active.rstrip("\n"))
    return [segment for segment in segments if segment.strip()]


def _detect_conflicts(
    spans: Sequence[EvidenceSpan],
    candidates: Sequence[EvidenceQuoteCandidate],
) -> list[EvidenceConflict]:
    """Find near-matching prescriptive statements whose material terms differ."""

    evidence = {span.evidence_id: span for span in spans}
    conflicts: list[EvidenceConflict] = []
    for left_index, left in enumerate(candidates):
        left_span = evidence[left.evidence_id]
        left_tokens = tokenize(left.text)
        left_counter = Counter(left_tokens)
        if not (_CONFLICT_CUES & set(left_tokens)):
            continue
        for right in candidates[left_index + 1 :]:
            right_span = evidence[right.evidence_id]
            if left_span.document_sha256 == right_span.document_sha256:
                continue
            right_tokens = tokenize(right.text)
            if not (_CONFLICT_CUES & set(right_tokens)):
                continue
            similarity = difflib.SequenceMatcher(
                None,
                " ".join(left_tokens),
                " ".join(right_tokens),
                autojunk=False,
            ).ratio()
            if similarity < 0.88:
                continue
            right_counter = Counter(right_tokens)
            left_only = sorted((left_counter - right_counter).elements())
            right_only = sorted((right_counter - left_counter).elements())
            differing = sorted(set(left_only + right_only))
            if not left_only or not right_only or not (2 <= len(differing) <= 16):
                continue
            conflicts.append(
                EvidenceConflict(
                    conflict_id=f"X{len(conflicts) + 1}",
                    quote_ids=[left.quote_id, right.quote_id],
                    differing_terms=differing,
                    explanation=(
                        "Approved sources contain near-matching prescriptive statements "
                        "with materially different terms."
                    ),
                )
            )
            if len(conflicts) == 3:
                return conflicts
    return conflicts


def _candidate_chunk_ids(
    hit: RetrievalHit,
    by_parent_index: dict[tuple[str, int], ChunkRecord],
    window: int,
) -> set[str]:
    return {
        neighbor.chunk_id
        for offset in range(-window, window + 1)
        if (neighbor := by_parent_index.get((hit.parent_record_id, hit.chunk_index + offset)))
        is not None
    }


def _selection_overlap(text: str, target: str) -> float:
    required = {
        token
        for token in _support_tokens(target)
        if token not in _ASPECT_STOPWORDS and len(token) > 1
    }
    if not required:
        return 0.0
    available = _support_tokens(text)
    return len(required & available) / len(required)


def _select_evidence_hits(
    question: str,
    reranked_hits: Sequence[RetrievalHit],
    *,
    limit: int,
    selection_aspects: Sequence[str],
) -> list[RetrievalHit]:
    """Retain ranked relevance while reserving bounded slots for aspects and sources."""

    pool = list(reranked_hits[: max(limit * 4, limit)])
    if len(pool) <= limit:
        return pool
    targets = list(dict.fromkeys([*selection_aspects, question]))
    selected: set[int] = set()

    for target in targets:
        ranked = sorted(
            (
                (_selection_overlap(hit.text, target), index)
                for index, hit in enumerate(pool)
                if index not in selected
            ),
            key=lambda item: (-item[0], item[1]),
        )
        if ranked and ranked[0][0] >= 0.4:
            selected.add(ranked[0][1])
        if len(selected) == limit:
            break

    selected_sources = {pool[index].source_id for index in selected}
    for index, hit in enumerate(pool):
        if len(selected) == limit:
            break
        if index in selected or hit.source_id in selected_sources:
            continue
        if max((_selection_overlap(hit.text, target) for target in targets), default=0.0) < 0.4:
            continue
        selected.add(index)
        selected_sources.add(hit.source_id)

    for index in range(len(pool)):
        if len(selected) == limit:
            break
        selected.add(index)

    return [pool[index] for index in sorted(selected)]


def build_evidence_packet(
    question: str,
    reranked_hits: Sequence[RetrievalHit],
    chunks: Sequence[ChunkRecord],
    *,
    corpus_version: str,
    config: FireLensConfig,
    evidence_index: EvidenceIndex | None = None,
    selection_aspects: Sequence[str] = (),
) -> EvidencePacket:
    index = evidence_index or EvidenceIndex.from_chunks(chunks)
    groups: list[EvidenceGroup] = []

    selected_hits = _select_evidence_hits(
        question,
        reranked_hits,
        limit=config.max_evidence_spans,
        selection_aspects=selection_aspects,
    )
    for hit in selected_hits:
        neighbor_ids = _candidate_chunk_ids(hit, index.by_parent_index, config.neighbor_window)
        matching_groups: list[EvidenceGroup] = []
        for group in groups:
            if group.parent_record_id == hit.parent_record_id and (
                group.chunk_ids & neighbor_ids
            ):
                matching_groups.append(group)
        if not matching_groups:
            groups.append(
                EvidenceGroup(
                    parent_record_id=hit.parent_record_id,
                    chunk_ids=set(neighbor_ids),
                    primary_hits=[hit],
                )
            )
            continue

        target = matching_groups[0]
        target.chunk_ids.update(neighbor_ids)
        target.primary_hits.append(hit)
        for redundant in matching_groups[1:]:
            target.chunk_ids.update(redundant.chunk_ids)
            target.primary_hits.extend(redundant.primary_hits)
            groups.remove(redundant)

    spans: list[EvidenceSpan] = []
    used_chars = 0
    for group in groups:
        primary_hits = group.primary_hits
        primary_ids = [hit.chunk_id for hit in primary_hits]
        ordered_chunks = sorted(
            (index.by_id[chunk_id] for chunk_id in group.chunk_ids),
            key=lambda chunk: chunk.chunk_index,
        )
        primary_text = "\n\n".join(hit.text for hit in primary_hits)
        context_text = "\n\n".join(chunk.text for chunk in ordered_chunks)
        remaining = config.max_context_chars - used_chars
        if len(context_text) > remaining:
            context_text = primary_text
        if len(context_text) > remaining:
            continue
        hit = primary_hits[0]
        spans.append(
            EvidenceSpan(
                evidence_id=f"E{len(spans) + 1}",
                primary_chunk_ids=primary_ids,
                chunk_ids=[chunk.chunk_id for chunk in ordered_chunks],
                primary_text=primary_text,
                context_text=context_text,
                source_id=hit.source_id,
                title=hit.title,
                publisher=hit.publisher,
                canonical_url=hit.canonical_url,
                page_number=hit.page_number,
                section_title=hit.section_title,
                locator=hit.locator,
                temporal_class=hit.temporal_class,
                authority_class=hit.authority_class,
                document_sha256=hit.document_sha256,
                review_provenance=hit.review_provenance,
            )
        )
        used_chars += len(context_text)

    quote_candidates = [
        EvidenceQuoteCandidate(
            quote_id=f"{span.evidence_id}Q{quote_number}",
            evidence_id=span.evidence_id,
            text=quote,
        )
        for span in spans
        for quote_number, quote in enumerate(_exact_quote_segments(span.primary_text), start=1)
    ]
    conflicts = _detect_conflicts(spans, quote_candidates)
    return EvidencePacket(
        question=question,
        corpus_version=corpus_version,
        items=spans,
        quote_candidates=quote_candidates,
        conflicts=conflicts,
        limitations=[
            "The evidence contains stable official guidance and does not establish current wildfire conditions."
        ],
    )


def decide_support(
    plan: QueryPlan,
    packet: EvidencePacket | None,
    retrieval: RetrievalBundle | None = None,
) -> SupportDecision:
    if plan.route == QueryRoute.PROHIBITED:
        return SupportDecision(
            status=SupportStatus.PROHIBITED,
            reason_code=plan.boundary_reason or ReasonCode.PERSONALIZED_SAFETY_DECISION,
            explanation=(
                "FireLens cannot provide personalized medical advice."
                if plan.boundary_reason == ReasonCode.PERSONALIZED_MEDICAL_ADVICE
                else (
                    "Conversation text cannot override FireLens safety and evidence rules."
                    if plan.boundary_reason == ReasonCode.POLICY_MANIPULATION
                    else (
                        "FireLens cannot provide personalized safety advice, select evacuation "
                        "routes, or decide whether you should stay, leave, evacuate, or return."
                    )
                )
            ),
        )
    if plan.route == QueryRoute.LIVE:
        return SupportDecision(
            status=SupportStatus.REQUIRES_LIVE_DATA,
            reason_code=ReasonCode.LIVE_DATA_REQUIRED,
            explanation="This question requires current official information that is not available in static RAG.",
        )
    if retrieval is not None and not retrieval.complete:
        return SupportDecision(
            status=SupportStatus.INSUFFICIENT_EVIDENCE,
            reason_code=ReasonCode.RETRIEVAL_INCOMPLETE,
            explanation="The required retrieval pipeline did not complete.",
        )
    if packet is None or not packet.items:
        return SupportDecision(
            status=SupportStatus.INSUFFICIENT_EVIDENCE,
            reason_code=ReasonCode.NO_APPROVED_EVIDENCE,
            explanation="No approved static evidence was available for this question.",
        )
    if any(item.temporal_class != "stable_guidance" for item in packet.items):
        return SupportDecision(
            status=SupportStatus.INSUFFICIENT_EVIDENCE,
            reason_code=ReasonCode.WRONG_TEMPORAL_CLASS,
            explanation="Retrieved evidence has an unsupported temporal classification.",
        )
    support_queries = [
        plan.original_question,
        *(request.query for request in plan.retrieval_requests),
    ]
    if not any(
        _aspect_supported(query, packet, minimum_ratio=0.5) for query in support_queries
    ):
        return SupportDecision(
            status=SupportStatus.INSUFFICIENT_EVIDENCE,
            reason_code=ReasonCode.NO_APPROVED_EVIDENCE,
            explanation=(
                "The selected evidence does not directly support the user's question."
            ),
        )
    if packet.conflicts:
        return SupportDecision(
            status=SupportStatus.CONFLICT,
            reason_code=ReasonCode.CONFLICTING_EVIDENCE,
            explanation=(
                "The selected approved sources contain conflicting guidance that must be "
                "shown rather than resolved silently."
            ),
        )
    required = set().union(
        *(request.required_authorities for request in plan.retrieval_requests)
    )
    available = {item.authority_class for item in packet.items}
    if required and not required.issubset(available):
        return SupportDecision(
            status=SupportStatus.INSUFFICIENT_EVIDENCE,
            reason_code=ReasonCode.REQUIRED_AUTHORITY_MISSING,
            explanation="One or more required authority classes were absent from selected evidence.",
        )
    for request in plan.retrieval_requests:
        if not request.required_authorities:
            continue
        authoritative_packet = packet.model_copy(
            update={
                "items": [
                    item
                    for item in packet.items
                    if item.authority_class in request.required_authorities
                ]
            }
        )
        if not (
            _aspect_supported(request.query, authoritative_packet)
            or _aspect_supported(plan.original_question, authoritative_packet)
        ):
            return SupportDecision(
                status=SupportStatus.INSUFFICIENT_EVIDENCE,
                reason_code=ReasonCode.REQUIRED_AUTHORITY_MISSING,
                explanation=(
                    "The required authority appears in retrieval, but its evidence does not "
                    "directly support the retrieval request."
                ),
            )
    if any(
        stem in plan.original_question.casefold() for stem in _ADMINISTRATIVE_STEMS
    ) and not (_aspect_supported(plan.original_question, packet, minimum_ratio=0.8)):
        return SupportDecision(
            status=SupportStatus.INSUFFICIENT_EVIDENCE,
            reason_code=ReasonCode.NO_APPROVED_EVIDENCE,
            explanation=(
                "The selected evidence mentions the topic but does not directly establish "
                "the requested administrative process or policy."
            ),
        )
    if plan.required_aspects:
        supported_aspects = [
            aspect for aspect in plan.required_aspects if _aspect_supported(aspect, packet)
        ]
        missing_aspects = [
            aspect for aspect in plan.required_aspects if aspect not in supported_aspects
        ]
        # A planner may over-decompose a simple question, but its rewrite may not
        # lower the evidence bar. Only strong lexical coverage of the user's own
        # wording can override a missing proposed aspect.
        deictic_question = any(
            marker in plan.original_question.casefold()
            for marker in ("that", "those", "this", "simpler", "why does it", "why does that")
        )
        resolved_request_supported = deictic_question and any(
            _aspect_supported(request.query, packet, minimum_ratio=0.6)
            for request in plan.retrieval_requests
        )
        question_directly_supported = (
            _aspect_supported(plan.original_question, packet, minimum_ratio=0.5)
            or resolved_request_supported
        )
        explicit_multi_topic = len(plan.retrieval_requests) > 1 and any(
            marker in f" {plan.original_question.casefold()} "
            for marker in (" and ", " also ", " both ", ";")
        )
        if (
            missing_aspects
            and not question_directly_supported
            and not (supported_aspects and explicit_multi_topic)
        ):
            return SupportDecision(
                status=SupportStatus.INSUFFICIENT_EVIDENCE,
                reason_code=ReasonCode.NO_APPROVED_EVIDENCE,
                explanation="The selected evidence does not directly cover the required answer aspects.",
                missing_aspects=missing_aspects,
            )
        if missing_aspects and supported_aspects and explicit_multi_topic:
            return SupportDecision(
                status=SupportStatus.PARTIAL,
                reason_code=ReasonCode.RETRIEVAL_INCOMPLETE,
                explanation="The selected evidence supports only part of the request.",
                supported_aspects=supported_aspects,
                missing_aspects=missing_aspects,
            )
    return SupportDecision(
        status=SupportStatus.ANSWERABLE,
        reason_code=ReasonCode.APPROVED_STATIC_EVIDENCE,
        explanation="Approved stable guidance is available.",
        supported_aspects=list(plan.required_aspects),
    )
