from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import yaml

from firelens.answering.claim_integration import (
    production_claim_id,
    validate_integrated_inventory_bindings,
)
from firelens.answering.typed_records import load_inventory
from firelens.publication.records import clear_authority_caches, versioned_records

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "data/typed_claims/high_risk_v1.yaml"
MANIFEST = ROOT / "docs/reports/V1_6_RC_INTEGRATION_MANIFEST.json"


def test_checked_in_rc_inventory_is_reproducible_from_human_decisions() -> None:
    inventory = validate_integrated_inventory_bindings(ROOT)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["integrated_inventory_sha256"] == sha256(INVENTORY.read_bytes()).hexdigest()
    assert (
        manifest["prepared_artifact_sha256"]
        == sha256(
            (ROOT / "data/typed_claims/prepared_candidates_v2.yaml").read_bytes()
        ).hexdigest()
    )
    assert len(inventory.records) == 26
    assert len({record.claim_id for record in inventory.records}) == 26


def test_all_twenty_prepared_approvals_have_stable_production_ids() -> None:
    payload = yaml.safe_load(INVENTORY.read_text(encoding="utf-8"))
    claim_ids = {row["claim_id"] for row in payload["records"]}
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    assert len(manifest["candidate_to_claim_id"]) == 20
    assert set(manifest["candidate_to_claim_id"].values()) <= claim_ids
    assert all(
        claim_id == production_claim_id(candidate_id)
        for candidate_id, claim_id in manifest["candidate_to_claim_id"].items()
    )


def test_integrated_inventory_has_twenty_six_bound_supported_claims() -> None:
    clear_authority_caches()
    inventory = load_inventory()
    records = versioned_records()

    assert len(inventory.records) == 26
    assert all(record.production_supported() for record in inventory.records)
    assert len(records) == 26
    assert all(record.available_for_structured_support for record in records)
    sprinkler = next(record for record in records if record.claim_id == "TC-SPRINKLER-001")
    assert sprinkler.canonical_text == sprinkler.source_span_text
