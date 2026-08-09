"""Manual accessibility and wildfire product-safety qualification validation."""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml

from firelens.evaluation.common import (
    ROOT,
    file_sha256,
)
from firelens.evaluation.common import (
    require_digest as _require_digest,
)
from firelens.evaluation.common import (
    require_exact_keys as _require_exact_keys,
)
from firelens.evaluation.common import (
    require_full_git_sha as _require_full_git_sha,
)
from firelens.evaluation.common import (
    require_nonempty_string as _require_nonempty_string,
)
from firelens.evaluation.common import (
    require_timestamp as _require_timestamp,
)
from firelens.evaluation.common import (
    strict_bool as _strict_bool,
)
from firelens.evaluation.common import (
    strict_int as _strict_int,
)
from firelens.evaluation.frontend_manual_protocol import _frontend_manual_review_protocol
from firelens.evaluation.frontend_manual_setup import (
    validate_manual_review_evidence,
    validate_manual_review_setup,
)

FRONTEND_MANUAL_REVIEW_PROTOCOL = ROOT / "data/evaluation/frontend_manual_review.v1.yaml"


def validate_frontend_manual_review(
    bundle_path: Path,
    *,
    expected_commit: str,
    protocol_path: Path = FRONTEND_MANUAL_REVIEW_PROTOCOL,
) -> dict[str, Any]:
    """Validate and recompute the after-only manual frontend qualification."""

    if bundle_path.is_symlink():
        raise ValueError("frontend manual review bundle cannot be a symbolic link")
    try:
        raw_bundle = bundle_path.read_bytes()
    except OSError as error:
        raise ValueError("frontend manual review bundle is not readable") from error
    try:
        bundle = yaml.safe_load(raw_bundle.decode("utf-8"))
    except (UnicodeDecodeError, yaml.YAMLError) as error:
        raise ValueError(
            "frontend manual review bundle is not valid UTF-8 YAML/JSON"
        ) from error
    if not isinstance(bundle, dict):
        raise ValueError("frontend manual review bundle must be an object")
    protocol = _frontend_manual_review_protocol(protocol_path)
    _require_exact_keys(
        bundle,
        {
            "schema_version",
            "protocol",
            "candidate",
            "review_window",
            "role_assignments",
            "test_environments",
            "evidence",
            "coverage",
            "criteria",
            "findings",
            "adjudication",
            "generated_at",
        },
        context="frontend manual review bundle",
    )
    if bundle.get("schema_version") != protocol["bundle_schema_version"]:
        raise ValueError("frontend manual review bundle uses an unsupported schema")
    generated_at = _require_timestamp(
        bundle.get("generated_at"), context="frontend manual review generated_at"
    )
    frozen_at = _require_timestamp(
        protocol.get("frozen_at"), context="frontend manual review protocol frozen_at"
    )

    protocol_binding = bundle.get("protocol")
    if not isinstance(protocol_binding, dict):
        raise ValueError("frontend manual review protocol binding must be an object")
    _require_exact_keys(
        protocol_binding,
        {"protocol_id", "protocol_sha256"},
        context="frontend manual review protocol binding",
    )
    if protocol_binding.get("protocol_id") != protocol["protocol_id"]:
        raise ValueError("frontend manual review bundle targets the wrong protocol")
    submitted_protocol_digest = _require_digest(
        protocol_binding.get("protocol_sha256"),
        context="frontend manual review protocol digest",
    )
    protocol_digest = file_sha256(protocol_path)
    if submitted_protocol_digest != protocol_digest:
        raise ValueError(
            "frontend manual review protocol digest does not match the frozen file"
        )

    commit = _require_full_git_sha(
        expected_commit, context="expected frontend candidate commit"
    )
    candidate = bundle.get("candidate")
    if not isinstance(candidate, dict):
        raise ValueError("frontend manual review candidate binding must be an object")
    _require_exact_keys(
        candidate,
        {
            "candidate_id",
            "commit",
            "target_url",
            "build_verified_at",
            "identity_evidence_id",
        },
        context="frontend manual review candidate binding",
    )
    candidate_commit = _require_full_git_sha(
        candidate.get("commit"), context="frontend manual review candidate commit"
    )
    if candidate_commit != commit:
        raise ValueError("frontend manual review bundle targets the wrong candidate commit")
    candidate_id = _require_nonempty_string(
        candidate.get("candidate_id"), context="frontend manual review candidate ID"
    )
    expected_candidate_id = f"{protocol['candidate_contract']['candidate_id_prefix']}{commit}"
    if candidate_id != expected_candidate_id:
        raise ValueError(
            "frontend manual review candidate ID is not derived from its exact commit"
        )
    target_url = _require_nonempty_string(
        candidate.get("target_url"), context="frontend manual review target URL"
    )
    parsed_url = urlsplit(target_url)
    if (
        parsed_url.scheme not in protocol["candidate_contract"]["allowed_target_url_schemes"]
        or not parsed_url.netloc
        or parsed_url.username is not None
        or parsed_url.password is not None
        or parsed_url.fragment
        or parsed_url.query
        or parsed_url.path not in {"", "/"}
    ):
        raise ValueError("frontend manual review target URL is not canonical")
    identity_evidence_id = _require_nonempty_string(
        candidate.get("identity_evidence_id"),
        context="frontend manual review candidate identity evidence ID",
    )
    build_verified_at = _require_timestamp(
        candidate.get("build_verified_at"), context="frontend candidate build_verified_at"
    )

    review_window = bundle.get("review_window")
    if not isinstance(review_window, dict):
        raise ValueError("frontend manual review window must be an object")
    _require_exact_keys(
        review_window,
        {"started_at", "completed_at"},
        context="frontend manual review window",
    )
    review_started_at = _require_timestamp(
        review_window.get("started_at"), context="frontend manual review started_at"
    )
    review_completed_at = _require_timestamp(
        review_window.get("completed_at"), context="frontend manual review completed_at"
    )
    if not (frozen_at <= build_verified_at <= review_started_at <= review_completed_at):
        raise ValueError(
            "frontend manual review protocol/build/review timestamp chain is invalid"
        )

    setup = validate_manual_review_setup(
        bundle,
        protocol,
        frozen_at=frozen_at,
        review_started_at=review_started_at,
        review_completed_at=review_completed_at,
    )
    assignments = setup.assignments
    assignment_by_role = setup.assignment_by_role
    protocol_profiles = setup.protocol_profiles
    environment_by_profile = setup.environment_by_profile
    reviewer_ids = setup.reviewer_ids
    retained_evidence = validate_manual_review_evidence(
        bundle_path,
        bundle,
        protocol,
        environment_by_profile,
        review_started_at=review_started_at,
        review_completed_at=review_completed_at,
        identity_evidence_id=identity_evidence_id,
        target_url=target_url,
        candidate_id=candidate_id,
        commit=commit,
    )
    evidence_rows = retained_evidence.rows
    evidence_by_id = retained_evidence.by_id

    coverage_rows = bundle.get("coverage")
    expected_coverage = [
        (profile["id"], state_id)
        for profile in protocol_profiles
        for state_id in protocol["state_roster"]
    ]
    if not isinstance(coverage_rows, list) or len(coverage_rows) != len(expected_coverage):
        raise ValueError(
            "frontend manual review environment/state coverage roster is incomplete"
        )
    coverage_by_id: dict[str, dict[str, Any]] = {}
    coverage_order: list[str] = []
    coverage_track_statuses: dict[str, list[str]] = {
        "accessibility": [],
        "product_safety": [],
    }
    role_latest_coverage: dict[str, datetime] = {}
    used_evidence_ids: set[str] = set()
    for index, ((expected_profile_id, expected_state_id), coverage) in enumerate(
        zip(expected_coverage, coverage_rows, strict=True)
    ):
        context = f"frontend manual review coverage {index}"
        if not isinstance(coverage, dict):
            raise ValueError(f"{context} must be an object")
        _require_exact_keys(
            coverage,
            {
                "profile_id",
                "state_id",
                "status",
                "reviewer_id",
                "observed_at",
                "evidence_ids",
                "notes",
            },
            context=context,
        )
        if (
            coverage.get("profile_id") != expected_profile_id
            or coverage.get("state_id") != expected_state_id
        ):
            raise ValueError(
                "frontend manual review environment/state coverage differs from the frozen matrix"
            )
        expected_profile = next(
            profile for profile in protocol_profiles if profile["id"] == expected_profile_id
        )
        expected_reviewer = assignment_by_role[expected_profile["required_role"]]
        if coverage.get("reviewer_id") != expected_reviewer["reviewer_id"]:
            raise ValueError(f"{context} was not performed by its designated reviewer")
        status = coverage.get("status")
        if status not in {"pass", "fail", "not_tested"}:
            raise ValueError(f"{context} status is invalid")
        evidence_ids = coverage.get("evidence_ids")
        if (
            not isinstance(evidence_ids, list)
            or not evidence_ids
            or len(evidence_ids) != len(set(evidence_ids))
            or any(evidence_id not in evidence_by_id for evidence_id in evidence_ids)
        ):
            raise ValueError(f"{context} must reference unique retained evidence")
        if any(
            expected_profile_id not in evidence_by_id[str(evidence_id)]["profile_ids"]
            or expected_state_id not in evidence_by_id[str(evidence_id)]["state_ids"]
            for evidence_id in evidence_ids
        ):
            raise ValueError(f"{context} evidence does not bind its profile and state")
        observed_at = _require_timestamp(
            coverage.get("observed_at"), context=f"{context} observed_at"
        )
        if not (
            environment_by_profile[expected_profile_id]["verified_at_parsed"]
            <= observed_at
            <= review_completed_at
        ) or any(
            evidence_by_id[str(evidence_id)]["captured_at_parsed"] > observed_at
            for evidence_id in evidence_ids
        ):
            raise ValueError(f"{context} evidence/observation timestamp chain is invalid")
        _require_nonempty_string(coverage.get("notes"), context=f"{context} notes")
        coverage_id = f"{expected_profile_id}/{expected_state_id}"
        coverage_order.append(coverage_id)
        coverage_by_id[coverage_id] = {
            **coverage,
            "observed_at_parsed": observed_at,
            "track": (
                "accessibility"
                if expected_profile["required_role"] == "accessibility_specialist"
                else "product_safety"
            ),
        }
        coverage_track_statuses[coverage_by_id[coverage_id]["track"]].append(str(status))
        profile_role = str(expected_profile["required_role"])
        role_latest_coverage[profile_role] = max(
            observed_at, role_latest_coverage.get(profile_role, observed_at)
        )
        used_evidence_ids.update(str(evidence_id) for evidence_id in evidence_ids)

    protocol_criteria = protocol["criteria"]
    submitted_criteria = bundle.get("criteria")
    if not isinstance(submitted_criteria, list) or len(submitted_criteria) != len(
        protocol_criteria
    ):
        raise ValueError("frontend manual review criterion roster is incomplete")
    checks_by_id: dict[str, dict[str, Any]] = {}
    check_order: list[str] = []
    criterion_order: list[str] = []
    role_latest_check: dict[str, datetime] = {}
    track_statuses: dict[str, list[str]] = {"accessibility": [], "product_safety": []}
    for criterion_index, (expected_criterion, submitted_criterion) in enumerate(
        zip(protocol_criteria, submitted_criteria, strict=True)
    ):
        context = f"frontend manual review criterion {criterion_index}"
        if not isinstance(submitted_criterion, dict):
            raise ValueError(f"{context} must be an object")
        _require_exact_keys(
            submitted_criterion, {"criterion_id", "atomic_checks"}, context=context
        )
        criterion_id = submitted_criterion.get("criterion_id")
        if criterion_id != expected_criterion["id"]:
            raise ValueError(
                "frontend manual review criterion roster differs from the protocol"
            )
        criterion_order.append(str(criterion_id))
        expected_checks = expected_criterion["atomic_checks"]
        submitted_checks = submitted_criterion.get("atomic_checks")
        if not isinstance(submitted_checks, list) or len(submitted_checks) != len(
            expected_checks
        ):
            raise ValueError(f"{context} atomic-check roster is incomplete")
        required_role = expected_criterion["required_role"]
        required_reviewer = assignment_by_role[required_role]
        for check_index, (expected_check, submitted_check) in enumerate(
            zip(expected_checks, submitted_checks, strict=True)
        ):
            check_context = f"{context} atomic check {check_index}"
            if not isinstance(submitted_check, dict):
                raise ValueError(f"{check_context} must be an object")
            _require_exact_keys(
                submitted_check,
                {"check_id", "status", "reviewer_id", "reviewed_at", "evidence_ids", "notes"},
                context=check_context,
            )
            check_id = submitted_check.get("check_id")
            if check_id != expected_check["id"] or check_id in checks_by_id:
                raise ValueError(
                    "frontend manual review atomic-check roster differs from the protocol"
                )
            status = submitted_check.get("status")
            if status not in {"pass", "fail", "not_tested"}:
                raise ValueError(f"{check_context} status is invalid")
            reviewer_id = submitted_check.get("reviewer_id")
            if reviewer_id != required_reviewer["reviewer_id"]:
                raise ValueError(
                    f"{check_context} was not performed by its designated specialist"
                )
            reviewed_at = _require_timestamp(
                submitted_check.get("reviewed_at"), context=f"{check_context} reviewed_at"
            )
            evidence_ids = submitted_check.get("evidence_ids")
            if (
                not isinstance(evidence_ids, list)
                or not evidence_ids
                or len(evidence_ids) != len(set(evidence_ids))
                or any(evidence_id not in evidence_by_id for evidence_id in evidence_ids)
            ):
                raise ValueError(f"{check_context} must reference unique retained evidence")
            latest_evidence = max(
                evidence_by_id[str(evidence_id)]["captured_at_parsed"]
                for evidence_id in evidence_ids
            )
            evidenced_profiles = {
                str(profile_id)
                for evidence_id in evidence_ids
                for profile_id in evidence_by_id[str(evidence_id)]["profile_ids"]
            }
            required_profiles = set(
                protocol["atomic_check_requirements"][str(check_id)]["required_profile_ids"]
            )
            if not required_profiles.issubset(evidenced_profiles):
                raise ValueError(
                    f"{check_context} evidence omits required test profiles: "
                    f"{sorted(required_profiles - evidenced_profiles)}"
                )
            if not (latest_evidence <= reviewed_at <= review_completed_at):
                raise ValueError(f"{check_context} evidence/review timestamp chain is invalid")
            if reviewed_at < required_reviewer["assigned_at_parsed"]:
                raise ValueError(f"{check_context} predates its reviewer assignment")
            _require_nonempty_string(
                submitted_check.get("notes"), context=f"{check_context} notes"
            )
            role_latest_check[required_role] = max(
                reviewed_at, role_latest_check.get(required_role, reviewed_at)
            )
            used_evidence_ids.update(str(evidence_id) for evidence_id in evidence_ids)
            check_order.append(str(check_id))
            track_statuses[expected_criterion["track"]].append(str(status))
            checks_by_id[str(check_id)] = {
                **submitted_check,
                "reviewed_at_parsed": reviewed_at,
                "track": expected_criterion["track"],
            }

    for role in ("accessibility_specialist", "wildfire_product_safety_reviewer"):
        assignment = assignment_by_role[role]
        latest_activity = max(role_latest_check[role], role_latest_coverage[role])
        if not (latest_activity <= assignment["attested_at_parsed"] <= review_completed_at):
            raise ValueError(f"frontend manual review {role} attestation chain is invalid")

    findings = bundle.get("findings")
    if not isinstance(findings, list):
        raise ValueError("frontend manual review findings must be a list")
    finding_ids: set[str] = set()
    open_findings_by_target: Counter[tuple[str, str]] = Counter()
    open_finding_count = 0
    for index, finding in enumerate(findings):
        context = f"frontend manual review finding {index}"
        if not isinstance(finding, dict):
            raise ValueError(f"{context} must be an object")
        _require_exact_keys(
            finding,
            {
                "finding_id",
                "target_type",
                "target_id",
                "severity",
                "status",
                "opened_at",
                "resolved_at",
                "owner_id",
                "resolution",
                "evidence_ids",
            },
            context=context,
        )
        finding_id = _require_nonempty_string(
            finding.get("finding_id"), context=f"{context} ID"
        )
        if not re.fullmatch(r"F-[0-9]{3,}", finding_id) or finding_id in finding_ids:
            raise ValueError("frontend manual review finding IDs must be unique canonical IDs")
        finding_ids.add(finding_id)
        target_type = finding.get("target_type")
        target_id = finding.get("target_id")
        if target_type == "atomic_check":
            if target_id not in checks_by_id:
                raise ValueError(f"{context} references an unknown atomic check")
            target_reviewed_at = checks_by_id[str(target_id)]["reviewed_at_parsed"]
        elif target_type == "environment_state":
            if target_id not in coverage_by_id:
                raise ValueError(f"{context} references unknown environment/state coverage")
            target_reviewed_at = coverage_by_id[str(target_id)]["observed_at_parsed"]
        else:
            raise ValueError(f"{context} target type is invalid")
        if finding.get("severity") not in {"critical", "high", "medium", "low"}:
            raise ValueError(f"{context} severity is invalid")
        status = finding.get("status")
        if status not in {"open", "resolved"}:
            raise ValueError(f"{context} status is invalid")
        owner_id = _require_nonempty_string(
            finding.get("owner_id"), context=f"{context} owner ID"
        )
        if owner_id.casefold() not in reviewer_ids:
            raise ValueError(f"{context} owner is not in the named role registry")
        evidence_ids = finding.get("evidence_ids")
        if (
            not isinstance(evidence_ids, list)
            or not evidence_ids
            or len(evidence_ids) != len(set(evidence_ids))
            or any(evidence_id not in evidence_by_id for evidence_id in evidence_ids)
        ):
            raise ValueError(f"{context} must reference unique retained evidence")
        used_evidence_ids.update(str(evidence_id) for evidence_id in evidence_ids)
        opened_at = _require_timestamp(finding.get("opened_at"), context=f"{context} opened_at")
        if not (review_started_at <= opened_at <= target_reviewed_at):
            raise ValueError(f"{context} opened/reviewed timestamp chain is invalid")
        if any(
            evidence_by_id[str(evidence_id)]["captured_at_parsed"] > target_reviewed_at
            for evidence_id in evidence_ids
        ):
            raise ValueError(f"{context} references evidence captured after final review")
        if status == "open":
            if finding.get("resolved_at") is not None or finding.get("resolution") is not None:
                raise ValueError(f"{context} open finding cannot claim a resolution")
            open_findings_by_target[(str(target_type), str(target_id))] += 1
            open_finding_count += 1
        else:
            resolved_at = _require_timestamp(
                finding.get("resolved_at"), context=f"{context} resolved_at"
            )
            if not (opened_at <= resolved_at <= target_reviewed_at):
                raise ValueError(f"{context} resolution/review timestamp chain is invalid")
            _require_nonempty_string(finding.get("resolution"), context=f"{context} resolution")

    for check_id, check in checks_by_id.items():
        has_open_finding = open_findings_by_target[("atomic_check", check_id)] > 0
        if check["status"] == "pass" and has_open_finding:
            raise ValueError(
                f"frontend manual review check {check_id} passes with an open finding"
            )
        if check["status"] != "pass" and not has_open_finding:
            raise ValueError(
                f"frontend manual review non-passing check {check_id} requires an open finding"
            )
    for coverage_id, coverage in coverage_by_id.items():
        has_open_finding = open_findings_by_target[("environment_state", coverage_id)] > 0
        if coverage["status"] == "pass" and has_open_finding:
            raise ValueError(
                f"frontend manual review coverage {coverage_id} passes with an open finding"
            )
        if coverage["status"] != "pass" and not has_open_finding:
            raise ValueError(
                f"frontend manual review non-passing coverage {coverage_id} requires an open finding"
            )

    if used_evidence_ids != set(evidence_by_id):
        unused = sorted(set(evidence_by_id) - used_evidence_ids)
        raise ValueError(f"frontend manual review contains unused evidence padding: {unused}")

    accessibility_qualified = all(
        status == "pass"
        for status in [
            *track_statuses["accessibility"],
            *coverage_track_statuses["accessibility"],
        ]
    )
    product_safety_qualified = all(
        status == "pass"
        for status in [
            *track_statuses["product_safety"],
            *coverage_track_statuses["product_safety"],
        ]
    )
    qualified = accessibility_qualified and product_safety_qualified and open_finding_count == 0

    adjudication = bundle.get("adjudication")
    if not isinstance(adjudication, dict):
        raise ValueError("frontend manual review adjudication must be an object")
    _require_exact_keys(
        adjudication,
        {
            "adjudicator_id",
            "decision",
            "decided_at",
            "accessibility_qualified",
            "product_safety_qualified",
            "open_finding_count",
            "criterion_ids",
            "atomic_check_ids",
            "test_profile_ids",
            "state_ids",
            "coverage_ids",
            "evidence_ids",
            "attestation",
        },
        context="frontend manual review adjudication",
    )
    adjudicator = assignment_by_role["release_adjudicator"]
    if adjudication.get("adjudicator_id") != adjudicator["reviewer_id"]:
        raise ValueError(
            "frontend manual review decision was not made by the release adjudicator"
        )
    decided_at = _require_timestamp(
        adjudication.get("decided_at"), context="frontend manual review adjudication decided_at"
    )
    if not (
        review_completed_at <= decided_at <= adjudicator["attested_at_parsed"] <= generated_at
    ):
        raise ValueError("frontend manual review adjudication timestamp chain is invalid")
    expected_decision = "qualified" if qualified else "not_qualified"
    if adjudication.get("decision") != expected_decision:
        raise ValueError("frontend manual review decision differs from recomputed evidence")
    submitted_accessibility = _strict_bool(
        adjudication,
        "accessibility_qualified",
        "frontend manual review adjudication",
    )
    submitted_product_safety = _strict_bool(
        adjudication,
        "product_safety_qualified",
        "frontend manual review adjudication",
    )
    submitted_open_findings = _strict_int(
        adjudication,
        "open_finding_count",
        "frontend manual review adjudication",
        minimum=0,
    )
    if (
        submitted_accessibility != accessibility_qualified
        or submitted_product_safety != product_safety_qualified
        or submitted_open_findings != open_finding_count
    ):
        raise ValueError(
            "frontend manual review adjudication summary differs from raw evidence"
        )
    if adjudication.get("criterion_ids") != criterion_order:
        raise ValueError("frontend manual review adjudication omits or reorders criteria")
    if adjudication.get("atomic_check_ids") != check_order:
        raise ValueError("frontend manual review adjudication omits or reorders atomic checks")
    if adjudication.get("test_profile_ids") != list(environment_by_profile):
        raise ValueError("frontend manual review adjudication omits or reorders test profiles")
    if adjudication.get("state_ids") != protocol["state_roster"]:
        raise ValueError("frontend manual review adjudication omits or reorders states")
    if adjudication.get("coverage_ids") != coverage_order:
        raise ValueError("frontend manual review adjudication omits or reorders coverage")
    if adjudication.get("evidence_ids") != list(evidence_by_id):
        raise ValueError("frontend manual review adjudication omits or reorders evidence")
    _require_nonempty_string(
        adjudication.get("attestation"),
        context="frontend manual review adjudication attestation",
    )

    return {
        "status": "complete",
        "protocol_id": protocol["protocol_id"],
        "protocol_sha256": protocol_digest,
        "bundle_sha256": hashlib.sha256(raw_bundle).hexdigest(),
        "candidate_id": candidate_id,
        "commit": commit,
        "target_url": target_url,
        "build_verified_at": candidate["build_verified_at"],
        "review_started_at": review_window["started_at"],
        "review_completed_at": review_window["completed_at"],
        "decided_at": adjudication["decided_at"],
        "generated_at": bundle["generated_at"],
        "roles": [
            {
                "role": assignment["role"],
                "reviewer_id": assignment["reviewer_id"],
                "reviewer_name": assignment["reviewer_name"],
                "attested_at": assignment["attested_at"],
            }
            for assignment in assignments
        ],
        "criterion_ids": criterion_order,
        "atomic_check_ids": check_order,
        "test_profile_ids": list(environment_by_profile),
        "state_ids": protocol["state_roster"],
        "coverage_ids": coverage_order,
        "criterion_count": len(criterion_order),
        "atomic_check_count": len(check_order),
        "test_profile_count": len(environment_by_profile),
        "state_count": len(protocol["state_roster"]),
        "coverage_count": len(coverage_by_id),
        "evidence_count": len(evidence_by_id),
        "evidence_manifest": [
            {
                "evidence_id": evidence["evidence_id"],
                "path": evidence["path"],
                "sha256": evidence["sha256"],
                "bytes": evidence["bytes"],
                "media_type": evidence["media_type"],
                "profile_ids": evidence["profile_ids"],
                "state_ids": evidence["state_ids"],
            }
            for evidence in evidence_rows
        ],
        "finding_count": len(findings),
        "open_finding_count": open_finding_count,
        "accessibility_qualified": accessibility_qualified,
        "product_safety_qualified": product_safety_qualified,
        "qualified": qualified,
    }
