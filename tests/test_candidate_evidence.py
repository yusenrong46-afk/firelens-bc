from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from firelens.evaluation import candidate_evidence_documents, productbench_v2_report
from firelens.evaluation.candidate_evidence_common import MATERIAL_PATHS
from firelens.evaluation.candidate_evidence_validation import validate_workflow_identity
from firelens.evaluation.common import file_sha256
from firelens.evaluation.release_promotion import (
    MANIFEST_RELATIVE,
    promotion_manifest_document,
    promotion_material_record,
)
from firelens.evaluation.v1_6_2_patch_promotion import (
    MANIFEST_RELATIVE as PATCH_MANIFEST_RELATIVE,
)
from firelens.evaluation.v1_6_standard import STANDARD_RELATIVE
from scripts.candidate_evidence import (
    REQUIRED_COMMAND_POLICIES,
    SCHEMA_VERSION,
    SUBJECT_FILE,
    SUBJECT_TREE,
    build_candidate_evidence,
    verify_candidate_evidence,
)

COMMIT = "a" * 40
TREE = "b" * 40
GENERATED_AT = "2026-08-23T20:00:00+00:00"
RC2_MIGRATED_IDS = (
    "A04",
    "A05",
    "A07",
    "A08",
    "A09",
    "A10",
    "I01",
    "I02",
    "J01",
    "J02",
)
MIGRATED_IDS = (*RC2_MIGRATED_IDS, "A01")
STRUCTURED_TWO_SIDED_IDS = {"A09", "A10"}
QUOTE_ONLY_IDS = set(RC2_MIGRATED_IDS) - {"J01"} - STRUCTURED_TWO_SIDED_IDS
RC2_QUOTE_ONLY_IDS = set(RC2_MIGRATED_IDS) - {"J01"}
CASE_IDS = [*MIGRATED_IDS, *(f"HP-{index:03d}" for index in range(94))]
OFFICIAL_HANDOFF_ANSWER = (
    "FireLens does not have a reviewed structured claim for this high-risk question. "
    "Use the issuing authority for official wording."
)
LIMITATIONS = [
    "Exact-main qualification remains a separate human-authorized gate.",
    "Paid H4/H8 evidence is not part of this zero-cost candidate bundle.",
    "Preview, accessibility, participant review, and release GO remain separate gates.",
]


def _write(path: Path, value: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, bytes):
        path.write_bytes(value)
    else:
        path.write_text(value, encoding="utf-8")


def _json(path: Path, value: object) -> None:
    _write(path, json.dumps(value) + "\n")


def _fixture_material_sha(relative: str) -> str:
    return hashlib.sha256(f"fixture:{relative}\n".encode()).hexdigest()


def _migration(case_id: str, *, profile: str = "rc2.2") -> dict[str, object]:
    two_sided = profile == "rc2.2" and case_id in STRUCTURED_TWO_SIDED_IDS
    quote_only = case_id in RC2_QUOTE_ONLY_IDS and not two_sided
    mixed = case_id == "A01"
    rationale = (
        "Accept the deterministic two-sided structured_reviewed coverage of the reviewed "
        "evacuation-alert and evacuation-order claims."
        if two_sided
        else "Accept the deterministic official-quote-only downgrade required by structured "
        "publication."
        if quote_only
        else "Accept the deterministic mixed reviewed-claim and exact-official-quote "
        "response for the requested grab-and-go contents."
        if mixed
        else "Accept the deterministic official issuing-authority handoff when no reviewed "
        "structured claim is available."
    )
    return {
        "id": case_id,
        "add_allowed_modes": [
            "partial" if quote_only or mixed or two_sided else "scope_redirect"
        ],
        "required_publication_kinds": (
            ["structured_reviewed"]
            if two_sided
            else ["official_quote_only"]
            if quote_only
            else ["structured_reviewed", "official_quote_only"]
            if mixed
            else []
        ),
        "require_validation_accepted": quote_only or mixed or two_sided,
        "require_exact_quote_support": quote_only or mixed or two_sided,
        "require_zero_generation": True,
        "require_zero_claims": not quote_only and not mixed and not two_sided,
        "require_zero_evidence": not quote_only and not mixed and not two_sided,
        "require_official_handoff": not quote_only and not mixed and not two_sided,
        "required_reason_code": (
            None if quote_only or two_sided else "high_risk_claim_not_structured"
        ),
        "rationale": rationale,
    }


