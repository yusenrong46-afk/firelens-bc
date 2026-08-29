"""Deterministic construction of bounded evidence packets.

The public compatibility surface remains :mod:`firelens.answering.context`.
Keeping packet assembly separate from lexical support decisions makes the
authority-bearing data path easier to inspect without changing its behavior.
"""

from __future__ import annotations

import difflib
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field

from firelens.answering.context_support import (
    SUPPORT_TOKEN_OVERLAP_FLOOR,
    support_token_overlap,
)
from firelens.config import FireLensConfig
from firelens.contracts import (
    EvidenceConflict,
    EvidencePacket,
    EvidenceQuoteCandidate,
    EvidenceSpan,
    RetrievalHit,
)
from firelens.ingestion.chunking import ChunkRecord
from firelens.publication.comparison_targets import reserve_fused_atomic_hits
from firelens.retrieval.bm25 import tokenize

_CONFLICT_CUES = frozenset({"is", "means", "must", "required", "shall", "should", "will"})


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
    """A neighbor-connected group of selected chunks from one source record."""

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


def _select_evidence_hits(
    question: str,
    reranked_hits: Sequence[RetrievalHit],
    *,
    limit: int,
    selection_aspects: Sequence[str],
    coverage_hits: Sequence[RetrievalHit] = (),
) -> list[RetrievalHit]:
    """Retain ranked relevance while reserving bounded slots for aspects and sources."""

    reserved = reserve_fused_atomic_hits(
        reranked_hits,
        coverage_hits,
        selection_aspects=selection_aspects,
        limit=limit,
    )
    if reserved is not None:
        return reserved
    pool = list(reranked_hits[: max(limit * 4, limit)])
    if len(pool) <= limit:
        return pool
    targets = list(dict.fromkeys([*selection_aspects, question]))
    selected: set[int] = set()

    for target in targets:
        ranked = sorted(
            (
                (support_token_overlap(hit.text, target), index)
                for index, hit in enumerate(pool)
                if index not in selected
            ),
            key=lambda item: (-item[0], item[1]),
        )
        if ranked and ranked[0][0] >= SUPPORT_TOKEN_OVERLAP_FLOOR:
            selected.add(ranked[0][1])
        if len(selected) == limit:
            break

    selected_sources = {pool[index].source_id for index in selected}
    for index, hit in enumerate(pool):
        if len(selected) == limit:
            break
        if index in selected or hit.source_id in selected_sources:
            continue
        if (
            max(
                (support_token_overlap(hit.text, target) for target in targets),
                default=0.0,
            )
            < SUPPORT_TOKEN_OVERLAP_FLOOR
        ):
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
    coverage_hits: Sequence[RetrievalHit] = (),
) -> EvidencePacket:
    """Construct the bounded packet consumed by deterministic publication."""

    index = evidence_index or EvidenceIndex.from_chunks(chunks)
    groups: list[EvidenceGroup] = []

    selected_hits = _select_evidence_hits(
        question,
        reranked_hits,
        limit=config.max_evidence_spans,
        selection_aspects=selection_aspects,
        coverage_hits=coverage_hits,
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
