"""Role, environment, and retained-evidence validation for manual review."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from firelens.evaluation.common import (
    file_sha256,
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
    strict_int as _strict_int,
)
from firelens.evaluation.ux import _named_frontend_reviewer


@dataclass(frozen=True)
class ManualReviewSetup:
    assignments: list[dict[str, Any]]
    assignment_by_role: dict[str, dict[str, Any]]
    protocol_profiles: list[dict[str, Any]]
    environment_by_profile: dict[str, dict[str, Any]]
    reviewer_ids: set[str]


@dataclass(frozen=True)
class ManualReviewEvidence:
    rows: list[dict[str, Any]]
    by_id: dict[str, dict[str, Any]]


def safe_frontend_review_evidence_path(
    bundle_path: Path, relative_value: Any, *, context: str
) -> tuple[Path, str]:
    relative = _require_nonempty_string(relative_value, context=f"{context} path")
    configured = Path(relative)
    if (
        configured.is_absolute()
        or ".." in configured.parts
        or configured.parts[:1] != ("evidence",)
        or configured.as_posix() != relative
    ):
        raise ValueError(f"{context} path must be a canonical relative path under evidence/")
    base = bundle_path.resolve().parent
    unresolved = base / configured
    current = base
    for part in configured.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"{context} path cannot use symbolic links")
    try:
        resolved = unresolved.resolve(strict=True)
    except FileNotFoundError as error:
        raise ValueError(f"{context} retained file is missing") from error
    if not resolved.is_relative_to(base) or not resolved.is_file():
        raise ValueError(f"{context} retained file must be a regular file inside the bundle")
    return resolved, relative


def validate_manual_review_setup(
    bundle: dict[str, Any],
    protocol: dict[str, Any],
    *,
    frozen_at: datetime,
    review_started_at: datetime,
    review_completed_at: datetime,
) -> ManualReviewSetup:
    """Validate the named-human roster and exact test environments."""

    expected_role_ids = [row["id"] for row in protocol["roles"]]
    raw_assignments = bundle.get("role_assignments")
    if not isinstance(raw_assignments, list) or len(raw_assignments) != len(expected_role_ids):
        raise ValueError("frontend manual review role assignment roster is incomplete")
    assignments: list[dict[str, Any]] = []
    assignment_by_role: dict[str, dict[str, Any]] = {}
    reviewer_ids: set[str] = set()
    reviewer_names: set[str] = set()
    for index, raw_assignment in enumerate(raw_assignments):
        context = f"frontend manual review role assignment {index}"
        if not isinstance(raw_assignment, dict):
            raise ValueError(f"{context} must be an object")
        assignment: dict[str, Any] = raw_assignment
        assignments.append(assignment)
        _require_exact_keys(
            assignment,
            {
                "role",
                "reviewer_id",
                "reviewer_name",
                "credentials",
                "assigned_at",
                "attested_at",
                "attestation",
            },
            context=context,
        )
        role = assignment.get("role")
        if role != expected_role_ids[index]:
            raise ValueError(
                "frontend manual review role assignments must use the exact roster"
            )
        reviewer_id = _require_nonempty_string(
            assignment.get("reviewer_id"), context=f"{context} reviewer ID"
        )
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:@-]{2,127}", reviewer_id):
            raise ValueError(f"{context} reviewer ID is not canonical")
        reviewer_name = _named_frontend_reviewer(
            assignment.get("reviewer_name"), context=f"{context} reviewer name"
        )
        if reviewer_id.casefold() in reviewer_ids or reviewer_name.casefold() in reviewer_names:
            raise ValueError("frontend manual review roles must be assigned to distinct people")
        reviewer_ids.add(reviewer_id.casefold())
        reviewer_names.add(reviewer_name.casefold())
        _require_nonempty_string(
            assignment.get("credentials"), context=f"{context} credentials"
        )
        _require_nonempty_string(
            assignment.get("attestation"), context=f"{context} attestation"
        )
        assigned_at = _require_timestamp(
            assignment.get("assigned_at"), context=f"{context} assigned_at"
        )
        attested_at = _require_timestamp(
            assignment.get("attested_at"), context=f"{context} attested_at"
        )
        if not (frozen_at <= assigned_at <= review_started_at) or attested_at < assigned_at:
            raise ValueError(f"{context} timestamp chain is invalid")
        assignment_by_role[str(role)] = {
            **assignment,
            "assigned_at_parsed": assigned_at,
            "attested_at_parsed": attested_at,
        }

    raw_profiles = protocol["test_profiles"]
    if not isinstance(raw_profiles, list) or not all(
        isinstance(profile, dict) for profile in raw_profiles
    ):
        raise ValueError("frontend manual review protocol test profiles are invalid")
    protocol_profiles: list[dict[str, Any]] = raw_profiles
    test_environments = bundle.get("test_environments")
    if not isinstance(test_environments, list) or len(test_environments) != len(
        protocol_profiles
    ):
        raise ValueError("frontend manual review test-environment roster is incomplete")
    environment_by_profile: dict[str, dict[str, Any]] = {}
    for index, (expected_profile, environment) in enumerate(
        zip(protocol_profiles, test_environments, strict=True)
    ):
        context = f"frontend manual review test environment {index}"
        if not isinstance(environment, dict):
            raise ValueError(f"{context} must be an object")
        _require_exact_keys(
            environment,
            {
                "profile_id",
                "reviewer_id",
                "os_name",
                "os_version",
                "browser_name",
                "browser_version",
                "assistive_technology",
                "assistive_technology_version",
                "input_methods",
                "viewport",
                "zoom_percentages",
                "reflow_widths_css_px",
                "reduced_motion",
                "verified_at",
            },
            context=context,
        )
        profile_id = environment.get("profile_id")
        if profile_id != expected_profile["id"]:
            raise ValueError(
                "frontend manual review test environments must use the exact roster"
            )
        expected_reviewer = assignment_by_role[expected_profile["required_role"]]
        if environment.get("reviewer_id") != expected_reviewer["reviewer_id"]:
            raise ValueError(f"{context} is not bound to its designated reviewer")
        for key in (
            "os_name",
            "browser_name",
            "assistive_technology",
            "input_methods",
            "viewport",
            "zoom_percentages",
            "reflow_widths_css_px",
            "reduced_motion",
        ):
            if environment.get(key) != expected_profile[key]:
                raise ValueError(f"{context} {key} differs from the frozen profile")
        _require_nonempty_string(environment.get("os_version"), context=f"{context} OS version")
        _require_nonempty_string(
            environment.get("browser_version"), context=f"{context} browser version"
        )
        assistive_version = environment.get("assistive_technology_version")
        if expected_profile["assistive_technology"] == "none":
            if assistive_version is not None:
                raise ValueError(f"{context} cannot name an assistive-technology version")
        else:
            _require_nonempty_string(
                assistive_version, context=f"{context} assistive-technology version"
            )
        verified_at = _require_timestamp(
            environment.get("verified_at"), context=f"{context} verified_at"
        )
        if not (review_started_at <= verified_at <= review_completed_at):
            raise ValueError(f"{context} verification falls outside the review window")
        environment_by_profile[str(profile_id)] = {
            **environment,
            "verified_at_parsed": verified_at,
        }
    return ManualReviewSetup(
        assignments=assignments,
        assignment_by_role=assignment_by_role,
        protocol_profiles=protocol_profiles,
        environment_by_profile=environment_by_profile,
        reviewer_ids=reviewer_ids,
    )


def validate_manual_review_evidence(
    bundle_path: Path,
    bundle: dict[str, Any],
    protocol: dict[str, Any],
    environment_by_profile: dict[str, dict[str, Any]],
    *,
    review_started_at: datetime,
    review_completed_at: datetime,
    identity_evidence_id: str,
    target_url: str,
    candidate_id: str,
    commit: str,
) -> ManualReviewEvidence:
    """Validate retained evidence files and the deployed candidate identity proof."""

    raw_evidence_rows = bundle.get("evidence")
    if not isinstance(raw_evidence_rows, list) or not raw_evidence_rows:
        raise ValueError("frontend manual review must retain evidence")
    evidence_rows: list[dict[str, Any]] = []
    evidence_by_id: dict[str, dict[str, Any]] = {}
    evidence_paths: set[str] = set()
    evidence_digests: set[str] = set()
    allowed_media_types = protocol["evidence_contract"]["allowed_media_types"]
    for index, raw_evidence in enumerate(raw_evidence_rows):
        context = f"frontend manual review evidence {index}"
        if not isinstance(raw_evidence, dict):
            raise ValueError(f"{context} must be an object")
        evidence: dict[str, Any] = raw_evidence
        evidence_rows.append(evidence)
        _require_exact_keys(
            evidence,
            {
                "evidence_id",
                "path",
                "sha256",
                "bytes",
                "media_type",
                "captured_at",
                "description",
                "profile_ids",
                "state_ids",
            },
            context=context,
        )
        evidence_id = _require_nonempty_string(
            evidence.get("evidence_id"), context=f"{context} ID"
        )
        if not re.fullmatch(r"EV-[0-9]{3,}", evidence_id) or evidence_id in evidence_by_id:
            raise ValueError("frontend manual review evidence IDs must be unique canonical IDs")
        path, relative_path = safe_frontend_review_evidence_path(
            bundle_path, evidence.get("path"), context=context
        )
        if relative_path in evidence_paths:
            raise ValueError("frontend manual review evidence paths must be unique")
        evidence_paths.add(relative_path)
        digest = _require_digest(evidence.get("sha256"), context=f"{context} digest")
        if digest != file_sha256(path):
            raise ValueError(f"{context} digest does not match the retained file")
        if digest in evidence_digests:
            raise ValueError(
                "frontend manual review evidence cannot duplicate retained content"
            )
        evidence_digests.add(digest)
        byte_count = _strict_int(evidence, "bytes", context, minimum=1)
        if byte_count != path.stat().st_size:
            raise ValueError(f"{context} byte count does not match the retained file")
        media_type = _require_nonempty_string(
            evidence.get("media_type"), context=f"{context} media type"
        )
        if (
            media_type not in allowed_media_types
            or path.suffix.lower() not in allowed_media_types[media_type]
        ):
            raise ValueError(f"{context} media type does not match its file extension")
        captured_at = _require_timestamp(
            evidence.get("captured_at"), context=f"{context} captured_at"
        )
        if not (review_started_at <= captured_at <= review_completed_at):
            raise ValueError(f"{context} falls outside the review window")
        profile_ids = evidence.get("profile_ids")
        state_ids = evidence.get("state_ids")
        if (
            not isinstance(profile_ids, list)
            or not profile_ids
            or len(profile_ids) != len(set(profile_ids))
            or any(profile_id not in environment_by_profile for profile_id in profile_ids)
        ):
            raise ValueError(f"{context} profile roster is invalid")
        if (
            not isinstance(state_ids, list)
            or not state_ids
            or len(state_ids) != len(set(state_ids))
            or any(state_id not in protocol["state_roster"] for state_id in state_ids)
        ):
            raise ValueError(f"{context} state roster is invalid")
        if any(
            environment_by_profile[str(profile_id)]["verified_at_parsed"] > captured_at
            for profile_id in profile_ids
        ):
            raise ValueError(f"{context} predates its recorded test environment")
        _require_nonempty_string(evidence.get("description"), context=f"{context} description")
        evidence_by_id[evidence_id] = {
            **evidence,
            "captured_at_parsed": captured_at,
            "resolved_path": path,
        }

    identity_evidence = evidence_by_id.get(identity_evidence_id)
    if identity_evidence is None:
        raise ValueError("frontend manual review candidate identity evidence is missing")
    if identity_evidence["media_type"] != "application/json":
        raise ValueError("frontend manual review candidate identity evidence must be JSON")
    try:
        identity_payload = json.loads(
            identity_evidence["resolved_path"].read_text(encoding="utf-8")
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(
            "frontend manual review candidate identity evidence is unreadable"
        ) from error
    if not isinstance(identity_payload, dict):
        raise ValueError("frontend manual review candidate identity evidence must be an object")
    _require_exact_keys(
        identity_payload,
        {"schema_version", "captured_at", "request", "response"},
        context="frontend manual review candidate identity evidence",
    )
    if (
        identity_payload.get("schema_version")
        != protocol["candidate_contract"]["identity_evidence_schema_version"]
    ):
        raise ValueError("frontend manual review candidate identity evidence schema is invalid")
    identity_captured_at = _require_timestamp(
        identity_payload.get("captured_at"),
        context="frontend manual review candidate identity evidence captured_at",
    )
    if identity_captured_at != identity_evidence["captured_at_parsed"]:
        raise ValueError("frontend manual review candidate identity timestamps differ")
    identity_request = identity_payload.get("request")
    identity_response = identity_payload.get("response")
    if not isinstance(identity_request, dict) or not isinstance(identity_response, dict):
        raise ValueError(
            "frontend manual review candidate identity request/response is invalid"
        )
    _require_exact_keys(
        identity_request,
        {"method", "url"},
        context="frontend manual review candidate identity request",
    )
    expected_identity_url = (
        target_url.rstrip("/") + protocol["candidate_contract"]["identity_endpoint_path"]
    )
    if identity_request != {"method": "GET", "url": expected_identity_url}:
        raise ValueError(
            "frontend manual review candidate identity request targets the wrong URL"
        )
    _require_exact_keys(
        identity_response,
        {"status_code", "content_type", "candidate_id", "build_commit"},
        context="frontend manual review candidate identity response",
    )
    if (
        identity_response.get("status_code") != 200
        or identity_response.get("content_type") != "application/json"
        or identity_response.get("candidate_id") != candidate_id
        or identity_response.get("build_commit") != commit
    ):
        raise ValueError(
            "frontend manual review candidate URL does not prove the exact identity"
        )
    return ManualReviewEvidence(rows=evidence_rows, by_id=evidence_by_id)
