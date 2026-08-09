"""Semantic development registry, holdout manifest, and candidate identity validation."""

from __future__ import annotations

import hashlib
from collections import Counter
from pathlib import Path
from typing import Any

from firelens.evaluation.common import (
    read_report as _read_report,
)
from firelens.evaluation.common import (
    require_digest as _require_digest,
)
from firelens.evaluation.common import (
    require_exact_keys as _require_exact_keys,
)
from firelens.evaluation.common import (
    require_nonempty_string as _require_nonempty_string,
)
from firelens.evaluation.common import (
    require_timestamp as _require_timestamp,
)
from firelens.evaluation.common import (
    sha256_json as _sha256_json,
)
from firelens.evaluation.common import (
    strict_bool as _strict_bool,
)
from firelens.evaluation.common import (
    strict_int as _strict_int,
)


def _sorted_unique_strings(
    value: Any,
    *,
    context: str,
    minimum: int = 1,
) -> list[str]:
    if not isinstance(value, list) or len(value) < minimum:
        raise ValueError(f"{context} must contain at least {minimum} values")
    parsed = [
        _require_nonempty_string(item, context=f"{context} item {index}")
        for index, item in enumerate(value)
    ]
    if parsed != sorted(parsed) or len(parsed) != len(set(parsed)):
        raise ValueError(f"{context} must be sorted and unique")
    return parsed


def _semantic_development_registry_payload(
    registry: dict[str, Any],
) -> dict[str, Any]:
    _require_exact_keys(
        registry,
        {
            "registry_version",
            "registry_id",
            "frozen_at",
            "dataset_roster_sha256",
            "datasets",
            "source_id_sha256s",
            "source_roster_sha256",
            "question_family_ids",
            "question_family_roster_sha256",
        },
        context="semantic development exposure registry",
    )
    if registry.get("registry_version") != "firelens_semantic_development_exposure_registry.v1":
        raise ValueError("semantic development exposure registry uses an unsupported version")
    _require_nonempty_string(
        registry.get("registry_id"), context="semantic development registry ID"
    )
    _require_timestamp(
        registry.get("frozen_at"), context="semantic development registry frozen_at"
    )
    _require_digest(
        registry.get("dataset_roster_sha256"),
        context="semantic development dataset-roster commitment",
    )
    _require_digest(
        registry.get("source_roster_sha256"),
        context="semantic development source-roster commitment",
    )
    _require_digest(
        registry.get("question_family_roster_sha256"),
        context="semantic development question-family-roster commitment",
    )
    datasets = registry.get("datasets")
    if not isinstance(datasets, list) or not datasets:
        raise ValueError("semantic development registry requires dataset exposures")
    dataset_ids, aggregate_sources, aggregate_families = _development_dataset_rosters(datasets)
    if dataset_ids != sorted(dataset_ids) or len(dataset_ids) != len(set(dataset_ids)):
        raise ValueError("semantic development dataset roster must be sorted and unique")
    if registry["dataset_roster_sha256"] != _sha256_json(datasets):
        raise ValueError("semantic development dataset-roster digest is inconsistent")
    source_roster = _sorted_unique_strings(
        registry.get("source_id_sha256s"),
        context="semantic development source roster",
        minimum=1,
    )
    for source in source_roster:
        _require_digest(source, context="semantic development source ID commitment")
    if source_roster != sorted(aggregate_sources):
        raise ValueError("semantic development source roster differs from dataset exposures")
    if registry["source_roster_sha256"] != _sha256_json(source_roster):
        raise ValueError("semantic development source-roster digest is inconsistent")
    family_roster = _sorted_unique_strings(
        registry.get("question_family_ids"),
        context="semantic development question-family roster",
        minimum=5,
    )
    if family_roster != sorted(aggregate_families):
        raise ValueError(
            "semantic development question-family roster differs from dataset exposures"
        )
    if registry["question_family_roster_sha256"] != _sha256_json(family_roster):
        raise ValueError("semantic development question-family-roster digest is inconsistent")
    return registry


