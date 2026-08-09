"""Deterministic admission checks for untrusted static-corpus chunks.

Source-registry approval and file hashes establish provenance, but they do not
make the extracted text safe instructions for a model.  This module performs a
second, content-level admission pass and reports source-level findings so a
caller can either fail the build or quarantine a rejected source.
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from firelens.ingestion.chunking import ChunkRecord

ADMISSION_POLICY_VERSION = "firelens_corpus_admission.v1"
MAX_ADMITTED_CHUNK_CHARS = 4_000

_INSTRUCTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "model_instruction",
        re.compile(
            r"\b(?:system|developer|assistant)\s+(?:override|instruction|message)s?\b",
            re.IGNORECASE,
        ),
    ),
    (
        "policy_override",
        re.compile(
            r"\bignore\s+(?:all\s+|any\s+)?(?:previous|prior|system|developer)\s+"
            r"(?:instructions|rules|messages)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "assistant_directive",
        re.compile(
            r"\b(?:for|to)\s+(?:the\s+)?(?:assistant|language model|chatbot|ai)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "citation_fabrication",
        re.compile(
            r"\b(?:invent|fabricate|fake|make\s+up)\b.{0,100}"
            r"\b(?:citation|source|url|evidence)\b",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "authority_suppression",
        re.compile(r"\bdo\s+not\s+cite\b", re.IGNORECASE),
    ),
)

_TOKEN = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class AdmissionFinding:
    source_id: str
    chunk_id: str | None
    code: str
    detail: str
    blocking: bool = True

    def as_dict(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "chunk_id": self.chunk_id,
            "code": self.code,
            "detail": self.detail,
            "blocking": self.blocking,
        }


def _source_shingles(chunks: Sequence[ChunkRecord]) -> set[str]:
    tokens = _TOKEN.findall(" ".join(chunk.text for chunk in chunks).casefold())
    return {
        hashlib.sha256(" ".join(tokens[index : index + 5]).encode()).hexdigest()
        for index in range(max(0, len(tokens) - 4))
    }


def audit_corpus_admission(chunks: Sequence[ChunkRecord]) -> list[AdmissionFinding]:
    """Return deterministic blocking findings and review-only duplicate warnings."""

    findings: list[AdmissionFinding] = []
    chunks_by_source: dict[str, list[ChunkRecord]] = defaultdict(list)
    source_by_document_hash: dict[str, set[str]] = defaultdict(set)
    seen_chunk_ids: set[str] = set()

    for chunk in chunks:
        chunks_by_source[chunk.source_id].append(chunk)
        source_by_document_hash[chunk.document_sha256].add(chunk.source_id)
        findings.extend(
            _chunk_admission_findings(chunk, duplicate=chunk.chunk_id in seen_chunk_ids)
        )
        seen_chunk_ids.add(chunk.chunk_id)
    findings.extend(_duplicate_document_findings(source_by_document_hash))
    source_shingles = {
        source_id: _source_shingles(source_chunks)
        for source_id, source_chunks in chunks_by_source.items()
    }
    findings.extend(_near_duplicate_findings(source_shingles))
    return findings


def _finding(chunk: ChunkRecord, code: str, detail: str) -> AdmissionFinding:
    return AdmissionFinding(
        source_id=chunk.source_id, chunk_id=chunk.chunk_id, code=code, detail=detail
    )


def _chunk_admission_findings(chunk: ChunkRecord, *, duplicate: bool) -> list[AdmissionFinding]:
    findings: list[AdmissionFinding] = []
    checks = (
        (duplicate, "duplicate_chunk_id", "A chunk ID occurs more than once in the corpus."),
        (
            chunk.source_type not in {"pdf", "html"},
            "unsupported_source_type",
            f"Unsupported source type: {chunk.source_type}",
        ),
        (
            not chunk.text.strip() or chunk.char_count != len(chunk.text),
            "malformed_extraction",
            "Chunk text is blank or its declared character count is invalid.",
        ),
        (
            len(chunk.text) > MAX_ADMITTED_CHUNK_CHARS,
            "pathological_chunk_size",
            f"Chunk exceeds the {MAX_ADMITTED_CHUNK_CHARS}-character admission ceiling.",
        ),
        (
            not re.fullmatch(r"[a-f0-9]{64}", chunk.document_sha256),
            "invalid_document_hash",
            "Document SHA-256 is missing or malformed.",
        ),
        (
            not chunk.authority_class,
            "missing_authority",
            "Chunk has no governed authority class.",
        ),
    )
    findings.extend(_finding(chunk, code, detail) for failed, code, detail in checks if failed)
    findings.extend(
        _finding(
            chunk,
            code,
            "Untrusted source text contains a model-facing instruction or citation manipulation pattern.",
        )
        for code, pattern in _INSTRUCTION_PATTERNS
        if pattern.search(chunk.text)
    )
    return findings


def _duplicate_document_findings(
    sources_by_hash: dict[str, set[str]],
) -> list[AdmissionFinding]:
    return [
        AdmissionFinding(
            source_id=source_id,
            chunk_id=None,
            code="duplicate_document",
            detail=f"The same reviewed document hash is registered under multiple sources: {document_hash}.",
        )
        for document_hash, source_ids in sources_by_hash.items()
        if len(source_ids) >= 2
        for source_id in sorted(source_ids)
    ]


def _near_duplicate_findings(source_shingles: dict[str, set[str]]) -> list[AdmissionFinding]:
    findings: list[AdmissionFinding] = []
    ordered_source_ids = sorted(source_shingles)
    for index, left_id in enumerate(ordered_source_ids):
        left = source_shingles[left_id]
        if len(left) < 20:
            continue
        for right_id in ordered_source_ids[index + 1 :]:
            right = source_shingles[right_id]
            if len(right) < 20:
                continue
            similarity = len(left & right) / max(1, len(left | right))
            if similarity < 0.92:
                continue
            # Near-duplicates are retained for version/conflict handling, but the
            # warning makes the admission decision explicit and reviewable.
            for source_id in (left_id, right_id):
                findings.append(
                    AdmissionFinding(
                        source_id=source_id,
                        chunk_id=None,
                        code="near_duplicate_source",
                        detail=(
                            f"Source is {similarity:.1%} textually similar to "
                            f"{right_id if source_id == left_id else left_id}; review version "
                            "and conflict metadata."
                        ),
                        blocking=False,
                    )
                )
    return findings


def blocking_findings(findings: Sequence[AdmissionFinding]) -> list[AdmissionFinding]:
    return [finding for finding in findings if finding.blocking]


def quarantine_rejected_sources(
    chunks: Sequence[ChunkRecord],
) -> tuple[list[ChunkRecord], list[AdmissionFinding]]:
    """Remove whole sources with blocking findings; never keep partial documents."""

    findings = audit_corpus_admission(chunks)
    rejected_source_ids = {finding.source_id for finding in findings if finding.blocking}
    return (
        [chunk for chunk in chunks if chunk.source_id not in rejected_source_ids],
        findings,
    )
