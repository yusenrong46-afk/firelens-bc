"""Integrate source-bound human decisions into the typed claim inventory."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any

import yaml

from firelens.answering.candidate_preparation import PreparedCandidateArtifact
from firelens.answering.typed_records import TypedClaimInventory

PREPARED_RELATIVE = "data/typed_claims/prepared_candidates_v2.yaml"
INVENTORY_RELATIVE = "data/typed_claims/high_risk_v1.yaml"
CORPUS_RELATIVE = "data/processed/firelens_static_corpus.chunks.jsonl"
BATCH_JOURNAL_PATTERN = "docs/reports/V1_6_TYPED_CLAIM_REVIEW_BATCH_{batch}_DECISIONS.yaml"
SPRINKLER_JOURNAL_RELATIVE = "docs/reports/V1_6_TYPED_CLAIM_REVIEW_BATCH_1_DECISIONS.yaml"
REPAIR_JOURNAL_RELATIVE = "docs/reports/V1_6_SOURCE_REPAIR_SCOPE_DECISIONS.yaml"
H8_JOURNAL_RELATIVE = "docs/reports/V1_6_H8_TRADEOFF_DECISION.yaml"


def file_sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def production_claim_id(candidate_id: str) -> str:
    if not candidate_id.startswith("PC2-"):
        raise ValueError(f"invalid prepared candidate ID {candidate_id}")
    return "TC-" + candidate_id.removeprefix("PC2-")


def build_integrated_inventory(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    prepared_path = root / PREPARED_RELATIVE
    inventory_path = root / INVENTORY_RELATIVE
    prepared = PreparedCandidateArtifact.model_validate(
        yaml.safe_load(prepared_path.read_text(encoding="utf-8"))
    )
    inventory: dict[str, Any] = yaml.safe_load(inventory_path.read_text(encoding="utf-8"))
    chunks = _load_chunks(root / CORPUS_RELATIVE)
    decisions = _load_approved_decisions(root, prepared)
    _validate_owner_gates(root)

    integrated_ids = {
        production_claim_id(row.candidate_id) for row in prepared.prepared_candidates
    }
    retained = [
        row for row in inventory["records"] if str(row["claim_id"]) not in integrated_ids
    ]
    sprinkler = next(row for row in retained if row["claim_id"] == "TC-SPRINKLER-001")
    _integrate_sprinkler(root, sprinkler)
    integrated = [
        _candidate_record(row, decisions[row.candidate_id], chunks)
        for row in prepared.prepared_candidates
    ]
    inventory["note"] = (
        "Reviewed high-risk subset only. Thomas approved the Batch 2/3 proposals and "
        "the edited SPRINKLER surface. Nine extraction defects are deferred outside "
        "V1.6. Visible development tests are not independent proof."
    )
    inventory["records"] = retained + integrated
    TypedClaimInventory.model_validate(inventory)

    decision_paths = [
        root / BATCH_JOURNAL_PATTERN.format(batch=batch.batch) for batch in prepared.batches
    ]
    decision_paths.extend(
        [
            root / SPRINKLER_JOURNAL_RELATIVE,
            root / REPAIR_JOURNAL_RELATIVE,
            root / H8_JOURNAL_RELATIVE,
        ]
    )
    manifest = {
        "schema_version": "firelens.typed_claim_rc_integration.v1",
        "prepared_artifact_sha256": file_sha256(prepared_path),
        "decision_artifact_sha256": {
            str(path.relative_to(root)): file_sha256(path) for path in decision_paths
        },
        "integrated_prepared_claim_count": len(integrated),
        "approved_sprinkler_count": 1,
        "deferred_source_repair_count": 9,
        "inventory_record_count": len(inventory["records"]),
        "candidate_to_claim_id": {
            row.candidate_id: production_claim_id(row.candidate_id)
            for row in prepared.prepared_candidates
        },
    }
    return inventory, manifest


def _load_chunks(path: Path) -> dict[str, dict[str, Any]]:
    chunks: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        chunks[str(row["chunk_id"])] = row
    return chunks


def _load_approved_decisions(
    root: Path, prepared: PreparedCandidateArtifact
) -> dict[str, dict[str, Any]]:
    decisions: dict[str, dict[str, Any]] = {}
    for batch in prepared.batches:
        path = root / BATCH_JOURNAL_PATTERN.format(batch=batch.batch)
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        rows = payload["decisions"]
        if [row["candidate_id"] for row in rows] != batch.candidate_ids:
            raise ValueError(f"Batch {batch.batch} decision IDs do not match preparation")
        for row in rows:
            if row["decision"] != "approve" or row["reviewer"] != "Thomas":
                raise ValueError(f"{row['candidate_id']} lacks Thomas approval")
            if row["production_supported"] is not False:
                raise ValueError("decision journal cannot self-enable production")
            decisions[str(row["candidate_id"])] = row
    return decisions


def _validate_owner_gates(root: Path) -> None:
    repairs = yaml.safe_load((root / REPAIR_JOURNAL_RELATIVE).read_text(encoding="utf-8"))
    repair_rows = repairs["decisions"]
    if len(repair_rows) != 9 or any(
        row["owner_scope_decision"] != "defer_out_of_scope" for row in repair_rows
    ):
        raise ValueError("source-repair scope is not closed")
    h8 = yaml.safe_load((root / H8_JOURNAL_RELATIVE).read_text(encoding="utf-8"))
    if h8.get("reviewer") != "Thomas" or h8.get("decision") != "accept_measured_tradeoff":
        raise ValueError("H8 tradeoff is not accepted")


def _integrate_sprinkler(root: Path, record: dict[str, Any]) -> None:
    journal = yaml.safe_load((root / SPRINKLER_JOURNAL_RELATIVE).read_text(encoding="utf-8"))
    final = [row for row in journal["decisions"] if row["candidate_id"] == "TC-SPRINKLER-001"][
        -1
    ]
    if final["decision"] != "approve_after_edits" or final["reviewer"] != "Thomas":
        raise ValueError("SPRINKLER lacks final edited approval")
    if final["source_document_sha256"] != record["source_document_sha256"]:
        raise ValueError("SPRINKLER document binding changed")
    if final["source_span_sha256"] != record["source_span_sha256"]:
        raise ValueError("SPRINKLER quote binding changed")
    record["canonical_text"] = final["approved_surface"]
    record["approved_surface_sha256"] = final["approved_surface_sha256"]
    record["human_review_state"] = "approved_static"


def _candidate_record(
    candidate: Any,
    decision: dict[str, Any],
    chunks: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    if decision["source_document_sha256"] != candidate.source_document_sha256:
        raise ValueError(f"{candidate.candidate_id} document binding changed")
    if decision["source_span_sha256"] != candidate.source_span_sha256:
        raise ValueError(f"{candidate.candidate_id} quote binding changed")
    if decision["approved_surface_sha256"] != candidate.proposed_surface_sha256:
        raise ValueError(f"{candidate.candidate_id} surface binding changed")
    if decision["approved_surface"] != candidate.proposed_surface:
        raise ValueError(f"{candidate.candidate_id} approved text changed")
    bound = [chunks[span_id] for span_id in candidate.source_span_ids]
    retrieved_at = {str(row["retrieved_at"]) for row in bound}
    temporal_class = {str(row["temporal_class"]) for row in bound}
    if len(retrieved_at) != 1 or len(temporal_class) != 1:
        raise ValueError(f"{candidate.candidate_id} has inconsistent corpus metadata")
    typed = candidate.typed_fields.model_dump(mode="json")
    return {
        "claim_id": production_claim_id(candidate.candidate_id),
        "risk_tier": candidate.risk_tier,
        "authority": candidate.authority,
        "jurisdiction": candidate.jurisdiction,
        **typed,
        "inclusive_exclusive": None,
        "locations": [],
        "valid_from": None,
        "valid_to": None,
        "official_source_updated_at": None,
        "firelens_retrieved_at": retrieved_at.pop(),
        "freshness": temporal_class.pop(),
        "source_span_ids": candidate.source_span_ids,
        "source_revision": candidate.source_revision,
        "binding_kind": "corpus_chunk",
        "source_document_sha256": candidate.source_document_sha256,
        "source_span_sha256": candidate.source_span_sha256,
        "approved_surface_sha256": candidate.proposed_surface_sha256,
        "human_review_state": "approved_static",
        "canonical_text": candidate.proposed_surface,
        "source_span_text": candidate.exact_source_quote,
    }