def _development_dataset_rosters(
    datasets: list[Any],
) -> tuple[list[str], set[str], set[str]]:
    dataset_ids: list[str] = []
    aggregate_sources: set[str] = set()
    aggregate_families: set[str] = set()
    for index, row in enumerate(datasets):
        if not isinstance(row, dict):
            raise ValueError(f"semantic development dataset {index} must be an object")
        _require_exact_keys(
            row,
            {
                "dataset_id",
                "dataset_sha256",
                "source_id_sha256s",
                "question_family_ids",
            },
            context=f"semantic development dataset {index}",
        )
        dataset_ids.append(
            _require_nonempty_string(row.get("dataset_id"), context="development dataset ID")
        )
        _require_digest(
            row.get("dataset_sha256"), context=f"development dataset {index} digest"
        )
        sources = _sorted_unique_strings(
            row.get("source_id_sha256s"),
            context=f"semantic development dataset {index} source roster",
            minimum=0,
        )
        for source in sources:
            _require_digest(
                source, context=f"semantic development dataset {index} source ID commitment"
            )
        families = _sorted_unique_strings(
            row.get("question_family_ids"),
            context=f"semantic development dataset {index} question-family roster",
            minimum=1,
        )
        aggregate_sources.update(sources)
        aggregate_families.update(families)
    return dataset_ids, aggregate_sources, aggregate_families


def _semantic_development_registry(path: Path) -> dict[str, Any]:
    registry = _read_report(path)
    if registry is None:
        raise ValueError("semantic development exposure registry is missing")
    return _semantic_development_registry_payload(registry)