RC2_MIGRATIONS = [_migration(case_id, profile="rc2") for case_id in RC2_MIGRATED_IDS]
RC2_1_MIGRATIONS = [_migration(case_id, profile="rc2.1") for case_id in MIGRATED_IDS]
MIGRATIONS = [_migration(case_id, profile="rc2.2") for case_id in MIGRATED_IDS]
MIGRATION_BY_ID = {str(item["id"]): item for item in MIGRATIONS}
BASE_DATASET = {
    "dataset_version": "hard_probe.v1",
    "description": "candidate-evidence fixture",
    "cases": [
        {
            "id": case_id,
            "section": "A",
            "question": f"Fixture question {case_id}",
            "expected_text": "fixture",
            "priority": "HIGH",
            "history": [],
            "allowed_modes": ["grounded"],
        }
        for case_id in CASE_IDS
    ],
    "browser_cases": [],
    "fixture_cases": [],
}
BASE_DATASET_BYTES = yaml.safe_dump(BASE_DATASET, sort_keys=False).encode()
BASE_DATASET_SHA256 = hashlib.sha256(BASE_DATASET_BYTES).hexdigest()
PROFILE = {
    "schema_version": "firelens.hard_probe_expectations.v1",
    "profile": "rc2.2",
    "base_dataset_sha256": BASE_DATASET_SHA256,
    "minimum_passed": 86,
    "migrations": MIGRATIONS,
}
PROFILE_BYTES = yaml.safe_dump(PROFILE, sort_keys=False).encode()
PROFILE_SHA256 = hashlib.sha256(PROFILE_BYTES).hexdigest()
RC2_PROFILE = {
    "schema_version": "firelens.hard_probe_expectations.v1",
    "profile": "rc2",
    "base_dataset_sha256": BASE_DATASET_SHA256,
    "minimum_passed": 86,
    "migrations": RC2_MIGRATIONS,
}
RC2_PROFILE_BYTES = yaml.safe_dump(RC2_PROFILE, sort_keys=False).encode()
RC2_PROFILE_SHA256 = hashlib.sha256(RC2_PROFILE_BYTES).hexdigest()
RC2_1_PROFILE = {
    "schema_version": "firelens.hard_probe_expectations.v1",
    "profile": "rc2.1",
    "base_dataset_sha256": BASE_DATASET_SHA256,
    "minimum_passed": 86,
    "migrations": RC2_1_MIGRATIONS,
}
RC2_1_PROFILE_BYTES = yaml.safe_dump(RC2_1_PROFILE, sort_keys=False).encode()
RC2_1_PROFILE_SHA256 = hashlib.sha256(RC2_1_PROFILE_BYTES).hexdigest()
EFFECTIVE_EXPECTATIONS = {
    "schema_version": "firelens.hard_probe_effective_expectations.v1",
    "profile": "rc2.2",
    "base_dataset_sha256": BASE_DATASET_SHA256,
    "minimum_passed": 86,
    "cases": [
        {
            "id": case_id,
            "allowed_modes": [
                "grounded",
                *(
                    ["partial" if case_id != "J01" else "scope_redirect"]
                    if case_id in MIGRATED_IDS
                    else []
                ),
            ],
            "migration": MIGRATION_BY_ID.get(case_id),
        }
        for case_id in CASE_IDS
    ],
}
EFFECTIVE_EXPECTATIONS_SHA256 = hashlib.sha256(
    json.dumps(
        EFFECTIVE_EXPECTATIONS,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
).hexdigest()
PRODUCTBENCH_IDS = ["PB-04", "PB-05"]
PRODUCTBENCH_CATALOG = {
    "schema_version": "firelens.productbench_journeys.v1",
    "catalog_id": "fixture-productbench",
    "case_count": len(PRODUCTBENCH_IDS),
    "status": "development_unsealed",
    "cases": [{"id": case_id} for case_id in PRODUCTBENCH_IDS],
}
PRODUCTBENCH_CATALOG_BYTES = (json.dumps(PRODUCTBENCH_CATALOG) + "\n").encode()
PRODUCTBENCH_CATALOG_SHA256 = hashlib.sha256(PRODUCTBENCH_CATALOG_BYTES).hexdigest()
PRODUCTBENCH_MANIFEST = {
    "schema_version": "firelens.productbench_manifest.v2",
    "raw_catalog_sha256": PRODUCTBENCH_CATALOG_SHA256,
    "contract_sha256": "c" * 64,
    "executable_catalog_sha256": "d" * 64,
    "status": "development_unsealed",
    "tiers": {"offline_fake": PRODUCTBENCH_IDS, "provider_manual": []},
}
PRODUCTBENCH_MANIFEST_BYTES = (json.dumps(PRODUCTBENCH_MANIFEST) + "\n").encode()
PRODUCTBENCH_MANIFEST_SHA256 = hashlib.sha256(PRODUCTBENCH_MANIFEST_BYTES).hexdigest()


def _passing_invariants(names: list[str]) -> list[dict[str, object]]:
    return [{"name": name, "expected": True, "actual": True, "passed": True} for name in names]


def _quote_only_result(case_id: str) -> dict[str, object]:
    return {
        "id": case_id,
        "passed": True,
        "cost_usd": 0.0,
        "response_mode": "partial",
        "validation_status": "accepted",
        "provider_stages": [],
        "effective_allowed_modes": ["grounded", "partial"],
        "applied_migration": MIGRATION_BY_ID[case_id],
        "semantic_checks": {
            "base_issues": [],
            "migration_invariants": _passing_invariants(
                [
                    "at_least_one_claim",
                    "at_least_one_evidence",
                    "required_publication_kinds",
                    "validation_accepted",
                    "exact_quote_support",
                    "zero_generation_attempts",
                    "zero_generation_cost_usd",
                ]
            ),
        },
        "response": {
            "status": "answer",
            "response_mode": "partial",
            "answer": "Exact official wording.",
            "reason_code": "high_risk_claim_not_structured",
            "claims": [
                {
                    "claim_id": "C1",
                    "text": "Exact official wording.",
                    "evidence_status": "verified_corpus",
                    "supports": [{"evidence_id": "E1", "quote": "Exact official wording."}],
                    "publication": {"kind": "official_quote_only"},
                }
            ],
            "evidence": [{"evidence_id": "E1", "primary_text": "Exact official wording."}],
        },
    }


def _structured_two_sided_result(case_id: str) -> dict[str, object]:
    return {
        "id": case_id,
        "passed": True,
        "cost_usd": 0.0,
        "response_mode": "grounded",
        "validation_status": "accepted",
        "provider_stages": [],
        "effective_allowed_modes": ["grounded", "partial"],
        "applied_migration": MIGRATION_BY_ID[case_id],
        "semantic_checks": {
            "base_issues": [],
            "migration_invariants": _passing_invariants(
                [
                    "at_least_one_claim",
                    "at_least_one_evidence",
                    "required_publication_kinds",
                    "validation_accepted",
                    "exact_quote_support",
                    "zero_generation_attempts",
                    "zero_generation_cost_usd",
                ]
            ),
        },
        "response": {
            "status": "answer",
            "response_mode": "grounded",
            "answer": "Reviewed alert and order wording.",
            "reason_code": None,
            "validation": {"accepted": True},
            "claims": [
                {
                    "claim_id": "C1",
                    "text": "Leave immediately.",
                    "evidence_status": "verified_corpus",
                    "supports": [{"evidence_id": "E1", "quote": "leave immediately"}],
                    "publication": {
                        "kind": "structured_reviewed",
                        "typed_claim_id": "TC-EVAC-ORDER-001",
                    },
                },
                {
                    "claim_id": "C2",
                    "text": "Be ready on short notice.",
                    "evidence_status": "verified_corpus",
                    "supports": [{"evidence_id": "E2", "quote": "short notice"}],
                    "publication": {
                        "kind": "structured_reviewed",
                        "typed_claim_id": "TC-EVAC-ALERT-001",
                    },
                },
            ],
            "evidence": [
                {"evidence_id": "E1", "primary_text": "You must leave immediately."},
                {"evidence_id": "E2", "primary_text": "Be ready to leave on short notice."},
            ],
        },
    }


def _mixed_result() -> dict[str, object]:
    return {
        "id": "A01",
        "passed": True,
        "cost_usd": 0.0,
        "response_mode": "partial",
        "validation_status": "accepted",
        "provider_stages": [],
        "effective_allowed_modes": ["grounded", "partial"],
        "applied_migration": MIGRATION_BY_ID["A01"],
        "semantic_checks": {
            "base_issues": [],
            "migration_invariants": _passing_invariants(
                [
                    "at_least_one_claim",
                    "at_least_one_evidence",
                    "required_publication_kinds",
                    "validation_accepted",
                    "exact_quote_support",
                    "zero_generation_attempts",
                    "zero_generation_cost_usd",
                    "required_reason_code",
                ]
            ),
        },
        "response": {
            "status": "answer",
            "response_mode": "partial",
            "answer": "Reviewed preparation plus exact official contents.",
            "reason_code": "high_risk_claim_not_structured",
            "validation": {"accepted": True},
            "claims": [
                {
                    "claim_id": "C1",
                    "supports": [{"evidence_id": "E1", "quote": "Reviewed wording."}],
                    "publication": {"kind": "structured_reviewed"},
                },
                {
                    "claim_id": "C2",
                    "supports": [{"evidence_id": "E2", "quote": "Official wording."}],
                    "publication": {"kind": "official_quote_only"},
                },
            ],
            "evidence": [
                {"evidence_id": "E1", "primary_text": "Reviewed wording."},
                {"evidence_id": "E2", "primary_text": "Official wording."},
            ],
        },
    }


def _handoff_result() -> dict[str, object]:
    return {
        "id": "J01",
        "passed": True,
        "cost_usd": 0.0,
        "response_mode": "scope_redirect",
        "validation_status": None,
        "provider_stages": [],
        "effective_allowed_modes": ["grounded", "scope_redirect"],
        "applied_migration": MIGRATION_BY_ID["J01"],
        "semantic_checks": {
            "base_issues": [],
            "migration_invariants": _passing_invariants(
                [
                    "zero_generation_attempts",
                    "zero_generation_cost_usd",
                    "zero_claims",
                    "zero_evidence",
                    "official_handoff",
                    "required_reason_code",
                ]
            ),
        },
        "response": {
            "status": "answer",
            "response_mode": "scope_redirect",
            "answer": OFFICIAL_HANDOFF_ANSWER,
            "reason_code": "high_risk_claim_not_structured",
            "claims": [],
            "evidence": [],
        },
    }


def _hard_probe(
    *, commit: str = COMMIT, tree: str = TREE, passed_ids: set[str] | None = None
) -> dict[str, object]:
    passing = passed_ids if passed_ids is not None else set(CASE_IDS[:86])
    results: list[dict[str, object]] = []
    for case_id in CASE_IDS:
        if case_id in QUOTE_ONLY_IDS:
            row = _quote_only_result(case_id)
        elif case_id in STRUCTURED_TWO_SIDED_IDS:
            row = _structured_two_sided_result(case_id)
        elif case_id == "A01":
            row = _mixed_result()
        elif case_id == "J01":
            row = _handoff_result()
        else:
            row = {
                "id": case_id,
                "passed": case_id in passing,
                "cost_usd": 0.0,
                "response_mode": "grounded",
                "validation_status": "accepted",
                "provider_stages": [],
                "effective_allowed_modes": ["grounded"],
                "applied_migration": None,
                "semantic_checks": {"base_issues": [], "migration_invariants": []},
                "response": {},
            }
        row["passed"] = case_id in passing
        results.append(row)
    return {
        "schema_version": "firelens_hard_probe_report.v2",
        "manifest": {
            "commit": commit,
            "tree": tree,
            "mode": "offline",
            "provider_boundary": "offline_double",
            "dataset_sha256": BASE_DATASET_SHA256,
            "expectation_profile": "rc2.2",
            "expectation_overlay_sha256": PROFILE_SHA256,
            "effective_expectations_sha256": EFFECTIVE_EXPECTATIONS_SHA256,
            "corpus_sha256": _fixture_material_sha(
                "data/processed/firelens_static_corpus.chunks.jsonl"
            ),
            "corpus_manifest_sha256": _fixture_material_sha(
                "data/processed/firelens_static_corpus.manifest.json"
            ),
            "vector_matrix_sha256": _fixture_material_sha("data/index/firelens_vectors.npy"),
            "vector_manifest_sha256": _fixture_material_sha(
                "data/index/firelens_vectors.manifest.json"
            ),
        },
        "summary": {
            "executed": 105,
            "passed": len(passing),
            "failed": 105 - len(passing),
            "minimum_passed": 86,
            "minimum_passed_met": len(passing) >= 86,
            "cost_usd": 0.0,
        },
        "results": results,
    }


def _baseline_hard_probe(*, passed_ids: set[str] | None = None) -> dict[str, object]:
    passing = passed_ids if passed_ids is not None else set(CASE_IDS[:86])
    return {
        "schema_version": "firelens_hard_probe_report.v1",
        "manifest": {},
        "summary": {
            "executed": 105,
            "passed": len(passing),
            "failed": 105 - len(passing),
            "cost_usd": 0.0,
        },
        "results": [{"id": case_id, "passed": case_id in passing} for case_id in CASE_IDS],
    }


def _productbench_deterministic(*, tree: str = TREE) -> dict[str, object]:
    return {
        "schema_version": "firelens.productbench_report.v2",
        "generated_at": GENERATED_AT,
        "identity": {
            "commit": COMMIT,
            "tree": tree,
            "catalog_path": "data/evaluation/productbench_journeys_50.json",
            "manifest_path": "data/evaluation/productbench_v2.manifest.json",
            "raw_catalog_sha256": PRODUCTBENCH_CATALOG_SHA256,
            "manifest_sha256": PRODUCTBENCH_MANIFEST_SHA256,
            "contract_sha256": "c" * 64,
            "executable_catalog_sha256": "d" * 64,
            "schema_version": "firelens.productbench_manifest.v2",
            "tier": "offline_fake",
            "status": "development_unsealed",
            "case_ids": PRODUCTBENCH_IDS,
            "git_clean": True,
            "status_sha256": hashlib.sha256(b"").hexdigest(),
            "tracked_diff_sha256": hashlib.sha256(b"").hexdigest(),
            "untracked_content_sha256": hashlib.sha256(b"[]").hexdigest(),
            "untracked_file_count": 0,
        },
        "provider_boundary": "offline_fake",
        "execution_complete": True,
        "passed": len(PRODUCTBENCH_IDS),
        "failed": 0,
        "case_count": len(PRODUCTBENCH_IDS),
        "cost": {
            "max_cost_usd": 0.0,
            "reported_cost_usd": 0.0,
            "ceiling_exceeded": False,
        },
        # This is the report shape emitted by productbench_v2_report.build(),
        # including the canonical activity counters added in ProductBench v2.
        # Candidate evidence must bind it rather than reject a complete offline
        # run for carrying the report's required provenance.
        "provider_activity": {
            "call_counts": {
                "plan": 2,
                "embed": 9,
                "rerank": 9,
                "generate": 2,
                "generate_grounded": 0,
                "generate_background": 2,
                "generate_contexts": 0,
                "chat_turn": 0,
            },
            "total_calls": 22,
        },
        "results": [
            {
                "id": case_id,
                "passed": True,
                "issues": [],
                "contract": {},
                "latency_ms": 1.0,
                "call_evidence": {
                    "tool_names": [],
                    "tool_attempts": 0,
                    "provider_calls": {
                        "plan": 0,
                        "embed": 0,
                        "rerank": 0,
                        "generate": 0,
                        "generate_grounded": 0,
                        "generate_background": 0,
                        "generate_contexts": 0,
                        "chat_turn": 0,
                    },
                },
                "scope_evidence": {
                    "observed_location_labels": [],
                    "selected_result_id": None,
                },
                "trace": {
                    "trace_id": f"trace-{case_id}",
                    "tool_names": [],
                    "response_sha256": "e" * 64,
                },
                "cost_usd": 0.0,
            }
            for case_id in PRODUCTBENCH_IDS
        ],
        "offline_execution": {
            "live_fixture": "productbench_official_record_double.v1",
            "fake_provider_calls": {"plan": 0, "embed": 0, "rerank": 0, "generate": 0},
        },
    }


def _fixture_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    for relative in MATERIAL_PATHS:
        _write(root / relative, f"fixture:{relative}\n")
    _write(root / "data/evaluation/hard_probe.v1.yaml", BASE_DATASET_BYTES)
    _json(
        root / "data/evaluation/hard_probe.v1.manifest.json",
        {"dataset_sha256": BASE_DATASET_SHA256, "case_count": 105},
    )
    _write(root / "data/evaluation/productbench_journeys_50.json", PRODUCTBENCH_CATALOG_BYTES)
    _write(root / "data/evaluation/productbench_v2.manifest.json", PRODUCTBENCH_MANIFEST_BYTES)
    _write(
        root / "data/evaluation/hard_probe_rc2_expectations.v1.yaml",
        RC2_PROFILE_BYTES,
    )
    _json(
        root / "data/evaluation/hard_probe_rc2_expectations.v1.manifest.json",
        {
            "schema_version": "firelens.hard_probe_expectations_manifest.v1",
            "profile": "rc2",
            "expectations_sha256": RC2_PROFILE_SHA256,
            "base_dataset_sha256": BASE_DATASET_SHA256,
            "migration_count": 10,
            "migration_ids": sorted(RC2_MIGRATED_IDS),
            "minimum_passed": 86,
        },
    )
    _write(
        root / "data/evaluation/hard_probe_rc2_1_expectations.v1.yaml",
        RC2_1_PROFILE_BYTES,
    )
    _json(
        root / "data/evaluation/hard_probe_rc2_1_expectations.v1.manifest.json",
        {
            "schema_version": "firelens.hard_probe_expectations_manifest.v1",
            "profile": "rc2.1",
            "expectations_sha256": RC2_1_PROFILE_SHA256,
            "base_dataset_sha256": BASE_DATASET_SHA256,
            "migration_count": 11,
            "migration_ids": sorted(MIGRATED_IDS),
            "minimum_passed": 86,
        },
    )
    _write(root / "data/evaluation/hard_probe_rc2_2_expectations.v1.yaml", PROFILE_BYTES)
    _json(
        root / "data/evaluation/hard_probe_rc2_2_expectations.v1.manifest.json",
        {
            "schema_version": "firelens.hard_probe_expectations_manifest.v1",
            "profile": "rc2.2",
            "expectations_sha256": PROFILE_SHA256,
            "base_dataset_sha256": BASE_DATASET_SHA256,
            "migration_count": 11,
            "migration_ids": sorted(MIGRATED_IDS),
            "minimum_passed": 86,
        },
    )
    _write(root / "pyproject.toml", '[project]\nname = "fixture"\nversion = "1.6.0rc1"\n')
    _write(root / "requirements.lock", "fastapi==1.2.3\nPyYAML==6.0.3\n")
    _json(root / "apps/web/package.json", {"name": "ui", "version": "1.6.0-rc.1"})
    _json(
        root / "apps/web/package-lock.json",
        {
            "name": "ui",
            "version": "1.6.0-rc.1",
            "lockfileVersion": 3,
            "packages": {
                "": {"name": "ui", "version": "1.0.0"},
                "node_modules/react": {"version": "19.2.0", "license": "MIT"},
                "node_modules/vitest": {
                    "version": "4.1.10",
                    "license": "MIT",
                    "dev": True,
                },
            },
        },
    )
    _json(
        root / "docs/reports/V1_6_STRUCTURED_PUBLICATION_HARD_PROBE.json",
        _baseline_hard_probe(),
    )
    _json(
        root / SUBJECT_FILE,
        {
            "schema_version": "firelens.runtime_candidate.v4",
            "release_version": "1.6.0-rc.1",
        },
    )
    _write(root / SUBJECT_TREE / "index.html", "<!doctype html><div>FireLens</div>\n")
    _write(root / SUBJECT_TREE / "assets/app.js", "console.log('FireLens');\n")
    return root


def _evidence_inputs(
    tmp_path: Path,
    *,
    python_vulnerabilities: list[dict[str, object]] | None = None,
    npm_high: int = 0,
    npm_critical: int = 0,
    prohibited: list[str] | None = None,
    hard_probe: dict[str, object] | None = None,
    productbench_deterministic: dict[str, object] | None = None,
    clean: bool = True,
) -> dict[str, Path]:
    inputs = tmp_path / "inputs"
    values: dict[str, object] = {
        "python_audit": [
            {
                "name": "fastapi",
                "version": "1.2.3",
                "vulns": python_vulnerabilities or [],
            }
        ],
        "npm_audit": {
            "auditReportVersion": 2,
            "metadata": {
                "vulnerabilities": {
                    "info": 0,
                    "low": 0,
                    "moderate": 0,
                    "high": npm_high,
                    "critical": npm_critical,
                    "total": npm_high + npm_critical,
                }
            },
        },
        "licenses": {
            "python": [{"name": "fastapi", "version": "1.2.3", "license": "MIT"}],
            "node": [{"name": "react", "version": "19.2.0", "license": "MIT"}],
            "prohibited": prohibited or [],
        },
        "checkout_state": {
            "schema_version": "firelens.checkout_state.v1",
            "commit": COMMIT,
            "tree": TREE,
            "clean": clean,
            "status_porcelain": "" if clean else " M pyproject.toml",
        },
        "build_environment": {
            "schema_version": "firelens.build_environment.v1",
            "python": "3.12.11",
            "pip": "25.2",
            "node": "v22.18.0",
            "npm": "10.9.3",
            "runner_os": "Linux",
        },
        "command_outcomes": {
            "schema_version": "firelens.command_outcomes.v1",
            "commands": [
                {
                    "id": command_id,
                    "command": f"fixture command: {command_id}",
                    "exit_code": (
                        1
                        if command_id in {"hard_probe_offline", "python_audit", "npm_audit"}
                        else 0
                    ),
                }
                for command_id in REQUIRED_COMMAND_POLICIES
            ],
        },
        "credential_absence": {
            "schema_version": "firelens.credential_absence.v1",
            "checked_names": [
                "OPENROUTER_API_KEY",
                "OPENAI_API_KEY",
                "COHERE_API_KEY",
                "FIRELENS_RUN_OPENROUTER_SMOKE",
            ],
            "present_names": [],
            "provider_calls": 0,
            "paid_cost_usd": 0.0,
            "sealed_labels_accessed": False,
        },
        "workflow_identity": {
            "schema_version": "firelens.workflow_identity.v1",
            "repository": "owner/firelens-bc",
            "workflow": ".github/workflows/candidate.yml",
            "event": "pull_request",
            "ref": "refs/pull/7/head",
            "commit": COMMIT,
            "tree": TREE,
            "run_id": "123",
            "run_attempt": "1",
        },
        "structured_eval": {
            "evidence_class": "EXECUTED",
            "structural_pass": True,
            "structural_gates": {"leaks": 0, "mismatches": 0},
            "architecture": {
                "compiler_exclusivity_offenders": [],
                "serving_broad_exception": [],
            },
            "hashes": {
                "hard_probe": BASE_DATASET_SHA256,
                "typed_inventory": _fixture_material_sha("data/typed_claims/high_risk_v1.yaml"),
            },
        },
        "hard_probe": hard_probe or _hard_probe(),
        "productbench_deterministic": productbench_deterministic
        or _productbench_deterministic(),
    }
    paths: dict[str, Path] = {}
    for name, value in values.items():
        path = inputs / f"{name.replace('_', '-')}.json"
        _json(path, value)
        paths[name] = path
    return paths


def _build(
    root: Path,
    bundle: Path,
    inputs: dict[str, Path],
    *,
    release_version: str = "1.6.0-rc.1",
) -> bool:
    return build_candidate_evidence(
        root,
        bundle,
        commit=COMMIT,
        tree=TREE,
        release_version=release_version,
        generated_at=GENERATED_AT,
        builder_id="https://github.com/owner/firelens-bc/actions/workflows/candidate.yml",
        invocation_id="123:1",
        python_audit_path=inputs["python_audit"],
        npm_audit_path=inputs["npm_audit"],
        licenses_path=inputs["licenses"],
        checkout_state_path=inputs["checkout_state"],
        build_environment_path=inputs["build_environment"],
        command_outcomes_path=inputs["command_outcomes"],
        credential_absence_path=inputs["credential_absence"],
        workflow_identity_path=inputs["workflow_identity"],
        structured_eval_path=inputs["structured_eval"],
        hard_probe_path=inputs["hard_probe"],
        productbench_deterministic_path=inputs["productbench_deterministic"],
        limitations=LIMITATIONS,
    )


def _verify(root: Path, bundle: Path) -> None:
    verify_candidate_evidence(
        root,
        bundle,
        expected_commit=COMMIT,
        expected_tree=TREE,
    )


def test_v2_bundle_binds_complete_candidate_and_recomputes(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    bundle = tmp_path / "candidate"

    assert _build(root, bundle, _evidence_inputs(tmp_path)) is True
    _verify(root, bundle)

    manifest = json.loads((bundle / "candidate-evidence-manifest.json").read_text())
    assert manifest["schema_version"] == SCHEMA_VERSION == "firelens.candidate_evidence.v2"
    assert manifest["candidate_identity"] == {"commit": COMMIT, "tree": TREE}
    assert manifest["clean_starting_state"] is True
    material_names = {item["name"] for item in manifest["materials"]}
    assert {
        "data/processed/firelens_static_corpus.chunks.jsonl",
        "data/index/firelens_vectors.npy",
        "data/typed_claims/high_risk_v1.yaml",
        "docs/openapi.v1.json",
        "data/evaluation/hard_probe.v1.yaml",
        "data/evaluation/hard_probe_rc2_expectations.v1.yaml",
        "data/evaluation/hard_probe_rc2_expectations.v1.manifest.json",
        "data/evaluation/hard_probe_rc2_1_expectations.v1.yaml",
        "data/evaluation/hard_probe_rc2_1_expectations.v1.manifest.json",
        "data/evaluation/hard_probe_rc2_2_expectations.v1.yaml",
        "data/evaluation/hard_probe_rc2_2_expectations.v1.manifest.json",
        "data/evaluation/v1_6_user_end_questions_50.json",
        ".github/workflows/candidate.yml",
    }.issubset(material_names)
    assert MANIFEST_RELATIVE not in material_names
    assert not any("v1_5" in name.casefold() for name in material_names)
    assert {item["name"] for item in manifest["subjects"]} == {SUBJECT_FILE, SUBJECT_TREE}
    qualification = json.loads((bundle / "candidate-qualification-summary.json").read_text())
    assert qualification["hard_probe"]["passed"] == 86
    assert qualification["hard_probe"]["paired_regressions"] == []
    assert qualification["hard_probe"]["expectation_profile"] == "rc2.2"
    assert qualification["hard_probe"]["migrated_case_ids"] == sorted(MIGRATED_IDS)
    assert qualification["productbench_deterministic"] == {
        "tier": "offline_fake",
        "case_count": len(PRODUCTBENCH_IDS),
        "passed": len(PRODUCTBENCH_IDS),
        "catalog_sha256": PRODUCTBENCH_CATALOG_SHA256,
        "manifest_sha256": PRODUCTBENCH_MANIFEST_SHA256,
    }
    assert qualification["credentials"]["provider_calls"] == 0
    assert not (bundle / "CURRENT_EVIDENCE.json").exists()


@pytest.mark.parametrize(
    ("input_kwargs", "blocker"),
    [
        ({"python_vulnerabilities": [{"id": "PYSEC-1"}]}, "python_vulnerabilities"),
        ({"npm_high": 1}, "npm_high_vulnerabilities"),
        ({"npm_critical": 1}, "npm_critical_vulnerabilities"),
        ({"prohibited": ["python:bad:AGPL-3.0"]}, "prohibited_licenses"),
    ],
)
def test_security_findings_emit_evidence_but_fail_gate(
    tmp_path: Path,
    input_kwargs: dict[str, object],
    blocker: str,
) -> None:
    root = _fixture_root(tmp_path)
    bundle = tmp_path / "candidate"

    assert _build(root, bundle, _evidence_inputs(tmp_path, **input_kwargs)) is False
    security = json.loads((bundle / "candidate-security-summary.json").read_text())
    assert blocker in security["blockers"]
    with pytest.raises(ValueError, match="security gate did not pass"):
        _verify(root, bundle)


def test_tampering_changed_material_and_changed_subject_are_rejected(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    bundle = tmp_path / "candidate"
    assert _build(root, bundle, _evidence_inputs(tmp_path)) is True

    (bundle / "candidate-sbom.cdx.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="artifact identity"):
        _verify(root, bundle)

    bundle = tmp_path / "candidate-material"
    assert _build(root, bundle, _evidence_inputs(tmp_path / "material")) is True
    _write(root / "data/index/firelens_vectors.npy", b"changed")
    with pytest.raises(ValueError, match="material identity"):
        _verify(root, bundle)

    root = _fixture_root(tmp_path / "subject")
    bundle = tmp_path / "candidate-subject"
    assert _build(root, bundle, _evidence_inputs(tmp_path / "subject-input")) is True
    _write(root / SUBJECT_TREE / "assets/app.js", "changed\n")
    with pytest.raises(ValueError, match="subject identity"):
        _verify(root, bundle)


def test_identity_extra_missing_and_stale_report_paths_are_rejected(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    bundle = tmp_path / "candidate"
    assert _build(root, bundle, _evidence_inputs(tmp_path)) is True

    with pytest.raises(ValueError, match="expected identity"):
        verify_candidate_evidence(
            root,
            bundle,
            expected_commit="c" * 40,
            expected_tree=TREE,
        )
    with pytest.raises(ValueError, match="expected identity"):
        verify_candidate_evidence(
            root,
            bundle,
            expected_commit=COMMIT,
            expected_tree="d" * 40,
        )

    _write(bundle / "unexpected.txt", "not allowed\n")
    with pytest.raises(ValueError, match="missing or unexpected"):
        _verify(root, bundle)
    (bundle / "unexpected.txt").unlink()

    captured_input = bundle / "inputs/build-environment.json"
    captured_bytes = captured_input.read_bytes()
    captured_input.unlink()
    with pytest.raises(ValueError, match="missing or unexpected"):
        _verify(root, bundle)
    _write(captured_input, captured_bytes)

    manifest_path = bundle / "candidate-evidence-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["materials"][0]["name"] = "docs/reports/V1_5_2_BENCHMARK.md"
    _json(manifest_path, manifest)
    with pytest.raises(ValueError, match="stale V1.5 report path"):
        _verify(root, bundle)


def test_unclean_start_and_hard_probe_regression_are_rejected(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    with pytest.raises(ValueError, match="captured clean starting state"):
        _build(
            root,
            tmp_path / "unclean-bundle",
            _evidence_inputs(tmp_path / "unclean-inputs", clean=False),
        )

    baseline_ids = set(CASE_IDS[:86])
    regressed_ids = (baseline_ids - {"HP-000"}) | {"HP-093"}
    with pytest.raises(ValueError, match="regressed previously passing cases: HP-000"):
        _build(
            root,
            tmp_path / "regressed-bundle",
            _evidence_inputs(
                tmp_path / "regressed-inputs",
                hard_probe=_hard_probe(passed_ids=regressed_ids),
            ),
        )


def test_productbench_evidence_must_be_present_current_and_complete(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    missing = _evidence_inputs(tmp_path / "missing")
    missing["productbench_deterministic"].unlink()
    with pytest.raises(ValueError, match="regular JSON file"):
        _build(root, tmp_path / "missing-candidate", missing)

    stale = _productbench_deterministic(tree="c" * 40)
    with pytest.raises(ValueError, match="stale or mismatched"):
        _build(
            root,
            tmp_path / "stale-candidate",
            _evidence_inputs(tmp_path / "stale", productbench_deterministic=stale),
        )

    dirty = _productbench_deterministic()
    dirty["identity"]["git_clean"] = False  # type: ignore[index]
    with pytest.raises(ValueError, match="stale or mismatched"):
        _build(
            root,
            tmp_path / "dirty-candidate",
            _evidence_inputs(tmp_path / "dirty", productbench_deterministic=dirty),
        )

    failed = _productbench_deterministic()
    failed["results"][0]["passed"] = False  # type: ignore[index]
    failed["results"][0]["issues"] = ["predicate_failed"]  # type: ignore[index]
    failed["passed"] = len(PRODUCTBENCH_IDS) - 1
    failed["failed"] = 1
    with pytest.raises(ValueError, match="execution did not pass"):
        _build(
            root,
            tmp_path / "failed-candidate",
            _evidence_inputs(tmp_path / "failed", productbench_deterministic=failed),
        )


def test_productbench_report_emitter_shape_is_candidate_evidence_compatible(
    tmp_path: Path,
) -> None:
    """A complete runner report must not be rejected for its own v2 provenance."""

    root = _fixture_root(tmp_path)
    template = _productbench_deterministic()
    manifest = json.loads(
        (root / "data/evaluation/productbench_v2.manifest.json").read_text(encoding="utf-8")
    )
    report = productbench_v2_report.build(
        manifest,
        "offline_fake",
        template["results"],
        max_cost_usd=0.0,
        provider_boundary="offline_fake",
        identity=lambda _: template["identity"],
        offline_execution=template["offline_execution"],
        provider_call_counts=template["provider_activity"]["call_counts"],
    )

    _build(
        root,
        tmp_path / "emitted-candidate",
        _evidence_inputs(tmp_path / "emitted-inputs", productbench_deterministic=report),
    )

    mismatched_activity = _productbench_deterministic()
    mismatched_activity["provider_activity"]["total_calls"] = 0  # type: ignore[index]
    with pytest.raises(ValueError, match="provider activity is invalid"):
        _build(
            root,
            tmp_path / "mismatched-activity-candidate",
            _evidence_inputs(
                tmp_path / "mismatched-activity-inputs",
                productbench_deterministic=mismatched_activity,
            ),
        )

    unverified_cost = _productbench_deterministic()
    unverified_cost["cost"]["cost_unverified"] = False  # type: ignore[index]
    with pytest.raises(ValueError, match="cost evidence fields are invalid"):
        _build(
            root,
            tmp_path / "unverified-cost-candidate",
            _evidence_inputs(
                tmp_path / "unverified-cost-inputs",
                productbench_deterministic=unverified_cost,
            ),
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("stale_schema", "schema is invalid"),
        ("wrong_tree", "identity or offline boundary"),
        ("wrong_profile", "identity or offline boundary"),
        ("wrong_effective_hash", "identity or offline boundary"),
        ("wrong_reported_floor", "frozen 86/105"),
        ("below_floor", "frozen 86/105"),
    ],
)
def test_current_report_requires_v2_rc2_2_tree_hashes_and_floor(
    tmp_path: Path, mutation: str, message: str
) -> None:
    root = _fixture_root(tmp_path)
    report = _hard_probe()
    if mutation == "stale_schema":
        report["schema_version"] = "firelens_hard_probe_report.v1"
    elif mutation == "wrong_tree":
        report["manifest"]["tree"] = "c" * 40  # type: ignore[index]
    elif mutation == "wrong_profile":
        report["manifest"]["expectation_profile"] = "arbitrary"  # type: ignore[index]
    elif mutation == "wrong_effective_hash":
        report["manifest"]["effective_expectations_sha256"] = "0" * 64  # type: ignore[index]
    elif mutation == "wrong_reported_floor":
        report["summary"]["minimum_passed"] = 85  # type: ignore[index]
    else:
        report = _hard_probe(passed_ids=set(CASE_IDS[:85]))
    with pytest.raises(ValueError, match=message):
        _build(
            root,
            tmp_path / "candidate",
            _evidence_inputs(tmp_path / "inputs", hard_probe=report),
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("missing", "regular file"),
        ("overlay_hash", "does not match its manifest"),
        ("wrong_floor", "identity or floor"),
        ("wrong_base", "identity or floor"),
        ("wrong_migrated_ids", "undeclared migration"),
    ],
)
def test_profile_missing_mutated_floor_base_and_roster_are_rejected(
    tmp_path: Path, mutation: str, message: str
) -> None:
    root = _fixture_root(tmp_path)
    profile_path = root / "data/evaluation/hard_probe_rc2_2_expectations.v1.yaml"
    if mutation == "missing":
        profile_path.unlink()
    elif mutation == "overlay_hash":
        _write(profile_path, profile_path.read_bytes() + b"\n")
    else:
        profile = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
        if mutation == "wrong_floor":
            profile["minimum_passed"] = 85
        elif mutation == "wrong_base":
            profile["base_dataset_sha256"] = "0" * 64
        else:
            profile["migrations"][-1]["id"] = "Z99"
        _write(profile_path, yaml.safe_dump(profile, sort_keys=False))
    with pytest.raises(ValueError, match=message):
        _build(root, tmp_path / "candidate", _evidence_inputs(tmp_path / "inputs"))


def test_frozen_rc2_profile_pair_remains_required_and_validated(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    frozen_rc2 = root / "data/evaluation/hard_probe_rc2_expectations.v1.yaml"
    _write(frozen_rc2, frozen_rc2.read_bytes() + b"\n")

    with pytest.raises(ValueError, match="does not match its manifest"):
        _build(root, tmp_path / "candidate", _evidence_inputs(tmp_path / "inputs"))


def test_frozen_rc2_1_profile_pair_remains_required_and_validated(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    frozen_rc2_1 = root / "data/evaluation/hard_probe_rc2_1_expectations.v1.yaml"
    _write(frozen_rc2_1, frozen_rc2_1.read_bytes() + b"\n")

    with pytest.raises(ValueError, match="does not match its manifest"):
        _build(root, tmp_path / "candidate", _evidence_inputs(tmp_path / "inputs"))


def test_unlisted_expectation_change_and_migrated_semantic_drift_are_rejected(
    tmp_path: Path,
) -> None:
    root = _fixture_root(tmp_path)
    report = _hard_probe()
    unlisted = next(row for row in report["results"] if row["id"] == "HP-000")  # type: ignore[index]
    unlisted["applied_migration"] = MIGRATION_BY_ID["A04"]
    with pytest.raises(ValueError, match="unbound expectation change: HP-000"):
        _build(
            root,
            tmp_path / "unlisted",
            _evidence_inputs(tmp_path / "unlisted-inputs", hard_probe=report),
        )

    report = _hard_probe()
    quote_row = next(row for row in report["results"] if row["id"] == "A04")  # type: ignore[index]
    quote_row["response_mode"] = "grounded"
    with pytest.raises(ValueError, match="quote-only case A04"):
        _build(
            root,
            tmp_path / "quote-drift",
            _evidence_inputs(tmp_path / "quote-inputs", hard_probe=report),
        )

    report = _hard_probe()
    quote_row = next(  # type: ignore[index]
        row for row in report["results"] if row["id"] == "A04"
    )
    quote_row["provider_stages"] = [
        {"stage": "grounded_generation", "attempts": 1, "cost_usd": 0.0}
    ]
    with pytest.raises(ValueError, match="migrated case A04 used generation"):
        _build(
            root,
            tmp_path / "generation-drift",
            _evidence_inputs(tmp_path / "generation-inputs", hard_probe=report),
        )

    report = _hard_probe()
    handoff = next(row for row in report["results"] if row["id"] == "J01")  # type: ignore[index]
    handoff["response"]["claims"] = [{"claim_id": "unexpected"}]  # type: ignore[index]
    with pytest.raises(ValueError, match="handoff case J01 is not deterministic"):
        _build(
            root,
            tmp_path / "handoff-drift",
            _evidence_inputs(tmp_path / "handoff-inputs", hard_probe=report),
        )

    report = _hard_probe()
    mixed = next(row for row in report["results"] if row["id"] == "A01")  # type: ignore[index]
    mixed["response"]["claims"] = [mixed["response"]["claims"][0]]  # type: ignore[index]
    with pytest.raises(ValueError, match="exact publication kinds"):
        _build(
            root,
            tmp_path / "mixed-kind-drift",
            _evidence_inputs(tmp_path / "mixed-kind-inputs", hard_probe=report),
        )

    report = _hard_probe()
    mixed = next(row for row in report["results"] if row["id"] == "A01")  # type: ignore[index]
    mixed["response"]["reason_code"] = None  # type: ignore[index]
    with pytest.raises(ValueError, match="safe response contract"):
        _build(
            root,
            tmp_path / "mixed-reason-drift",
            _evidence_inputs(tmp_path / "mixed-reason-inputs", hard_probe=report),
        )

    report = _hard_probe()
    two_sided = next(row for row in report["results"] if row["id"] == "A09")  # type: ignore[index]
    two_sided["response"]["claims"] = [two_sided["response"]["claims"][0]]  # type: ignore[index]
    with pytest.raises(ValueError, match="lacks alert and order claims"):
        _build(
            root,
            tmp_path / "two-sided-drift",
            _evidence_inputs(tmp_path / "two-sided-inputs", hard_probe=report),
        )


def test_release_version_must_match_python_web_and_runtime_subject(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    _json(root / "apps/web/package.json", {"name": "ui", "version": "1.6.0-rc.2"})
    with pytest.raises(ValueError, match="release version identities do not match"):
        _build(root, tmp_path / "candidate", _evidence_inputs(tmp_path / "inputs"))


def test_promoted_release_version_requires_the_internal_manifest(tmp_path: Path) -> None:
    root = _fixture_root(tmp_path)
    _write(root / "pyproject.toml", '[project]\nname = "fixture"\nversion = "1.6.0"\n')
    _json(root / "apps/web/package.json", {"name": "ui", "version": "1.6.0"})
    _json(
        root / SUBJECT_FILE,
        {
            "schema_version": "firelens.runtime_candidate.v4",
            "release_version": "1.6.0",
        },
    )
    with pytest.raises(ValueError, match="release-promotion manifest"):
        _build(
            root,
            tmp_path / "candidate",
            _evidence_inputs(tmp_path / "inputs"),
            release_version="1.6.0",
        )


def _promoted_fixture_root(tmp_path: Path) -> Path:
    root = _fixture_root(tmp_path)
    _write(root / "pyproject.toml", '[project]\nname = "fixture"\nversion = "1.6.0"\n')
    _json(root / "apps/web/package.json", {"name": "ui", "version": "1.6.0"})
    lock = json.loads((root / "apps/web/package-lock.json").read_text(encoding="utf-8"))
    lock["version"] = "1.6.0"
    lock["packages"][""]["version"] = "1.6.0"
    _json(root / "apps/web/package-lock.json", lock)
    _write(root / "src/firelens/config.py", 'DEFAULT_RELEASE_VERSION = "1.6.0"\n')
    _write(root / "Dockerfile", "ARG FIRELENS_RELEASE_VERSION=1.6.0\n")
    _write(
        root / "render.yaml",
        'services:\n  - envVars:\n      - key: FIRELENS_RELEASE_VERSION\n        value: "1.6.0"\n',
    )
    _json(root / "docs/openapi.v1.json", {"info": {"title": "FireLens BC", "version": "1.6.0"}})
    _write(
        root / ".github/workflows/candidate.yml",
        "run: python scripts/candidate_evidence.py --release-version 1.6.0\n",
    )
    _json(
        root / SUBJECT_FILE,
        {
            "schema_version": "firelens.runtime_candidate.v4",
            "release_version": "1.6.0",
        },
    )
    repo = Path(__file__).resolve().parents[1]
    _write(root / STANDARD_RELATIVE, (repo / STANDARD_RELATIVE).read_text(encoding="utf-8"))
    _json(
        root / MANIFEST_RELATIVE,
        promotion_manifest_document(
            frozen_standard_sha256=file_sha256(root / STANDARD_RELATIVE),
            functional_parent_commit="c" * 40,
            functional_parent_tree="d" * 40,
        ),
    )
    return root


def test_promoted_evidence_binds_and_rehashes_the_promotion_manifest(tmp_path: Path) -> None:
    root = _promoted_fixture_root(tmp_path)
    bundle = tmp_path / "promoted-candidate"
    assert (
        _build(
            root,
            bundle,
            _evidence_inputs(tmp_path / "promoted-inputs"),
            release_version="1.6.0",
        )
        is True
    )
    _verify(root, bundle)
    record = promotion_material_record(root)
    manifest = json.loads((bundle / "candidate-evidence-manifest.json").read_text())
    assert record in manifest["materials"]
    provenance = json.loads((bundle / "candidate-provenance.intoto.json").read_text())
    assert {
        "uri": f"file:{record['name']}",
        "digest": {"sha256": record["sha256"]},
    } in provenance["predicate"]["buildDefinition"]["resolvedDependencies"]
    (root / MANIFEST_RELATIVE).write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="release-promotion|material identity"):
        _verify(root, bundle)


def test_v1_6_2_evidence_selects_patch_validator_and_material(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _fixture_root(tmp_path)
    _write(root / "pyproject.toml", '[project]\nname = "fixture"\nversion = "1.6.2"\n')
    _json(root / "apps/web/package.json", {"name": "ui", "version": "1.6.2"})
    _json(root / PATCH_MANIFEST_RELATIVE, {"fixture": "patch material"})
    _json(
        root / SUBJECT_FILE,
        {
            "schema_version": "firelens.runtime_candidate.v4",
            "release_version": "1.6.2",
        },
    )
    calls: list[dict[str, object]] = []

    def record_patch_validation(*args: object, **kwargs: object) -> dict[str, object]:
        calls.append({"args": args, **kwargs})
        return {"qualification": {"status": "EXECUTED"}}

    monkeypatch.setattr(
        candidate_evidence_documents,
        "validate_patch_promotion",
        record_patch_validation,
    )
    monkeypatch.setattr(
        candidate_evidence_documents,
        "validate_release_promotion",
        lambda *args, **kwargs: pytest.fail("historical validator selected for V1.6.2"),
    )
    bundle = tmp_path / "patch-candidate"

    assert (
        _build(
            root,
            bundle,
            _evidence_inputs(tmp_path / "patch-inputs"),
            release_version="1.6.2",
        )
        is True
    )
    assert calls and calls[0]["release_version"] == "1.6.2"
    assert calls[0]["clean_starting_state_bound"] is True
    manifest = json.loads((bundle / "candidate-evidence-manifest.json").read_text())
    material_names = {item["name"] for item in manifest["materials"]}
    assert PATCH_MANIFEST_RELATIVE in material_names
    assert MANIFEST_RELATIVE not in material_names


def test_main_push_workflow_identity_is_accepted() -> None:
    validate_workflow_identity(
        {
            "schema_version": "firelens.workflow_identity.v1",
            "repository": "owner/firelens-bc",
            "workflow": ".github/workflows/candidate.yml",
            "event": "push",
            "ref": "refs/heads/main",
            "commit": COMMIT,
            "tree": TREE,
            "run_id": "123",
            "run_attempt": "1",
        },
        commit=COMMIT,
        tree=TREE,
    )


def test_non_main_push_workflow_identity_is_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported workflow or event"):
        validate_workflow_identity(
            {
                "schema_version": "firelens.workflow_identity.v1",
                "repository": "owner/firelens-bc",
                "workflow": ".github/workflows/candidate.yml",
                "event": "push",
                "ref": "refs/heads/fix/v1-6-paid-floor",
                "commit": COMMIT,
                "tree": TREE,
                "run_id": "123",
                "run_attempt": "1",
            },
            commit=COMMIT,
            tree=TREE,
        )


def test_candidate_workflow_is_exact_head_zero_cost_v2_artifact() -> None:
    workflow_path = Path(__file__).resolve().parents[1] / ".github/workflows/candidate.yml"
    workflow_text = workflow_path.read_text(encoding="utf-8")
    loaded = yaml.safe_load(workflow_text)
    assert isinstance(loaded, dict)
    triggers = loaded.get("on", loaded.get(True))
    assert triggers["push"]["branches"] == ["main"]
    assert "github.event.pull_request.head.sha || github.sha" in workflow_text
    assert "scripts/run_hard_probe.py --mode offline" in workflow_text
    assert "make productbench-deterministic" in workflow_text
    assert (
        "--productbench-deterministic candidate-inputs/productbench-deterministic.json"
        in workflow_text
    )
    assert workflow_text.index("Execute deterministic ProductBench") < workflow_text.index(
        "mkdir -p candidate-inputs"
    )
    assert (
        'productbench_deterministic="${{ steps.productbench.outputs.exit_code }}"'
        in workflow_text
    )
    assert "--expectation-profile rc2.2" in workflow_text
    assert "--release-version 1.6.4" in workflow_text
    assert "--release-version 1.6.0-rc.1" not in workflow_text
    assert "--release-version 1.6.0-rc.2" not in workflow_text
    assert "config/firelens.v1_6_3_patch_promotion.v1.json" in workflow_text
    assert "firelens.candidate_evidence.v2" in workflow_text
    assert "--expected-tree" in workflow_text
    assert "CURRENT_EVIDENCE" not in workflow_text
    assert "actions/upload-artifact@" in workflow_text
