"""Versioned static claims bound to source revision and span hashes."""

from __future__ import annotations

from functools import lru_cache
from hashlib import sha256
from pathlib import Path

from firelens.answering.risk_policy import RiskTier
from firelens.answering.typed_records import TypedClaimRecord, load_inventory
from firelens.contract_base import FrozenStrictModel
from firelens.publication_contracts import RENDERER_ID
from firelens.runtime_artifact_common import RuntimeArtifactError, strict_json_loads

_INVALID_BINDINGS: dict[str, dict[str, str]] = {}
_REPO_ROOT = Path(__file__).resolve().parents[3]
_CORPUS_RELATIVE = "data/processed/firelens_static_corpus.chunks.jsonl"
_INTERNAL_STATIC_SOURCE_URLS = {
    "firelens.freshness_language.stale": "https://firelens-bc.vercel.app",
}


def normalized_sha256(text: str) -> str:
    return sha256(" ".join(text.split()).encode("utf-8")).hexdigest()


class VersionedStaticClaim(FrozenStrictModel):
    claim_id: str
    risk_tier: RiskTier
    authority: str
    jurisdiction: str
    human_review_state: str
    canonical_text: str
    source_span_text: str
    source_span_ids: list[str]
    source_revision: str
    source_revision_sha256: str
    source_span_sha256: str
    approved_surface_sha256: str
    renderer_id: str = RENDERER_ID
    canonical_url: str | None
    available_for_structured_support: bool
    record: TypedClaimRecord

    @classmethod
    def from_record(
        cls,
        record: TypedClaimRecord,
        *,
        root: str | None = None,
    ) -> VersionedStaticClaim:
        override = _INVALID_BINDINGS.get(record.claim_id, {})
        expected_revision = _expected_revision_sha(record)
        revision_sha = override.get("source_revision_sha256", expected_revision)
        span_sha = override.get(
            "source_span_sha256", normalized_sha256(record.source_span_text)
        )
        surface_sha = normalized_sha256(record.canonical_text)
        source_bound, canonical_url = _source_binding(record, root=root)
        bound = bool(
            expected_revision
            and record.source_span_sha256
            and record.approved_surface_sha256
            and revision_sha == expected_revision
            and span_sha == record.source_span_sha256
            and surface_sha == record.approved_surface_sha256
            and source_bound
            and canonical_url
        )
        return cls(
            claim_id=record.claim_id,
            risk_tier=record.risk_tier,
            authority=record.authority,
            jurisdiction=record.jurisdiction,
            human_review_state=record.human_review_state,
            canonical_text=record.canonical_text.strip(),
            source_span_text=record.source_span_text.strip(),
            source_span_ids=list(record.source_span_ids),
            source_revision=record.source_revision,
            source_revision_sha256=revision_sha,
            source_span_sha256=span_sha,
            approved_surface_sha256=surface_sha,
            canonical_url=canonical_url,
            available_for_structured_support=bool(record.production_supported() and bound),
            record=record,
        )


@lru_cache(maxsize=4)
def _authority_index(root: str | None = None) -> dict[str, VersionedStaticClaim]:
    """Build the validated claim authority index once for each loaded corpus root."""

    records = [
        VersionedStaticClaim.from_record(item, root=root)
        for item in load_inventory(root).records
    ]
    return {record.claim_id: record for record in records}


def versioned_records(*, root: str | None = None) -> list[VersionedStaticClaim]:
    return list(_authority_index(root).values())


def get_versioned(claim_id: str, *, root: str | None = None) -> VersionedStaticClaim:
    try:
        return _authority_index(root)[claim_id]
    except KeyError as exc:
        raise ValueError(f"unknown typed claim {claim_id}") from exc


def invalidate_source_binding(
    claim_id: str,
    *,
    source_span_sha256: str | None = None,
    source_revision_sha256: str | None = None,
) -> VersionedStaticClaim:
    current = _INVALID_BINDINGS.get(claim_id, {})
    if source_span_sha256:
        current["source_span_sha256"] = source_span_sha256
    if source_revision_sha256:
        current["source_revision_sha256"] = source_revision_sha256
    _INVALID_BINDINGS[claim_id] = current
    _authority_index.cache_clear()
    return get_versioned(claim_id)


def clear_authority_caches() -> None:
    """Clear inventory/corpus caches after an intentional local reload."""

    _INVALID_BINDINGS.clear()
    load_inventory.cache_clear()
    _load_corpus_chunks.cache_clear()
    _authority_index.cache_clear()


def _expected_revision_sha(record: TypedClaimRecord) -> str:
    if record.binding_kind == "internal_static":
        return normalized_sha256(record.source_revision)
    return record.source_document_sha256 or "0" * 64


@lru_cache(maxsize=4)
def _load_corpus_chunks(root: str | None = None) -> dict[str, dict[str, str]]:
    path = (Path(root) if root else _REPO_ROOT) / _CORPUS_RELATIVE
    chunks: dict[str, dict[str, str]] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        try:
            row = strict_json_loads(line, context=f"corpus authority row {line_number}")
            if not isinstance(row, dict):
                raise ValueError("corpus authority row is not an object")
            chunk_id = str(row["chunk_id"])
            text = str(row["text"])
            document_sha256 = str(row["document_sha256"])
            canonical_url = str(row["canonical_url"])
        except (KeyError, TypeError, ValueError, RuntimeArtifactError) as exc:
            raise ValueError(f"invalid corpus authority row {line_number}") from exc
        if chunk_id in chunks:
            raise ValueError(f"duplicate corpus chunk ID {chunk_id}")
        chunks[chunk_id] = {
            "text": text,
            "document_sha256": document_sha256,
            "canonical_url": canonical_url,
        }
    return chunks


def _source_binding(
    record: TypedClaimRecord,
    *,
    root: str | None,
) -> tuple[bool, str | None]:
    if record.binding_kind == "internal_static":
        urls = {_INTERNAL_STATIC_SOURCE_URLS.get(span_id) for span_id in record.source_span_ids}
        return len(urls) == 1 and None not in urls, next(iter(urls), None)
    if not record.source_document_sha256:
        return False, None
    chunks = _load_corpus_chunks(root)
    bound_chunks = [chunks.get(span_id) for span_id in record.source_span_ids]
    if not bound_chunks or any(chunk is None for chunk in bound_chunks):
        return False, None
    present_chunks = [chunk for chunk in bound_chunks if chunk is not None]
    if any(
        chunk["document_sha256"] != record.source_document_sha256 for chunk in present_chunks
    ):
        return False, None
    canonical_urls = {chunk["canonical_url"] for chunk in present_chunks}
    if len(canonical_urls) != 1 or not next(iter(canonical_urls)).startswith(
        ("http://", "https://")
    ):
        return False, None
    source_text = " ".join(record.source_span_text.split()).casefold()
    matches = any(
        source_text in " ".join(chunk["text"].split()).casefold() for chunk in present_chunks
    )
    return matches, next(iter(canonical_urls)) if matches else None
