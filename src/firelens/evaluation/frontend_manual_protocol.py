"""Frozen manual accessibility and product-safety review protocol validation."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

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


def _frontend_manual_review_protocol(path: Path) -> dict[str, Any]:
    protocol = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(protocol, dict):
        raise ValueError("frontend manual review protocol must be an object")
    _require_exact_keys(
        protocol,
        {
            "schema_version",
            "protocol_id",
            "bundle_schema_version",
            "status",
            "frozen_at",
            "description",
            "candidate_contract",
            "standards",
            "manual_thresholds",
            "state_roster",
            "test_profiles",
            "roles",
            "criteria",
            "atomic_check_requirements",
            "evidence_contract",
            "qualification_contract",
        },
        context="frontend manual review protocol",
    )
    if protocol.get("schema_version") != "firelens.frontend_manual_review_protocol.v1":
        raise ValueError("frontend manual review protocol uses an unsupported schema")
    if protocol.get("bundle_schema_version") != "firelens.frontend_manual_review_bundle.v1":
        raise ValueError("frontend manual review protocol names an unsupported bundle schema")
    if protocol.get("status") != "frozen":
        raise ValueError("frontend manual review protocol must be frozen")
    _require_nonempty_string(
        protocol.get("protocol_id"), context="frontend manual review protocol ID"
    )
    _require_nonempty_string(
        protocol.get("description"), context="frontend manual review protocol description"
    )
    _require_timestamp(
        protocol.get("frozen_at"), context="frontend manual review protocol frozen_at"
    )

    candidate_contract = protocol.get("candidate_contract")
    if not isinstance(candidate_contract, dict):
        raise ValueError("frontend manual review candidate contract must be an object")
    _require_exact_keys(
        candidate_contract,
        {
            "candidate_id_prefix",
            "commit_format",
            "allowed_target_url_schemes",
            "identity_endpoint_path",
            "identity_evidence_schema_version",
        },
        context="frontend manual review candidate contract",
    )
    if candidate_contract.get("candidate_id_prefix") != "firelens-v1-5-2:":
        raise ValueError("frontend manual review candidate ID prefix is not canonical")
    if candidate_contract.get("commit_format") != "full_lowercase_git_sha":
        raise ValueError("frontend manual review commit format is not canonical")
    if candidate_contract.get("allowed_target_url_schemes") != ["http", "https"]:
        raise ValueError("frontend manual review target URL schemes are not canonical")
    if candidate_contract.get("identity_endpoint_path") != "/api/v1/health/ready":
        raise ValueError("frontend manual review identity endpoint is not canonical")
    if (
        candidate_contract.get("identity_evidence_schema_version")
        != "firelens.frontend_candidate_identity_evidence.v1"
    ):
        raise ValueError("frontend manual review identity-evidence schema is not canonical")

    standards = protocol.get("standards")
    if not isinstance(standards, dict):
        raise ValueError("frontend manual review standards block must be an object")
    _require_exact_keys(
        standards,
        {"wcag_version", "conformance_level", "success_criteria"},
        context="frontend manual review standards",
    )
    if standards.get("wcag_version") != "2.2" or standards.get("conformance_level") != "AA":
        raise ValueError("frontend manual review must use WCAG 2.2 AA")
    success_criteria = standards.get("success_criteria")
    expected_success_criteria = [
        "1.3.1",
        "1.3.2",
        "1.4.1",
        "1.4.3",
        "1.4.4",
        "1.4.10",
        "1.4.11",
        "1.4.12",
        "2.1.1",
        "2.1.2",
        "2.4.3",
        "2.4.6",
        "2.4.7",
        "2.4.11",
        "2.5.1",
        "2.5.8",
        "3.3.1",
        "3.3.3",
        "4.1.2",
        "4.1.3",
    ]
    if (
        not isinstance(success_criteria, list)
        or [row.get("id") for row in success_criteria if isinstance(row, dict)]
        != expected_success_criteria
    ):
        raise ValueError(
            "frontend manual review WCAG success-criterion roster is not canonical"
        )
    for index, criterion in enumerate(success_criteria):
        if not isinstance(criterion, dict):
            raise ValueError(f"frontend manual review WCAG criterion {index} must be an object")
        _require_exact_keys(
            criterion, {"id", "name"}, context=f"frontend manual review WCAG criterion {index}"
        )
        _require_nonempty_string(
            criterion.get("name"), context=f"frontend manual review WCAG criterion {index} name"
        )

    expected_thresholds = {
        "normal_text_contrast_ratio_min": 4.5,
        "large_text_contrast_ratio_min": 3.0,
        "non_text_and_focus_contrast_ratio_min": 3.0,
        "browser_zoom_percent_required": 200,
        "reflow_width_css_px": 320,
        "horizontal_content_scroll_max_css_px": 0,
        "target_width_css_px_min": 24,
        "target_height_css_px_min": 24,
        "text_spacing": {
            "line_height_em_min": 1.5,
            "paragraph_spacing_em_min": 2.0,
            "letter_spacing_em_min": 0.12,
            "word_spacing_em_min": 0.16,
        },
    }
    if protocol.get("manual_thresholds") != expected_thresholds:
        raise ValueError("frontend manual review thresholds are not canonical")

    expected_states = [
        "idle",
        "grounded",
        "partial",
        "abstention",
        "provider_failure",
        "live",
        "mixed",
        "stale",
        "no_result",
        "partial_layer",
    ]
    if protocol.get("state_roster") != expected_states:
        raise ValueError("frontend manual review state roster is not canonical")

    profiles = protocol.get("test_profiles")
    expected_profile_ids = [
        "desktop_chromium_keyboard",
        "desktop_safari_voiceover",
        "mobile_safari_voiceover_touch",
        "product_safety_desktop_chromium",
        "product_safety_mobile_safari",
    ]
    if (
        not isinstance(profiles, list)
        or [row.get("id") for row in profiles if isinstance(row, dict)] != expected_profile_ids
    ):
        raise ValueError("frontend manual review test-profile roster is not canonical")
    profile_by_id: dict[str, dict[str, Any]] = {}
    for index, profile in enumerate(profiles):
        context = f"frontend manual review test profile {index}"
        if not isinstance(profile, dict):
            raise ValueError(f"{context} must be an object")
        _require_exact_keys(
            profile,
            {
                "id",
                "required_role",
                "os_name",
                "browser_name",
                "assistive_technology",
                "input_methods",
                "viewport",
                "zoom_percentages",
                "reflow_widths_css_px",
                "reduced_motion",
            },
            context=context,
        )
        if profile.get("required_role") not in {
            "accessibility_specialist",
            "wildfire_product_safety_reviewer",
        }:
            raise ValueError(f"{context} has an invalid reviewer role")
        for key in ("os_name", "browser_name", "assistive_technology"):
            _require_nonempty_string(profile.get(key), context=f"{context} {key}")
        input_methods = profile.get("input_methods")
        if (
            not isinstance(input_methods, list)
            or not input_methods
            or len(input_methods) != len(set(input_methods))
            or any(method not in {"keyboard", "pointer", "touch"} for method in input_methods)
        ):
            raise ValueError(f"{context} input method roster is invalid")
        viewport = profile.get("viewport")
        if not isinstance(viewport, dict):
            raise ValueError(f"{context} viewport must be an object")
        _require_exact_keys(viewport, {"width", "height"}, context=f"{context} viewport")
        _strict_int(viewport, "width", f"{context} viewport", minimum=320)
        _strict_int(viewport, "height", f"{context} viewport", minimum=320)
        zoom_percentages = profile.get("zoom_percentages")
        reflow_widths = profile.get("reflow_widths_css_px")
        if (
            not isinstance(zoom_percentages, list)
            or not zoom_percentages
            or any(type(value) is not int or value < 100 for value in zoom_percentages)
            or not isinstance(reflow_widths, list)
            or any(type(value) is not int or value < 320 for value in reflow_widths)
        ):
            raise ValueError(f"{context} zoom/reflow roster is invalid")
        if profile.get("reduced_motion") != "reduce":
            raise ValueError(f"{context} must test reduced motion")
        profile_by_id[str(profile["id"])] = profile

    roles = protocol.get("roles")
    expected_roles = [
        "accessibility_specialist",
        "wildfire_product_safety_reviewer",
        "release_adjudicator",
    ]
    if (
        not isinstance(roles, list)
        or [row.get("id") for row in roles if isinstance(row, dict)] != expected_roles
    ):
        raise ValueError("frontend manual review protocol role roster is not canonical")
    for index, role in enumerate(roles):
        if not isinstance(role, dict):
            raise ValueError(f"frontend manual review protocol role {index} must be an object")
        _require_exact_keys(
            role,
            {"id", "responsibility"},
            context=f"frontend manual review protocol role {index}",
        )
        _require_nonempty_string(
            role.get("responsibility"),
            context=f"frontend manual review protocol role {role['id']} responsibility",
        )

    criteria = protocol.get("criteria")
    if not isinstance(criteria, list) or not criteria:
        raise ValueError("frontend manual review protocol must define criteria")
    criterion_ids: set[str] = set()
    atomic_ids: set[str] = set()
    for criterion_index, criterion in enumerate(criteria):
        context = f"frontend manual review protocol criterion {criterion_index}"
        if not isinstance(criterion, dict):
            raise ValueError(f"{context} must be an object")
        _require_exact_keys(
            criterion,
            {"id", "track", "required_role", "atomic_checks"},
            context=context,
        )
        criterion_id = _require_nonempty_string(criterion.get("id"), context=f"{context} ID")
        if not re.fullmatch(r"(?:A11Y|SAFETY)_[A-Z0-9_]+", criterion_id):
            raise ValueError(f"{context} ID is not canonical")
        if criterion_id in criterion_ids:
            raise ValueError("frontend manual review protocol criterion IDs must be unique")
        criterion_ids.add(criterion_id)
        track = criterion.get("track")
        role = criterion.get("required_role")
        if (track, role) not in {
            ("accessibility", "accessibility_specialist"),
            ("product_safety", "wildfire_product_safety_reviewer"),
        }:
            raise ValueError(f"{context} has an invalid track/role assignment")
        checks = criterion.get("atomic_checks")
        if not isinstance(checks, list) or not checks:
            raise ValueError(f"{context} must define atomic checks")
        for check_index, check in enumerate(checks):
            check_context = f"{context} atomic check {check_index}"
            if not isinstance(check, dict):
                raise ValueError(f"{check_context} must be an object")
            _require_exact_keys(check, {"id", "instruction"}, context=check_context)
            check_id = _require_nonempty_string(check.get("id"), context=f"{check_context} ID")
            expected_prefix = "A11Y-" if track == "accessibility" else "SAFETY-"
            if not check_id.startswith(expected_prefix) or not re.fullmatch(
                r"[A-Z0-9]+-[A-Z0-9]+-[0-9]{2}", check_id
            ):
                raise ValueError(f"{check_context} ID is not canonical")
            if check_id in atomic_ids:
                raise ValueError("frontend manual review atomic-check IDs must be unique")
            atomic_ids.add(check_id)
            _require_nonempty_string(
                check.get("instruction"), context=f"{check_context} instruction"
            )

    atomic_requirements = protocol.get("atomic_check_requirements")
    if not isinstance(atomic_requirements, dict) or set(atomic_requirements) != atomic_ids:
        raise ValueError("frontend manual review atomic-check requirements are incomplete")
    known_success_criteria = set(expected_success_criteria)
    for check_id, requirement in atomic_requirements.items():
        context = f"frontend manual review atomic requirement {check_id}"
        if not isinstance(requirement, dict):
            raise ValueError(f"{context} must be an object")
        _require_exact_keys(
            requirement,
            {"wcag_2_2_success_criteria", "required_profile_ids"},
            context=context,
        )
        wcag_ids = requirement.get("wcag_2_2_success_criteria")
        required_profiles = requirement.get("required_profile_ids")
        if (
            not isinstance(wcag_ids, list)
            or len(wcag_ids) != len(set(wcag_ids))
            or any(wcag_id not in known_success_criteria for wcag_id in wcag_ids)
        ):
            raise ValueError(f"{context} WCAG mapping is invalid")
        if (
            not isinstance(required_profiles, list)
            or not required_profiles
            or len(required_profiles) != len(set(required_profiles))
            or any(profile_id not in profile_by_id for profile_id in required_profiles)
        ):
            raise ValueError(f"{context} required profile roster is invalid")
        expected_role = (
            "accessibility_specialist"
            if str(check_id).startswith("A11Y-")
            else "wildfire_product_safety_reviewer"
        )
        if any(
            profile_by_id[str(profile_id)]["required_role"] != expected_role
            for profile_id in required_profiles
        ):
            raise ValueError(f"{context} references a profile owned by the wrong role")

    evidence_contract = protocol.get("evidence_contract")
    if not isinstance(evidence_contract, dict):
        raise ValueError("frontend manual review evidence contract must be an object")
    _require_exact_keys(
        evidence_contract,
        {
            "path_prefix",
            "require_sha256",
            "require_byte_count",
            "require_every_item_referenced",
            "allowed_media_types",
        },
        context="frontend manual review evidence contract",
    )
    if evidence_contract.get("path_prefix") != "evidence":
        raise ValueError("frontend manual review evidence path prefix is not canonical")
    for key in ("require_sha256", "require_byte_count", "require_every_item_referenced"):
        if evidence_contract.get(key) is not True:
            raise ValueError(f"frontend manual review evidence contract must enable {key}")
    media_types = evidence_contract.get("allowed_media_types")
    if not isinstance(media_types, dict) or not media_types:
        raise ValueError("frontend manual review media-type roster is missing")
    for media_type, extensions in media_types.items():
        if (
            not isinstance(media_type, str)
            or not media_type.strip()
            or not isinstance(extensions, list)
            or not extensions
            or any(
                not isinstance(extension, str) or not re.fullmatch(r"\.[a-z0-9]+", extension)
                for extension in extensions
            )
        ):
            raise ValueError("frontend manual review media-type roster is invalid")

    qualification = protocol.get("qualification_contract")
    expected_qualification = {
        "required_atomic_status": "pass",
        "open_findings_must_equal": 0,
        "require_distinct_people_for_all_roles": True,
        "require_exact_criterion_roster": True,
        "require_exact_atomic_check_roster": True,
    }
    if qualification != expected_qualification:
        raise ValueError("frontend manual review qualification contract is not canonical")
    return protocol