def _semantic_holdout_manifest_payload(
    manifest: dict[str, Any],
    *,
    development_registry: dict[str, Any],
    development_registry_sha256: str,
) -> dict[str, Any]:
    _require_exact_keys(
        manifest,
        {
            "manifest_version",
            "dataset_sha256",
            "case_roster_sha256",
            "case_count",
            "case_roster",
            "source_id_sha256s",
            "source_roster_sha256",
            "question_family_ids",
            "question_family_roster_sha256",
            "question_family_distribution",
            "development_registry_id",
            "development_registry_sha256",
            "disjointness_audit",
            "frozen_before_candidate",
            "double_review_required",
            "frozen_at",
        },
        context="semantic holdout manifest",
    )
    if manifest.get("manifest_version") != "firelens_semantic_holdout_manifest.v3":
        raise ValueError("semantic holdout manifest uses an unsupported version")
    _require_digest(
        manifest.get("dataset_sha256"), context="semantic holdout dataset commitment"
    )
    _require_digest(
        manifest.get("case_roster_sha256"), context="semantic holdout case-roster commitment"
    )
    _require_digest(
        manifest.get("source_roster_sha256"),
        context="semantic holdout source-roster commitment",
    )
    _require_digest(
        manifest.get("question_family_roster_sha256"),
        context="semantic holdout question-family-roster commitment",
    )
    registry_digest = _require_digest(
        development_registry_sha256, context="semantic development registry digest"
    )
    if manifest.get("development_registry_id") != development_registry["registry_id"]:
        raise ValueError("semantic holdout manifest uses the wrong development registry")
    if manifest.get("development_registry_sha256") != registry_digest:
        raise ValueError("semantic holdout manifest does not bind the development registry")
    frozen_at = _require_timestamp(
        manifest.get("frozen_at"), context="semantic holdout frozen_at"
    )
    for key in ("frozen_before_candidate", "double_review_required"):
        if not _strict_bool(manifest, key, "semantic holdout manifest"):
            raise ValueError(f"semantic holdout manifest requires {key}")
    case_count = _strict_int(manifest, "case_count", "semantic holdout manifest", minimum=25)
    roster = manifest.get("case_roster")
    if not isinstance(roster, list) or len(roster) != case_count:
        raise ValueError("semantic holdout manifest case roster differs from case_count")
    case_ids: list[str] = []
    aggregate_sources: set[str] = set()
    family_counts: Counter[str] = Counter()
    for index, row in enumerate(roster):
        if not isinstance(row, dict):
            raise ValueError(f"semantic holdout roster row {index} must be an object")
        _require_exact_keys(
            row,
            {
                "case_id",
                "input_sha256",
                "source_id_sha256s",
                "question_family_id",
            },
            context=f"semantic holdout roster row {index}",
        )
        case_ids.append(
            _require_nonempty_string(
                row.get("case_id"), context=f"semantic holdout roster row {index} case_id"
            )
        )
        _require_digest(
            row.get("input_sha256"),
            context=f"semantic holdout roster row {index} input_sha256",
        )
        sources = _sorted_unique_strings(
            row.get("source_id_sha256s"),
            context=f"semantic holdout roster row {index} source roster",
        )
        for source in sources:
            _require_digest(
                source, context=f"semantic holdout roster row {index} source ID commitment"
            )
        family = _require_nonempty_string(
            row.get("question_family_id"),
            context=f"semantic holdout roster row {index} question family",
        )
        aggregate_sources.update(sources)
        family_counts[family] += 1
    if case_ids != sorted(case_ids) or len(case_ids) != len(set(case_ids)):
        raise ValueError("semantic holdout manifest case roster must use unique canonical IDs")
    if manifest["case_roster_sha256"] != _sha256_json(roster):
        raise ValueError("semantic holdout manifest case-roster digest does not match its rows")
    source_roster = _sorted_unique_strings(
        manifest.get("source_id_sha256s"), context="semantic holdout source roster"
    )
    for source in source_roster:
        _require_digest(source, context="semantic holdout source ID commitment")
    if source_roster != sorted(aggregate_sources):
        raise ValueError("semantic holdout source roster differs from case-level sources")
    if manifest["source_roster_sha256"] != _sha256_json(source_roster):
        raise ValueError("semantic holdout source-roster digest is inconsistent")
    family_roster = _sorted_unique_strings(
        manifest.get("question_family_ids"),
        context="semantic holdout question-family roster",
        minimum=5,
    )
    if family_roster != sorted(family_counts):
        raise ValueError("semantic holdout question-family roster differs from cases")
    if manifest["question_family_roster_sha256"] != _sha256_json(family_roster):
        raise ValueError("semantic holdout question-family-roster digest is inconsistent")
    family_distribution = manifest.get("question_family_distribution")
    if not isinstance(family_distribution, dict) or len(family_distribution) < 5:
        raise ValueError("semantic holdout manifest requires at least five question families")
    valid_family_counts = all(
        isinstance(value, int) and not isinstance(value, bool) and value >= 1
        for value in family_distribution.values()
    )
    if not valid_family_counts or family_distribution != dict(sorted(family_counts.items())):
        raise ValueError("semantic holdout family distribution does not match its cases")

    audit = manifest.get("disjointness_audit")
    if not isinstance(audit, dict):
        raise ValueError("semantic holdout disjointness audit must be an object")
    _require_exact_keys(
        audit,
        {
            "audit_version",
            "audited_at",
            "development_registry_sha256",
            "development_source_roster_sha256",
            "development_question_family_roster_sha256",
            "holdout_source_roster_sha256",
            "holdout_question_family_roster_sha256",
            "source_overlap_id_sha256s",
            "question_family_overlap_ids",
            "source_disjoint_from_development",
            "question_family_disjoint_from_development",
        },
        context="semantic holdout disjointness audit",
    )
    if audit.get("audit_version") != "firelens_semantic_disjointness_audit.v1":
        raise ValueError("semantic holdout disjointness audit uses an unsupported version")
    audited_at = _require_timestamp(
        audit.get("audited_at"), context="semantic holdout disjointness audited_at"
    )
    development_frozen_at = _require_timestamp(
        development_registry.get("frozen_at"),
        context="semantic development registry frozen_at",
    )
    if audited_at < development_frozen_at or audited_at > frozen_at:
        raise ValueError("semantic holdout disjointness audit timestamps are out of order")
    expected_audit_digests = {
        "development_registry_sha256": registry_digest,
        "development_source_roster_sha256": development_registry["source_roster_sha256"],
        "development_question_family_roster_sha256": development_registry[
            "question_family_roster_sha256"
        ],
        "holdout_source_roster_sha256": manifest["source_roster_sha256"],
        "holdout_question_family_roster_sha256": manifest["question_family_roster_sha256"],
    }
    for key, expected in expected_audit_digests.items():
        _require_digest(audit.get(key), context=f"semantic disjointness audit {key}")
        if audit[key] != expected:
            raise ValueError(f"semantic holdout disjointness audit has the wrong {key}")
    source_overlap = sorted(set(source_roster) & set(development_registry["source_id_sha256s"]))
    family_overlap = sorted(
        set(family_roster) & set(development_registry["question_family_ids"])
    )
    if audit.get("source_overlap_id_sha256s") != source_overlap:
        raise ValueError("semantic holdout source-overlap audit is inconsistent")
    if audit.get("question_family_overlap_ids") != family_overlap:
        raise ValueError("semantic holdout question-family-overlap audit is inconsistent")
    source_disjoint = _strict_bool(
        audit, "source_disjoint_from_development", "semantic holdout disjointness audit"
    )
    family_disjoint = _strict_bool(
        audit,
        "question_family_disjoint_from_development",
        "semantic holdout disjointness audit",
    )
    if source_disjoint != (not source_overlap) or family_disjoint != (not family_overlap):
        raise ValueError("semantic holdout disjointness flags disagree with recomputed overlap")
    if not source_disjoint or not family_disjoint:
        raise ValueError("semantic holdout is not source and question-family disjoint")
    return manifest


