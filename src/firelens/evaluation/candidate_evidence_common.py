"""Shared constants, filesystem primitives, and RC2.1 case checks."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "firelens.candidate_evidence.v2"
SECURITY_SCHEMA_VERSION = "firelens.candidate_security.v1"
QUALIFICATION_SCHEMA_VERSION = "firelens.candidate_qualification.v2"
BUILD_TYPE = "https://firelens-bc.local/build-types/candidate-evidence/v2"
COMMIT = re.compile(r"^[0-9a-f]{40}$")
EXACT_REQUIREMENT = re.compile(r"^([A-Za-z0-9_.-]+)==([^\s;]+)$")
STALE_REPORT_PATH = re.compile(r"(^|/)v1_5[^/]*(/|$)", re.IGNORECASE)
HARD_PROBE_PROFILE = "rc2.2"
HARD_PROBE_FROZEN_RC2_PROFILE_PATH = "data/evaluation/hard_probe_rc2_expectations.v1.yaml"
HARD_PROBE_FROZEN_RC2_PROFILE_MANIFEST_PATH = (
    "data/evaluation/hard_probe_rc2_expectations.v1.manifest.json"
)
HARD_PROBE_FROZEN_RC2_1_PROFILE_PATH = "data/evaluation/hard_probe_rc2_1_expectations.v1.yaml"
HARD_PROBE_FROZEN_RC2_1_PROFILE_MANIFEST_PATH = (
    "data/evaluation/hard_probe_rc2_1_expectations.v1.manifest.json"
)
HARD_PROBE_PROFILE_PATH = "data/evaluation/hard_probe_rc2_2_expectations.v1.yaml"
HARD_PROBE_PROFILE_MANIFEST_PATH = (
    "data/evaluation/hard_probe_rc2_2_expectations.v1.manifest.json"
)
HARD_PROBE_RC2_MIGRATED_IDS = (
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
HARD_PROBE_MIGRATED_IDS = (*HARD_PROBE_RC2_MIGRATED_IDS, "A01")
HARD_PROBE_QUOTE_ONLY_MIGRATED_IDS = frozenset(HARD_PROBE_RC2_MIGRATED_IDS) - {"J01"}
HARD_PROBE_STRUCTURED_TWO_SIDED_IDS = frozenset({"A09", "A10"})
HARD_PROBE_ACTIVE_QUOTE_ONLY_IDS = (
    HARD_PROBE_QUOTE_ONLY_MIGRATED_IDS - HARD_PROBE_STRUCTURED_TWO_SIDED_IDS
)
HARD_PROBE_MIXED_MIGRATED_IDS = frozenset({"A01"})
OFFICIAL_HANDOFF_ANSWER = (
    "FireLens does not have a reviewed structured claim for this high-risk question. "
    "Use the issuing authority for official wording."
)

MATERIAL_PATHS = (
    "requirements.lock",
    "pyproject.toml",
    "apps/web/package.json",
    "apps/web/package-lock.json",
    "Dockerfile",
    "vercel.json",
    "render.yaml",
    "config/runtime_artifact_allowlist.v1.json",
    "data/processed/firelens_static_corpus.manifest.json",
    "data/processed/firelens_static_corpus.chunks.jsonl",
    "data/index/firelens_vectors.manifest.json",
    "data/index/firelens_vectors.npy",
    "data/typed_claims/high_risk_v1.yaml",
    "docs/openapi.v1.json",
    "data/evaluation/hard_probe.v1.yaml",
    "data/evaluation/hard_probe.v1.manifest.json",
    HARD_PROBE_FROZEN_RC2_PROFILE_PATH,
    HARD_PROBE_FROZEN_RC2_PROFILE_MANIFEST_PATH,
    HARD_PROBE_FROZEN_RC2_1_PROFILE_PATH,
    HARD_PROBE_FROZEN_RC2_1_PROFILE_MANIFEST_PATH,
    HARD_PROBE_PROFILE_PATH,
    HARD_PROBE_PROFILE_MANIFEST_PATH,
    "data/evaluation/v1_6_user_end_questions_50.json",
    "data/evaluation/v1_6_user_end_questions_50.manifest.json",
    "data/evaluation/productbench_journeys_50.json",
    "data/evaluation/productbench_v2.manifest.json",
    "docs/reports/V1_6_STRUCTURED_PUBLICATION_HARD_PROBE.json",
    "docs/reports/V1_6_TYPED_CLAIM_REVIEW_BATCH_1_DECISIONS.yaml",
    "docs/reports/V1_6_TYPED_CLAIM_REVIEW_BATCH_2_DECISIONS.yaml",
    "docs/reports/V1_6_TYPED_CLAIM_REVIEW_BATCH_3_DECISIONS.yaml",
    "docs/reports/V1_6_SOURCE_REPAIR_SCOPE_DECISIONS.yaml",
    ".github/workflows/candidate.yml",
)
SUBJECT_FILE = "config/runtime_candidate.v1.json"
SUBJECT_TREE = "apps/web/dist"
RAW_EVIDENCE_NAMES = (
    "inputs/python-audit.json",
    "inputs/npm-audit.json",
    "inputs/dependency-licenses.json",
    "inputs/checkout-state.json",
    "inputs/build-environment.json",
    "inputs/command-outcomes.json",
    "inputs/credential-absence.json",
    "inputs/workflow-identity.json",
    "inputs/structured-publication-eval.json",
    "inputs/hard-probe.json",
    "inputs/hard-probe-baseline.json",
    "inputs/productbench-deterministic.json",
)
GENERATED_NAMES = (
    "candidate-sbom.cdx.json",
    "candidate-provenance.intoto.json",
    "candidate-security-summary.json",
    "candidate-qualification-summary.json",
)

REQUIRED_COMMAND_POLICIES: dict[str, frozenset[int]] = {
    "lockfiles": frozenset({0}),
    "action_pins": frozenset({0}),
    "make_verify": frozenset({0}),
    "runtime_candidate": frozenset({0}),
    "frontend_build": frozenset({0}),
    "structured_publication_eval": frozenset({0}),
    # The permanent runner returns one when any of 105 cases fail. The v2
    # qualification validator owns the frozen 86/no-regression gate.
    "hard_probe_offline": frozenset({0, 1}),
    "productbench_deterministic": frozenset({0}),
    "python_audit": frozenset({0, 1}),
    "npm_audit": frozenset({0, 1}),
    "dependency_licenses": frozenset({0}),
    "candidate_artifact_scope": frozenset({0}),
}


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def strict_file(root: Path, relative: str) -> Path:
    if Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError(f"unsafe evidence path: {relative}")
    path = root / relative
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"candidate evidence requires a regular file: {relative}")
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"candidate evidence path escapes its root: {relative}")
    return path


def file_record(root: Path, relative: str) -> dict[str, object]:
    data = strict_file(root, relative).read_bytes()
    return {"name": relative, "sha256": sha256_bytes(data), "size_bytes": len(data)}


def tree_record(root: Path, relative: str) -> dict[str, object]:
    tree = root / relative
    if tree.is_symlink() or not tree.is_dir():
        raise ValueError(f"candidate evidence requires a regular directory: {relative}")
    files: list[dict[str, object]] = []
    total_size = 0
    for path in sorted(tree.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"candidate subject tree contains a symlink: {path}")
        if not path.is_file():
            continue
        name = path.relative_to(root).as_posix()
        data = path.read_bytes()
        total_size += len(data)
        files.append({"name": name, "sha256": sha256_bytes(data), "size_bytes": len(data)})
    if not files:
        raise ValueError(f"candidate subject tree is empty: {relative}")
    digest = sha256_bytes(canonical_bytes(files))
    return {
        "name": relative,
        "sha256": digest,
        "size_bytes": total_size,
        "file_count": len(files),
        "files": files,
    }


def load_json(path: Path, label: str) -> Any:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} must be a regular JSON file")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} must be valid UTF-8 JSON") from exc


def _exact_fields(value: Any, fields: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError(f"{label} fields are invalid")
    return value


def validate_zero_generation(row: dict[str, Any], *, case_id: str) -> None:
    stages = row.get("provider_stages")
    if not isinstance(stages, list) or any(not isinstance(stage, dict) for stage in stages):
        raise ValueError(f"hard-probe migrated case {case_id} has invalid provider stages")
    generation_stages = [
        stage
        for stage in stages
        if stage.get("stage") == "generation"
        or str(stage.get("stage", "")).endswith(("_generation", "_repair"))
    ]
    attempts = [stage.get("attempts") for stage in generation_stages]
    costs = [stage.get("cost_usd") for stage in generation_stages]
    if any(
        not isinstance(value, int) or isinstance(value, bool) or value != 0
        for value in attempts
    ) or any(
        not isinstance(value, (int, float)) or isinstance(value, bool) or value != 0
        for value in costs
    ):
        raise ValueError(f"hard-probe migrated case {case_id} used generation")


def validate_quote_only_migration(row: dict[str, Any], *, case_id: str) -> None:
    if (
        row.get("passed") is not True
        or row.get("response_mode") != "partial"
        or row.get("validation_status") != "accepted"
    ):
        raise ValueError(f"hard-probe migrated quote-only case {case_id} did not pass safely")
    validate_zero_generation(row, case_id=case_id)
    response = row.get("response")
    if not isinstance(response, dict) or response.get("response_mode") != "partial":
        raise ValueError(f"hard-probe migrated quote-only case {case_id} lacks its response")
    claims = response.get("claims")
    evidence = response.get("evidence")
    if (
        not isinstance(claims, list)
        or not claims
        or not isinstance(evidence, list)
        or not evidence
    ):
        raise ValueError(
            f"hard-probe migrated quote-only case {case_id} lacks claims or evidence"
        )
    evidence_by_id = {
        item.get("evidence_id"): item
        for item in evidence
        if isinstance(item, dict) and isinstance(item.get("evidence_id"), str)
    }
    publication_kinds: set[str] = set()
    for claim in claims:
        if not isinstance(claim, dict):
            raise ValueError(
                f"hard-probe migrated quote-only case {case_id} has invalid claims"
            )
        publication = claim.get("publication")
        supports = claim.get("supports")
        if not isinstance(publication, dict) or not isinstance(supports, list) or not supports:
            raise ValueError(
                f"hard-probe migrated quote-only case {case_id} lacks publication support"
            )
        kind = publication.get("kind")
        if isinstance(kind, str):
            publication_kinds.add(kind)
        for support in supports:
            if not isinstance(support, dict):
                raise ValueError(
                    f"hard-probe migrated quote-only case {case_id} has invalid support"
                )
            evidence_item = evidence_by_id.get(support.get("evidence_id"))
            quote = support.get("quote")
            if (
                not isinstance(evidence_item, dict)
                or not isinstance(quote, str)
                or not quote
                or quote not in str(evidence_item.get("primary_text", ""))
            ):
                raise ValueError(
                    f"hard-probe migrated quote-only case {case_id} lacks exact quote support"
                )
    if publication_kinds != {"official_quote_only"}:
        raise ValueError(
            f"hard-probe migrated quote-only case {case_id} has an invalid publication kind"
        )


def validate_mixed_migration(row: dict[str, Any], *, case_id: str) -> None:
    """Recompute the A01 mixed-publication contract from response evidence."""

    validate_zero_generation(row, case_id=case_id)
    response = row.get("response")
    if (
        row.get("response_mode") != "partial"
        or row.get("validation_status") != "accepted"
        or not isinstance(response, dict)
        or response.get("status") != "answer"
        or response.get("response_mode") != "partial"
        or response.get("reason_code") != "high_risk_claim_not_structured"
    ):
        raise ValueError(f"hard-probe mixed case {case_id} lacks its safe response contract")
    validation = response.get("validation")
    claims = response.get("claims")
    evidence = response.get("evidence")
    if (
        not isinstance(validation, dict)
        or validation.get("accepted") is not True
        or not isinstance(claims, list)
        or not claims
        or not isinstance(evidence, list)
        or not evidence
    ):
        raise ValueError(f"hard-probe mixed case {case_id} lacks accepted claims or evidence")
    evidence_by_id = {
        item.get("evidence_id"): item
        for item in evidence
        if isinstance(item, dict) and isinstance(item.get("evidence_id"), str)
    }
    publication_kinds: set[str] = set()
    for claim in claims:
        if not isinstance(claim, dict):
            raise ValueError(f"hard-probe mixed case {case_id} has invalid claims")
        publication = claim.get("publication")
        supports = claim.get("supports")
        if not isinstance(publication, dict) or not isinstance(supports, list) or not supports:
            raise ValueError(f"hard-probe mixed case {case_id} lacks publication support")
        kind = publication.get("kind")
        if not isinstance(kind, str):
            raise ValueError(f"hard-probe mixed case {case_id} has an invalid publication kind")
        publication_kinds.add(kind)
        for support in supports:
            if not isinstance(support, dict):
                raise ValueError(f"hard-probe mixed case {case_id} has invalid support")
            evidence_item = evidence_by_id.get(support.get("evidence_id"))
            quote = support.get("quote")
            if (
                not isinstance(evidence_item, dict)
                or not isinstance(quote, str)
                or not quote
                or quote not in str(evidence_item.get("primary_text", ""))
            ):
                raise ValueError(f"hard-probe mixed case {case_id} lacks exact quote support")
    if publication_kinds != {"structured_reviewed", "official_quote_only"}:
        raise ValueError(
            f"hard-probe mixed case {case_id} does not contain the exact publication kinds"
        )


def validate_structured_two_sided_migration(row: dict[str, Any], *, case_id: str) -> None:
    """Recompute A09/A10 two-sided structured_reviewed coverage from response evidence."""

    validate_zero_generation(row, case_id=case_id)
    response = row.get("response")
    if (
        row.get("passed") is not True
        or row.get("response_mode") != "grounded"
        or row.get("validation_status") != "accepted"
        or not isinstance(response, dict)
        or response.get("status") != "answer"
        or response.get("response_mode") != "grounded"
    ):
        raise ValueError(f"hard-probe two-sided structured case {case_id} did not pass safely")
    validation = response.get("validation")
    claims = response.get("claims")
    evidence = response.get("evidence")
    if (
        not isinstance(validation, dict)
        or validation.get("accepted") is not True
        or not isinstance(claims, list)
        or not claims
        or not isinstance(evidence, list)
        or not evidence
    ):
        raise ValueError(
            f"hard-probe two-sided structured case {case_id} lacks accepted claims or evidence"
        )
    evidence_by_id = {
        item.get("evidence_id"): item
        for item in evidence
        if isinstance(item, dict) and isinstance(item.get("evidence_id"), str)
    }
    publication_kinds: set[str] = set()
    typed_ids: set[str] = set()
    for claim in claims:
        if not isinstance(claim, dict):
            raise ValueError(
                f"hard-probe two-sided structured case {case_id} has invalid claims"
            )
        publication = claim.get("publication")
        supports = claim.get("supports")
        if not isinstance(publication, dict) or not isinstance(supports, list) or not supports:
            raise ValueError(
                f"hard-probe two-sided structured case {case_id} lacks publication support"
            )
        kind = publication.get("kind")
        typed_id = publication.get("typed_claim_id")
        if not isinstance(kind, str):
            raise ValueError(
                f"hard-probe two-sided structured case {case_id} has an invalid publication kind"
            )
        publication_kinds.add(kind)
        if isinstance(typed_id, str):
            typed_ids.add(typed_id)
        for support in supports:
            if not isinstance(support, dict):
                raise ValueError(
                    f"hard-probe two-sided structured case {case_id} has invalid support"
                )
            evidence_item = evidence_by_id.get(support.get("evidence_id"))
            quote = support.get("quote")
            if (
                not isinstance(evidence_item, dict)
                or not isinstance(quote, str)
                or not quote
                or quote not in str(evidence_item.get("primary_text", ""))
            ):
                raise ValueError(
                    f"hard-probe two-sided structured case {case_id} lacks exact quote support"
                )
    if publication_kinds != {"structured_reviewed"}:
        raise ValueError(
            f"hard-probe two-sided structured case {case_id} has an invalid publication kind"
        )
    if typed_ids != {"TC-EVAC-ALERT-001", "TC-EVAC-ORDER-001"}:
        raise ValueError(
            f"hard-probe two-sided structured case {case_id} lacks alert and order claims"
        )


def validate_handoff_migration(row: dict[str, Any]) -> None:
    if row.get("passed") is not True or row.get("response_mode") != "scope_redirect":
        raise ValueError("hard-probe migrated handoff case J01 did not pass safely")
    validate_zero_generation(row, case_id="J01")
    response = row.get("response")
    if (
        not isinstance(response, dict)
        or response.get("status") != "answer"
        or response.get("response_mode") != "scope_redirect"
        or response.get("reason_code") != "high_risk_claim_not_structured"
        or response.get("answer") != OFFICIAL_HANDOFF_ANSWER
        or response.get("claims") != []
        or response.get("evidence") != []
    ):
        raise ValueError("hard-probe migrated handoff case J01 is not deterministic")


def validate_report_semantic_checks(row: dict[str, Any], *, case_id: str) -> None:
    checks = _exact_fields(
        row.get("semantic_checks"),
        {"base_issues", "migration_invariants"},
        f"hard-probe case {case_id} semantic checks",
    )
    base_issues = checks["base_issues"]
    invariants = checks["migration_invariants"]
    if (
        not isinstance(base_issues, list)
        or any(not isinstance(issue, str) for issue in base_issues)
        or not isinstance(invariants, list)
    ):
        raise ValueError(f"hard-probe case {case_id} semantic checks are invalid")
    if row.get("passed") is True and base_issues:
        raise ValueError(f"hard-probe passing case {case_id} reports base semantic issues")
    if case_id in HARD_PROBE_STRUCTURED_TWO_SIDED_IDS:
        expected_names = [
            "at_least_one_claim",
            "at_least_one_evidence",
            "required_publication_kinds",
            "validation_accepted",
            "exact_quote_support",
            "zero_generation_attempts",
            "zero_generation_cost_usd",
        ]
    elif case_id in HARD_PROBE_ACTIVE_QUOTE_ONLY_IDS:
        expected_names = [
            "at_least_one_claim",
            "at_least_one_evidence",
            "required_publication_kinds",
            "validation_accepted",
            "exact_quote_support",
            "zero_generation_attempts",
            "zero_generation_cost_usd",
        ]
    elif case_id == "J01":
        expected_names = [
            "zero_generation_attempts",
            "zero_generation_cost_usd",
            "zero_claims",
            "zero_evidence",
            "official_handoff",
            "required_reason_code",
        ]
    elif case_id in HARD_PROBE_MIXED_MIGRATED_IDS:
        expected_names = [
            "at_least_one_claim",
            "at_least_one_evidence",
            "required_publication_kinds",
            "validation_accepted",
            "exact_quote_support",
            "zero_generation_attempts",
            "zero_generation_cost_usd",
            "required_reason_code",
        ]
    else:
        expected_names = []
    observed_names = []
    for invariant in invariants:
        item = _exact_fields(
            invariant,
            {"name", "expected", "actual", "passed"},
            f"hard-probe case {case_id} migration invariant",
        )
        observed_names.append(item["name"])
        if item["passed"] is not True:
            raise ValueError(f"hard-probe case {case_id} migration invariant did not pass")
    if observed_names != expected_names:
        raise ValueError(f"hard-probe case {case_id} migration invariants are invalid")
