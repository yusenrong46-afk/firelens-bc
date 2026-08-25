"""Detect approved-source changes and prepare a human review packet.

This never publishes a new corpus. Changed sources stay quarantined until an
authorized human re-admits them.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from firelens.corpus_admission import audit_corpus_admission, blocking_findings
from firelens.ingestion.pdf import sha256_file
from firelens.retrieval.bm25 import load_chunk_records
from firelens.runtime_artifact_common import strict_json_loads

MANIFEST_RELATIVE = "data/processed/firelens_static_corpus.manifest.json"
CHUNKS_RELATIVE = "data/processed/firelens_static_corpus.chunks.jsonl"


def inspect_source_changes(
    repository_root: Path,
    acquired_files: dict[str, Path],
    *,
    manifest_path: Path | None = None,
    chunks_path: Path | None = None,
) -> dict[str, Any]:
    """Compare acquired files to the approved corpus hashes. Do not publish."""

    resolved_manifest = manifest_path or repository_root / MANIFEST_RELATIVE
    manifest = strict_json_loads(
        resolved_manifest.read_text(encoding="utf-8"),
        context=f"source radar manifest {resolved_manifest}",
    )
    chunks = load_chunk_records(chunks_path or repository_root / CHUNKS_RELATIVE)
    chunks_by_source: dict[str, list[Any]] = {}
    for chunk in chunks:
        chunks_by_source.setdefault(chunk.source_id, []).append(chunk)

    changes: list[dict[str, Any]] = []
    missing_source_ids: list[str] = []
    for source in manifest.get("sources", []):
        if source.get("corpus_action") != "include":
            continue
        source_id = str(source["source_id"])
        acquired = acquired_files.get(source_id)
        if acquired is None:
            missing_source_ids.append(source_id)
            continue
        current_hash = sha256_file(acquired)
        approved_hash = str(source["document_sha256"])
        if current_hash == approved_hash:
            continue
        affected = chunks_by_source.get(source_id, [])
        findings = audit_corpus_admission(affected)
        changes.append(
            {
                "source_id": source_id,
                "approved_sha256": approved_hash,
                "acquired_sha256": current_hash,
                "affected_chunk_ids": [chunk.chunk_id for chunk in affected],
                "affected_chunk_count": len(affected),
                "admission_findings": [finding.as_dict() for finding in findings],
                "blocking_findings": [
                    finding.as_dict() for finding in blocking_findings(findings)
                ],
                "publication": "blocked",
                "next_step": "human_review_then_authorized_readmission",
            }
        )
    return {
        "schema_version": "firelens.source_change_radar.v1",
        "auto_publish": False,
        "changed_source_count": len(changes),
        "changes": changes,
        "missing_source_ids": missing_source_ids,
        "scan_complete": not missing_source_ids,
        "quarantine_recommended": bool(changes or missing_source_ids),
    }


def write_review_packet(report: dict[str, Any], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return output_path