def _semantic_holdout_manifest(
    path: Path,
    *,
    development_registry: dict[str, Any],
    development_registry_sha256: str,
) -> dict[str, Any]:
    manifest = _read_report(path)
    if manifest is None:
        raise ValueError("semantic holdout manifest is missing")
    return _semantic_holdout_manifest_payload(
        manifest,
        development_registry=development_registry,
        development_registry_sha256=development_registry_sha256,
    )


def _semantic_holdout_candidate_report(
    report: dict[str, Any],
    *,
    manifest: dict[str, Any],
    dataset_manifest_sha256: str,
) -> dict[str, Any]:
    _require_exact_keys(
        report,
        {
            "report_version",
            "candidate_id",
            "candidate_identity_sha256",
            "generated_at",
            "commit",
            "corpus_sha256",
            "vector_matrix_sha256",
            "document_context_sha256",
            "repairs_sha256",
            "configuration_sha256",
            "dataset_sha256",
            "dataset_manifest_sha256",
            "case_count",
            "cases",
        },
        context="semantic holdout candidate report",
    )
    if report.get("report_version") != "firelens_semantic_holdout_report.v1":
        raise ValueError("semantic holdout candidate report uses an unsupported version")
    candidate_id = _require_nonempty_string(
        report.get("candidate_id"), context="semantic holdout candidate_id"
    )
    generated_at = _require_timestamp(
        report.get("generated_at"), context="semantic holdout report generated_at"
    )
    if (
        _require_timestamp(
            manifest.get("frozen_at"), context="semantic holdout manifest frozen_at"
        )
        >= generated_at
    ):
        raise ValueError("semantic holdout manifest was not frozen before candidate generation")
    commit = _require_nonempty_string(
        report.get("commit"), context="semantic holdout candidate commit"
    )
    if len(commit) not in {40, 64} or any(
        character not in "0123456789abcdef" for character in commit
    ):
        raise ValueError("semantic holdout candidate commit must be a Git object ID")
    for key in (
        "candidate_identity_sha256",
        "corpus_sha256",
        "vector_matrix_sha256",
        "repairs_sha256",
        "configuration_sha256",
        "dataset_sha256",
        "dataset_manifest_sha256",
    ):
        _require_digest(report.get(key), context=f"semantic holdout report {key}")
    _require_digest(
        report.get("document_context_sha256"),
        context="semantic holdout report document_context_sha256",
        optional=True,
    )
    if report["dataset_sha256"] != manifest["dataset_sha256"]:
        raise ValueError("semantic holdout report uses the wrong dataset commitment")
    if report["dataset_manifest_sha256"] != dataset_manifest_sha256:
        raise ValueError("semantic holdout report uses the wrong manifest")
    candidate_identity = {
        "candidate_id": candidate_id,
        "commit": commit,
        "corpus_sha256": report["corpus_sha256"],
        "vector_matrix_sha256": report["vector_matrix_sha256"],
        "document_context_sha256": report["document_context_sha256"],
        "repairs_sha256": report["repairs_sha256"],
        "configuration_sha256": report["configuration_sha256"],
    }
    if report["candidate_identity_sha256"] != _sha256_json(candidate_identity):
        raise ValueError("semantic holdout candidate identity digest is inconsistent")
    case_count = _strict_int(
        report, "case_count", "semantic holdout candidate report", minimum=25
    )
    if case_count != manifest["case_count"]:
        raise ValueError("semantic holdout candidate report case_count differs from manifest")
    cases = report.get("cases")
    if not isinstance(cases, list) or len(cases) != case_count:
        raise ValueError("semantic holdout candidate report must retain every case")
    expected_roster = manifest["case_roster"]
    expected_case_ids = [row["case_id"] for row in expected_roster]
    expected_input_hashes = {row["case_id"]: row["input_sha256"] for row in expected_roster}
    actual_case_ids: list[str] = []
    for case_index, case in enumerate(cases):
        if not isinstance(case, dict):
            raise ValueError(f"semantic holdout report case {case_index} must be an object")
        _require_exact_keys(
            case,
            {"case_id", "input_sha256", "response", "response_sha256", "claims"},
            context=f"semantic holdout report case {case_index}",
        )
        case_id = _require_nonempty_string(
            case.get("case_id"), context=f"semantic holdout report case {case_index} case_id"
        )
        actual_case_ids.append(case_id)
        if case.get("input_sha256") != expected_input_hashes.get(case_id):
            raise ValueError(f"semantic holdout report case {case_id} input is not committed")
        response = case.get("response")
        if not isinstance(response, str) or not response.strip():
            raise ValueError(
                f"semantic holdout report case {case_id} response must be a non-empty string"
            )
        _require_digest(
            case.get("response_sha256"),
            context=f"semantic holdout report case {case_id} response_sha256",
        )
        if case["response_sha256"] != hashlib.sha256(response.encode("utf-8")).hexdigest():
            raise ValueError(f"semantic holdout report case {case_id} response digest is wrong")
        claims = case.get("claims")
        if not isinstance(claims, list) or not claims:
            raise ValueError(f"semantic holdout report case {case_id} has no reviewable claims")
        claim_ids: list[str] = []
        for claim_index, claim in enumerate(claims):
            if not isinstance(claim, dict):
                raise ValueError(
                    f"semantic holdout report case {case_id} claim {claim_index} must be an object"
                )
            _require_exact_keys(
                claim,
                {"claim_id", "text", "text_sha256"},
                context=f"semantic holdout report case {case_id} claim {claim_index}",
            )
            claim_id = _require_nonempty_string(
                claim.get("claim_id"),
                context=f"semantic holdout report case {case_id} claim {claim_index} claim_id",
            )
            claim_ids.append(claim_id)
            text = claim.get("text")
            if not isinstance(text, str) or not text.strip():
                raise ValueError(
                    f"semantic holdout report case {case_id} claim {claim_id} text "
                    "must be a non-empty string"
                )
            _require_digest(
                claim.get("text_sha256"),
                context=f"semantic holdout report case {case_id} claim {claim_id} text_sha256",
            )
            if claim["text_sha256"] != hashlib.sha256(text.encode("utf-8")).hexdigest():
                raise ValueError(
                    f"semantic holdout report case {case_id} claim {claim_id} digest is wrong"
                )
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError(f"semantic holdout report case {case_id} repeats claim IDs")
    if actual_case_ids != expected_case_ids:
        raise ValueError(
            "semantic holdout candidate report roster differs from frozen manifest"
        )
    return report
