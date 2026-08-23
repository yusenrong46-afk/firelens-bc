#!/usr/bin/env python3
"""Build the deterministic V1.6 typed-claim human-review artifact."""

from __future__ import annotations

import argparse
import json
from hashlib import sha256
from pathlib import Path

import yaml

from firelens.answering.candidate_preparation import (
    build_prepared_candidates,
    disposition_counts,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "data/typed_claims/prepared_candidates_v2.yaml"
DEFAULT_MANIFEST = ROOT / "docs/reports/V1_6_TYPED_CLAIM_PREPARATION_MANIFEST.json"
DEFAULT_REPAIR_SCOPE_TEMPLATE = ROOT / "data/typed_claims/source_repair_scope_template_v1.yaml"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument(
        "--repair-scope-template",
        type=Path,
        default=DEFAULT_REPAIR_SCOPE_TEMPLATE,
    )
    args = parser.parse_args()
    artifact = build_prepared_candidates(ROOT)
    rendered = yaml.safe_dump(
        artifact.model_dump(mode="json"),
        sort_keys=False,
        allow_unicode=True,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    repair_scope = {
        "schema_version": "firelens.typed_claim_source_repair_scope.v1",
        "raw_queue_sha256": artifact.raw_queue_sha256,
        "note": (
            "Blank owner scope template. The coding agent has made no repair or "
            "deferral decision."
        ),
        "decisions": [
            {
                "parent_candidate_id": row.parent_candidate_id,
                "current_disposition": row.disposition,
                "current_reason": row.reason,
                "owner_scope_decision": None,
                "reviewer": None,
                "decision_time": None,
                "notes": None,
            }
            for row in artifact.dispositions
            if row.disposition == "needs_source_repair"
        ],
    }
    repair_rendered = yaml.safe_dump(
        repair_scope,
        sort_keys=False,
        allow_unicode=True,
    )
    args.repair_scope_template.parent.mkdir(parents=True, exist_ok=True)
    args.repair_scope_template.write_text(repair_rendered, encoding="utf-8")
    manifest = {
        "schema_version": "firelens.typed_claim_preparation_manifest.v1",
        "artifact_sha256": sha256(rendered.encode("utf-8")).hexdigest(),
        "raw_candidate_count": len(artifact.dispositions),
        "prepared_candidate_count": len(artifact.prepared_candidates),
        "disposition_counts": disposition_counts(artifact),
        "batch_sizes": [len(batch.candidate_ids) for batch in artifact.batches],
        "review_state": "pending_review_only",
        "contains_reviewer_identity": False,
        "source_repair_scope_count": len(repair_scope["decisions"]),
        "source_repair_scope_decisions_blank": True,
        "source_repair_scope_template_sha256": sha256(
            repair_rendered.encode("utf-8")
        ).hexdigest(),
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, sort_keys=True))


if __name__ == "__main__":
    main()
