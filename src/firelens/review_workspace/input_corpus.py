"""Strict governed-corpus input validation for the review workspace.

This module owns the admission-aware corpus boundary.  It is intentionally
separate from :mod:`inputs` so the public review-import facade remains small
without making the manifest contract less strict.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from firelens.corpus_admission import ADMISSION_POLICY_VERSION
from firelens.review_workspace.input_common import (
    CHUNK_KEYS,
    InputFileIdentity,
    ReviewInputError,
    _content,
    _digest,
    _duplicate_rejecting_object,
    _exact_keys,
    _nonempty,
    _read_bound_file,
    _reject_constant,
    _timestamp,
)


def read_governed_chunks(
    path: Path,
) -> tuple[dict[str, dict[str, Any]], InputFileIdentity, dict[str, int]]:
    """Read only complete, current governed chunks from an identity-bound file."""

    raw, identity = _read_bound_file(path, "governed_corpus")
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise ReviewInputError("governed corpus must be UTF-8 JSONL") from exc
    chunks: dict[str, dict[str, Any]] = {}
    counts: dict[str, int] = {}
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(
                line,
                object_pairs_hook=_duplicate_rejecting_object,
                parse_constant=_reject_constant,
            )
        except (json.JSONDecodeError, ValueError) as exc:
            raise ReviewInputError(
                f"invalid governed corpus record at line {line_number}"
            ) from exc
        chunk = _exact_keys(value, CHUNK_KEYS, f"governed corpus line {line_number}")
        if chunk.get("schema_version") != "chunk_record.v2":
            raise ReviewInputError("governed corpus chunk version is unsupported")
        chunk_id = _nonempty(chunk.get("chunk_id"), "governed chunk ID")
        if chunk_id in chunks:
            raise ReviewInputError("governed corpus repeats chunk IDs")
        text = _content(chunk.get("text"), "governed chunk text")
        if type(chunk.get("char_count")) is not int or chunk["char_count"] != len(text):
            raise ReviewInputError("governed corpus char_count is inconsistent")
        _digest(chunk.get("document_sha256"), "governed chunk document digest")
        _timestamp(chunk.get("retrieved_at"), "governed chunk retrieved_at")
        if chunk.get("review_provenance") not in {"native_text", "human_verified_repair"}:
            raise ReviewInputError("governed chunk has unsupported review provenance")
        source_id = _nonempty(chunk.get("source_id"), "governed chunk source ID")
        counts[source_id] = counts.get(source_id, 0) + 1
        chunks[chunk_id] = chunk
    if not chunks:
        raise ReviewInputError("governed corpus has no chunks")
    return chunks, identity, counts


def validate_governed_corpus_manifest(
    manifest: dict[str, Any],
    *,
    corpus_path: Path,
    chunks: dict[str, dict[str, Any]],
    source_counts: dict[str, int],
) -> None:
    """Validate both legacy synthetic and current admission-aware manifests."""

    expected = {
        "combined_chunk_count",
        "combined_chunk_file",
        "corpus_version",
        "generated_at",
        "included_source_count",
        "registry_version",
        "repair_provenance_policy",
        "sources",
    }
    admission_fields = {
        "admission_policy_version",
        "admission_warnings",
        "quarantined_pages",
    }
    present_admission_fields = admission_fields.intersection(manifest)
    if present_admission_fields and present_admission_fields != admission_fields:
        raise ReviewInputError("governed corpus manifest has an incomplete admission schema")
    expected.update(present_admission_fields)
    if "provenance_migrated_at" in manifest:
        expected.add("provenance_migrated_at")
    _exact_keys(manifest, expected, "governed corpus manifest")
    _nonempty(manifest.get("corpus_version"), "corpus version")
    _timestamp(manifest.get("generated_at"), "corpus generated_at")
    if "provenance_migrated_at" in manifest:
        _timestamp(manifest.get("provenance_migrated_at"), "corpus provenance_migrated_at")
    if manifest.get("repair_provenance_policy") != "human_verified_only.v1":
        raise ReviewInputError("corpus manifest lacks the governed repair policy")
    if present_admission_fields:
        if manifest.get("admission_policy_version") != ADMISSION_POLICY_VERSION:
            raise ReviewInputError("corpus manifest has an unsupported admission policy")
        _validate_admission_warnings(manifest["admission_warnings"], chunks)
        _validate_quarantined_pages(manifest["quarantined_pages"], chunks)
    if type(manifest.get("combined_chunk_count")) is not int or manifest[
        "combined_chunk_count"
    ] != len(chunks):
        raise ReviewInputError("corpus manifest chunk count is inconsistent")
    declared_file = _nonempty(manifest.get("combined_chunk_file"), "combined chunk file")
    if Path(declared_file).name != corpus_path.name:
        raise ReviewInputError("corpus manifest names a different chunk file")
    sources = manifest.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ReviewInputError("corpus manifest has no source registry")
    governed: dict[str, dict[str, Any]] = {}
    for index, source_value in enumerate(sources):
        if not isinstance(source_value, dict):
            raise ReviewInputError(f"corpus manifest source {index} must be an object")
        source_id = _nonempty(source_value.get("source_id"), "manifest source ID")
        action = source_value.get("corpus_action")
        if action not in {"include", "include_quote_only"}:
            continue
        required = {
            "canonical_url",
            "chunk_count",
            "corpus_action",
            "document_sha256",
            "excluded_record_count",
            "local_file",
            "record_count",
            "review_status",
            "source_id",
            "source_type",
        }
        _exact_keys(source_value, required, f"included corpus source {index}")
        expected_review_status = (
            "approved_static" if action == "include" else "approved_quote_only"
        )
        if source_value.get("review_status") != expected_review_status:
            raise ReviewInputError("included corpus source is not approved static evidence")
        _digest(source_value.get("document_sha256"), "manifest source document digest")
        if type(source_value.get("chunk_count")) is not int:
            raise ReviewInputError("manifest source chunk_count must be an integer")
        governed[source_id] = source_value
    if type(manifest.get("included_source_count")) is not int or manifest[
        "included_source_count"
    ] != len(governed):
        raise ReviewInputError("corpus manifest included-source count is inconsistent")
    if set(source_counts) != set(governed):
        raise ReviewInputError("governed corpus source roster differs from its manifest")
    for source_id, count in source_counts.items():
        source = governed[source_id]
        if source["chunk_count"] != count:
            raise ReviewInputError("governed corpus per-source count is inconsistent")
        document_hashes = {
            chunk["document_sha256"]
            for chunk in chunks.values()
            if chunk["source_id"] == source_id
        }
        if document_hashes != {source["document_sha256"]}:
            raise ReviewInputError("governed corpus source digest differs from its manifest")


def _validate_admission_warnings(value: Any, chunks: dict[str, dict[str, Any]]) -> None:
    if not isinstance(value, list):
        raise ReviewInputError("corpus admission warnings must be a list")
    expected = {"source_id", "chunk_id", "code", "detail", "blocking"}
    seen: set[tuple[str, str | None, str, str]] = set()
    for index, warning in enumerate(value, start=1):
        context = f"corpus admission warning {index}"
        _exact_keys(warning, expected, context)
        source_id = _nonempty(warning.get("source_id"), f"{context} source ID")
        chunk_id = warning.get("chunk_id")
        if chunk_id is not None and not isinstance(chunk_id, str):
            raise ReviewInputError(f"{context} chunk ID is invalid")
        if chunk_id is not None:
            chunk = chunks.get(chunk_id)
            if chunk is None or chunk.get("source_id") != source_id:
                raise ReviewInputError(f"{context} does not bind an admitted chunk")
        elif not any(chunk.get("source_id") == source_id for chunk in chunks.values()):
            raise ReviewInputError(f"{context} does not bind an admitted source")
        code = _nonempty(warning.get("code"), f"{context} code")
        detail = _nonempty(warning.get("detail"), f"{context} detail")
        if warning.get("blocking") is not False:
            raise ReviewInputError(f"{context} must remain non-blocking")
        identity = (source_id, chunk_id, code, detail)
        if identity in seen:
            raise ReviewInputError("corpus admission warnings contain duplicates")
        seen.add(identity)


def _validate_quarantined_pages(value: Any, chunks: dict[str, dict[str, Any]]) -> None:
    if not isinstance(value, list):
        raise ReviewInputError("corpus quarantined pages must be a list")
    expected = {"source_id", "page_number", "document_sha256", "review_status", "reason"}
    source_documents = {
        (str(chunk["source_id"]), str(chunk["document_sha256"])) for chunk in chunks.values()
    }
    seen: set[tuple[str, int, str]] = set()
    for index, page in enumerate(value, start=1):
        context = f"corpus quarantined page {index}"
        _exact_keys(page, expected, context)
        source_id = _nonempty(page.get("source_id"), f"{context} source ID")
        page_number = page.get("page_number")
        if isinstance(page_number, bool) or not isinstance(page_number, int) or page_number < 1:
            raise ReviewInputError(f"{context} page number is invalid")
        digest = page.get("document_sha256")
        _digest(digest, f"{context} document digest")
        if (source_id, digest) not in source_documents:
            raise ReviewInputError(f"{context} does not bind a governed source revision")
        if page.get("review_status") not in {
            "pending_owner_review",
            "automated_visual_reviewed",
        }:
            raise ReviewInputError(f"{context} review status is invalid")
        if not isinstance(page.get("reason"), str) or not page["reason"].strip():
            raise ReviewInputError(f"{context} reason is invalid")
        target = (source_id, page_number, digest)
        if target in seen:
            raise ReviewInputError("corpus quarantined pages contain duplicates")
        if any(
            chunk.get("source_id") == source_id
            and chunk.get("page_number") == page_number
            and chunk.get("document_sha256") == digest
            for chunk in chunks.values()
        ):
            raise ReviewInputError(f"{context} remains in the admitted corpus")
        seen.add(target)
