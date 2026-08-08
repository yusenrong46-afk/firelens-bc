#!/usr/bin/env python3
"""Freeze or verify the public identities for the private semantic holdout."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import stat
import sys
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import scripts.upgrade_benchmark as benchmark_harness
except ModuleNotFoundError as error:  # Direct execution puts scripts/ on sys.path.
    if error.name != "scripts":
        raise
    import upgrade_benchmark as benchmark_harness  # type: ignore[no-redef]

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROTOCOL = ROOT / "data/evaluation/semantic_holdout_freeze_protocol.v1.json"
MAX_INPUT_BYTES = 16 * 1024 * 1024
LOWER_ID = re.compile(r"^[a-z][a-z0-9._-]{1,127}$")
CASE_ID = re.compile(r"^[A-Z][A-Z0-9._-]{2,63}$")
DIGEST = re.compile(r"^[0-9a-f]{64}$")


class FreezeRefusal(ValueError):
    """A refusal whose stable code is safe to show without private values."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _refuse(code: str) -> None:
    raise FreezeRefusal(code)


def _exact_keys(value: Any, expected: set[str], code: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        _refuse(code)
    return value


def _nonempty_string(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        _refuse(code)
    if unicodedata.normalize("NFC", value) != value:
        _refuse(code)
    return value


def _content_string(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _refuse(code)
    if unicodedata.normalize("NFC", value) != value or "\x00" in value:
        _refuse(code)
    return value


def _lower_identifier(value: Any, code: str) -> str:
    parsed = _nonempty_string(value, code)
    if LOWER_ID.fullmatch(parsed) is None:
        _refuse(code)
    return parsed


def _case_identifier(value: Any, code: str) -> str:
    parsed = _nonempty_string(value, code)
    if CASE_ID.fullmatch(parsed) is None:
        _refuse(code)
    return parsed


def _digest(value: Any, code: str) -> str:
    if not isinstance(value, str) or DIGEST.fullmatch(value) is None:
        _refuse(code)
    return value


def _timestamp(value: Any, code: str) -> datetime:
    parsed_value = _nonempty_string(value, code)
    try:
        parsed = datetime.fromisoformat(parsed_value.replace("Z", "+00:00"))
    except ValueError:
        _refuse(code)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        _refuse(code)
    return parsed


def _sorted_unique_strings(
    value: Any,
    *,
    code: str,
    minimum: int,
    parser: Any = _nonempty_string,
) -> list[str]:
    if not isinstance(value, list) or len(value) < minimum:
        _refuse(code)
    parsed = [parser(item, code) for item in value]
    if parsed != sorted(parsed) or len(parsed) != len(set(parsed)):
        _refuse(code)
    return parsed


def _validate_json_value(value: Any) -> None:
    if value is None or type(value) is bool:
        return
    if isinstance(value, str):
        if unicodedata.normalize("NFC", value) != value or "\x00" in value:
            _refuse("noncanonical_json_value")
        return
    if isinstance(value, int):
        if abs(value) > 9_007_199_254_740_991:
            _refuse("noncanonical_json_number")
        return
    if isinstance(value, float):
        if not math.isfinite(value) or (value == 0.0 and math.copysign(1.0, value) < 0):
            _refuse("noncanonical_json_number")
        return
    if isinstance(value, list):
        for item in value:
            _validate_json_value(item)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            _nonempty_string(key, "noncanonical_json_key")
            _validate_json_value(item)
        return
    _refuse("unsupported_json_value")


def _duplicate_rejecting_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _refuse("duplicate_json_key")
        result[key] = value
    return result


def _reject_constant(_: str) -> None:
    _refuse("noncanonical_json_number")


def _lexical_path(path: Path) -> Path:
    if ".." in path.parts:
        _refuse("parent_path_reference")
    return Path(os.path.abspath(os.fspath(path.expanduser())))


def _assert_no_symlink_components(path: Path, *, leaf_may_be_missing: bool) -> None:
    absolute = _lexical_path(path)
    current = Path(absolute.anchor)
    for index, part in enumerate(absolute.parts[1:], start=1):
        current /= part
        is_leaf = index == len(absolute.parts) - 1
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            if leaf_may_be_missing and is_leaf:
                return
            _refuse("path_component_missing")
        if stat.S_ISLNK(mode):
            _refuse("symlink_path_refused")


def _read_json(path: Path, *, private: bool = False) -> tuple[dict[str, Any], bytes]:
    absolute = _lexical_path(path)
    _assert_no_symlink_components(absolute, leaf_may_be_missing=False)
    if private and absolute.resolve(strict=True).is_relative_to(ROOT):
        _refuse("private_payload_inside_repository")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(absolute, flags)
    except OSError:
        _refuse("input_open_failed")
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            _refuse("input_not_regular_file")
        if metadata.st_size > MAX_INPUT_BYTES:
            _refuse("input_too_large")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            raw = stream.read(MAX_INPUT_BYTES + 1)
    finally:
        os.close(descriptor)
    if len(raw) > MAX_INPUT_BYTES:
        _refuse("input_too_large")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        _refuse("input_not_utf8")
    try:
        payload = json.loads(
            text,
            object_pairs_hook=_duplicate_rejecting_object,
            parse_constant=_reject_constant,
        )
    except FreezeRefusal:
        raise
    except (TypeError, ValueError, json.JSONDecodeError):
        _refuse("invalid_json")
    if not isinstance(payload, dict):
        _refuse("json_root_not_object")
    _validate_json_value(payload)
    return payload, raw


def _canonical_digest(payload: Any) -> str:
    return benchmark_harness._sha256_json(payload)


def _render_public_json(payload: dict[str, Any]) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        + "\n"
    ).encode("utf-8")


def _write_new_public_json(path: Path, payload: dict[str, Any]) -> None:
    absolute = _lexical_path(path)
    _assert_no_symlink_components(absolute, leaf_may_be_missing=True)
    if absolute.exists() or absolute.is_symlink():
        _refuse("output_exists")
    parent = absolute.parent
    if not parent.is_dir():
        _refuse("output_parent_not_directory")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(absolute, flags, 0o644)
    except FileExistsError:
        _refuse("output_exists")
    except OSError:
        _refuse("output_open_failed")
    created = True
    try:
        rendered = _render_public_json(payload)
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write(rendered)
            stream.flush()
            os.fsync(stream.fileno())
        created = False
    finally:
        os.close(descriptor)
        if created:
            try:
                absolute.unlink()
            except FileNotFoundError:
                pass


def load_protocol(path: Path = DEFAULT_PROTOCOL) -> dict[str, Any]:
    protocol, _ = _read_json(path)
    _exact_keys(
        protocol,
        {
            "canonical_json",
            "frozen_at",
            "minimums",
            "privacy",
            "protocol_version",
            "status",
            "supported_contracts",
        },
        "protocol_schema_invalid",
    )
    if protocol.get("protocol_version") != "firelens_semantic_holdout_freeze_protocol.v1":
        _refuse("protocol_version_invalid")
    if protocol.get("status") != "frozen":
        _refuse("protocol_not_frozen")
    _timestamp(protocol.get("frozen_at"), "protocol_timestamp_invalid")
    canonical_json = _exact_keys(
        protocol.get("canonical_json"),
        {
            "allow_non_finite_numbers",
            "duplicate_object_keys",
            "hash_encoding",
            "identifier_lists",
            "unicode_normalization",
        },
        "protocol_canonical_json_invalid",
    )
    if canonical_json != {
        "allow_non_finite_numbers": False,
        "duplicate_object_keys": "reject",
        "hash_encoding": "utf8_compact_sorted_keys_no_ascii_escaping",
        "identifier_lists": "sorted_unique",
        "unicode_normalization": "NFC",
    }:
        _refuse("protocol_canonical_json_invalid")
    minimums = _exact_keys(
        protocol.get("minimums"),
        {
            "case_count",
            "question_family_count",
            "risk_labels_per_case",
            "source_commitments_per_case",
        },
        "protocol_minimums_invalid",
    )
    if minimums != {
        "case_count": 25,
        "question_family_count": 5,
        "risk_labels_per_case": 1,
        "source_commitments_per_case": 1,
    }:
        _refuse("protocol_minimums_invalid")
    privacy = _exact_keys(
        protocol.get("privacy"),
        {
            "private_payload_must_be_outside_repository",
            "private_values_in_console_output",
            "write_normalized_private_payload",
        },
        "protocol_privacy_invalid",
    )
    if privacy != {
        "private_payload_must_be_outside_repository": True,
        "private_values_in_console_output": False,
        "write_normalized_private_payload": False,
    }:
        _refuse("protocol_privacy_invalid")
    contracts = _exact_keys(
        protocol.get("supported_contracts"),
        {
            "development_registry",
            "development_review_request",
            "disjointness_audit",
            "private_holdout_payload",
            "private_review_input",
            "public_holdout_manifest",
        },
        "protocol_contracts_invalid",
    )
    if contracts != {
        "development_registry": "firelens_semantic_development_exposure_registry.v1",
        "development_review_request": (
            "firelens_semantic_development_exposure_freeze_request.v1"
        ),
        "disjointness_audit": "firelens_semantic_disjointness_audit.v1",
        "private_holdout_payload": "firelens_semantic_holdout_private_payload.v1",
        "private_review_input": "firelens_semantic_holdout_review_input.v1",
        "public_holdout_manifest": "firelens_semantic_holdout_manifest.v3",
    }:
        _refuse("protocol_contracts_invalid")
    return protocol


def _require_pre_candidate_guard(
    *, attest_no_candidate: bool, candidate_created_at: str | None
) -> None:
    if candidate_created_at is not None:
        _timestamp(candidate_created_at, "candidate_timestamp_invalid")
        _refuse("candidate_already_started")
    if attest_no_candidate is not True:
        _refuse("pre_candidate_attestation_required")


def construct_development_registry(
    request: dict[str, Any], *, protocol: dict[str, Any]
) -> dict[str, Any]:
    contracts = protocol["supported_contracts"]
    _exact_keys(
        request,
        {"request_version", "registry_id", "frozen_at", "review", "datasets"},
        "development_request_schema_invalid",
    )
    if request.get("request_version") != contracts["development_review_request"]:
        _refuse("development_request_version_invalid")
    registry_id = _lower_identifier(request.get("registry_id"), "registry_id_invalid")
    frozen_at = _timestamp(request.get("frozen_at"), "registry_frozen_at_invalid")
    review = _exact_keys(
        request.get("review"),
        {
            "attestation",
            "question_family_roster_canonicalized",
            "reviewed_at",
            "reviewer_id",
            "source_roster_canonicalized",
        },
        "development_review_schema_invalid",
    )
    _lower_identifier(review.get("reviewer_id"), "development_reviewer_id_invalid")
    reviewed_at = _timestamp(review.get("reviewed_at"), "development_reviewed_at_invalid")
    _nonempty_string(review.get("attestation"), "development_attestation_invalid")
    if review.get("source_roster_canonicalized") is not True:
        _refuse("development_source_review_missing")
    if review.get("question_family_roster_canonicalized") is not True:
        _refuse("development_family_review_missing")
    if reviewed_at > frozen_at:
        _refuse("development_review_after_freeze")

    datasets_value = request.get("datasets")
    if not isinstance(datasets_value, list) or not datasets_value:
        _refuse("development_datasets_missing")
    datasets: list[dict[str, Any]] = []
    dataset_ids: list[str] = []
    aggregate_sources: set[str] = set()
    aggregate_families: set[str] = set()
    for row_value in datasets_value:
        row = _exact_keys(
            row_value,
            {"dataset_id", "dataset_sha256", "source_id_sha256s", "question_family_ids"},
            "development_dataset_schema_invalid",
        )
        dataset_id = _lower_identifier(row.get("dataset_id"), "development_dataset_id_invalid")
        dataset_sha256 = _digest(
            row.get("dataset_sha256"), "development_dataset_digest_invalid"
        )
        sources = _sorted_unique_strings(
            row.get("source_id_sha256s"),
            code="development_source_roster_noncanonical",
            minimum=0,
            parser=_digest,
        )
        families = _sorted_unique_strings(
            row.get("question_family_ids"),
            code="development_family_roster_noncanonical",
            minimum=1,
            parser=_lower_identifier,
        )
        dataset_ids.append(dataset_id)
        aggregate_sources.update(sources)
        aggregate_families.update(families)
        datasets.append(
            {
                "dataset_id": dataset_id,
                "dataset_sha256": dataset_sha256,
                "source_id_sha256s": sources,
                "question_family_ids": families,
            }
        )
    if dataset_ids != sorted(dataset_ids) or len(dataset_ids) != len(set(dataset_ids)):
        _refuse("development_dataset_roster_noncanonical")
    minimums = protocol["minimums"]
    sources = sorted(aggregate_sources)
    families = sorted(aggregate_families)
    if not sources:
        _refuse("development_source_roster_missing")
    if len(families) < minimums["question_family_count"]:
        _refuse("development_family_count_too_small")
    registry = {
        "registry_version": contracts["development_registry"],
        "registry_id": registry_id,
        "frozen_at": request["frozen_at"],
        "dataset_roster_sha256": _canonical_digest(datasets),
        "datasets": datasets,
        "source_id_sha256s": sources,
        "source_roster_sha256": _canonical_digest(sources),
        "question_family_ids": families,
        "question_family_roster_sha256": _canonical_digest(families),
    }
    try:
        benchmark_harness._semantic_development_registry_payload(registry)
    except ValueError:
        _refuse("development_registry_contract_rejected")
    return registry


def _load_development_registry(path: Path) -> tuple[dict[str, Any], str]:
    registry, raw = _read_json(path)
    try:
        benchmark_harness._semantic_development_registry_payload(registry)
    except ValueError:
        _refuse("development_registry_contract_rejected")
    return registry, hashlib.sha256(raw).hexdigest()


def _private_case_roster(
    private_payload: dict[str, Any], *, protocol: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[str], list[str], dict[str, int]]:
    contracts = protocol["supported_contracts"]
    _exact_keys(
        private_payload,
        {"payload_version", "dataset_id", "cases"},
        "private_payload_schema_invalid",
    )
    if private_payload.get("payload_version") != contracts["private_holdout_payload"]:
        _refuse("private_payload_version_invalid")
    _lower_identifier(private_payload.get("dataset_id"), "private_dataset_id_invalid")
    cases_value = private_payload.get("cases")
    minimums = protocol["minimums"]
    if not isinstance(cases_value, list) or len(cases_value) < minimums["case_count"]:
        _refuse("holdout_case_count_too_small")
    roster: list[dict[str, Any]] = []
    case_ids: list[str] = []
    aggregate_sources: set[str] = set()
    family_counts: dict[str, int] = {}
    for row_value in cases_value:
        row = _exact_keys(
            row_value,
            {
                "case_id",
                "input_payload",
                "question_family_id",
                "risk_labels",
                "source_id_sha256s",
            },
            "private_case_schema_invalid",
        )
        case_id = _case_identifier(row.get("case_id"), "private_case_id_invalid")
        input_payload = row.get("input_payload")
        _validate_review_input(input_payload, protocol=protocol)
        sources = _sorted_unique_strings(
            row.get("source_id_sha256s"),
            code="private_source_roster_noncanonical",
            minimum=minimums["source_commitments_per_case"],
            parser=_digest,
        )
        family = _lower_identifier(
            row.get("question_family_id"), "private_question_family_invalid"
        )
        _sorted_unique_strings(
            row.get("risk_labels"),
            code="private_risk_labels_noncanonical",
            minimum=minimums["risk_labels_per_case"],
            parser=_lower_identifier,
        )
        context_sources = sorted(
            {row["source_id_sha256"] for row in input_payload["source_context"]}
        )
        if sources != context_sources:
            _refuse("private_source_context_roster_mismatch")
        case_ids.append(case_id)
        aggregate_sources.update(sources)
        family_counts[family] = family_counts.get(family, 0) + 1
        roster.append(
            {
                "case_id": case_id,
                "input_sha256": _canonical_digest(input_payload),
                "source_id_sha256s": sources,
                "question_family_id": family,
            }
        )
    if case_ids != sorted(case_ids) or len(case_ids) != len(set(case_ids)):
        _refuse("private_case_roster_noncanonical")
    families = sorted(family_counts)
    if len(families) < minimums["question_family_count"]:
        _refuse("holdout_family_count_too_small")
    return roster, sorted(aggregate_sources), families, dict(sorted(family_counts.items()))


def _validate_review_input(value: Any, *, protocol: dict[str, Any]) -> dict[str, Any]:
    review_input = _exact_keys(
        value,
        {"history", "input_version", "question", "rubric", "source_context"},
        "private_review_input_schema_invalid",
    )
    if (
        review_input.get("input_version")
        != protocol["supported_contracts"]["private_review_input"]
    ):
        _refuse("private_review_input_version_invalid")
    _content_string(review_input.get("question"), "private_question_invalid")

    history = review_input.get("history")
    if not isinstance(history, list):
        _refuse("private_history_invalid")
    for message_value in history:
        message = _exact_keys(
            message_value,
            {"content", "role"},
            "private_history_message_schema_invalid",
        )
        if message.get("role") not in {"assistant", "user"}:
            _refuse("private_history_role_invalid")
        _content_string(message.get("content"), "private_history_content_invalid")

    rubric = _exact_keys(
        review_input.get("rubric"),
        {
            "expected_route",
            "expected_status",
            "forbidden_claims",
            "required_concepts",
            "required_limitations",
        },
        "private_rubric_schema_invalid",
    )
    _lower_identifier(rubric.get("expected_route"), "private_expected_route_invalid")
    _lower_identifier(rubric.get("expected_status"), "private_expected_status_invalid")
    rubric_lists: list[list[str]] = []
    for key in ("forbidden_claims", "required_concepts", "required_limitations"):
        values = _sorted_unique_strings(
            rubric.get(key),
            code="private_rubric_list_noncanonical",
            minimum=0,
            parser=_content_string,
        )
        rubric_lists.append(values)
    if not any(rubric_lists):
        _refuse("private_rubric_empty")

    source_context = review_input.get("source_context")
    if not isinstance(source_context, list) or not source_context:
        _refuse("private_source_context_missing")
    context_ids: list[str] = []
    for context_value in source_context:
        context = _exact_keys(
            context_value,
            {"context_id", "locator", "source_id_sha256", "text"},
            "private_source_context_schema_invalid",
        )
        context_ids.append(
            _lower_identifier(context.get("context_id"), "private_context_id_invalid")
        )
        _content_string(context.get("locator"), "private_context_locator_invalid")
        _digest(context.get("source_id_sha256"), "private_context_source_digest_invalid")
        _content_string(context.get("text"), "private_context_text_invalid")
    if context_ids != sorted(context_ids) or len(context_ids) != len(set(context_ids)):
        _refuse("private_source_context_noncanonical")
    return review_input


def construct_holdout_manifest(
    private_payload: dict[str, Any],
    *,
    development_registry: dict[str, Any],
    development_registry_sha256: str,
    audited_at: str,
    frozen_at: str,
    protocol: dict[str, Any],
) -> dict[str, Any]:
    audited_timestamp = _timestamp(audited_at, "holdout_audited_at_invalid")
    frozen_timestamp = _timestamp(frozen_at, "holdout_frozen_at_invalid")
    registry_frozen_timestamp = _timestamp(
        development_registry.get("frozen_at"), "registry_frozen_at_invalid"
    )
    if audited_timestamp < registry_frozen_timestamp or audited_timestamp > frozen_timestamp:
        _refuse("holdout_timestamp_order_invalid")
    registry_digest = _digest(
        development_registry_sha256, "development_registry_digest_invalid"
    )
    roster, source_roster, family_roster, family_distribution = _private_case_roster(
        private_payload, protocol=protocol
    )
    source_overlap = sorted(set(source_roster) & set(development_registry["source_id_sha256s"]))
    family_overlap = sorted(
        set(family_roster) & set(development_registry["question_family_ids"])
    )
    if source_overlap:
        _refuse("development_source_overlap")
    if family_overlap:
        _refuse("development_question_family_overlap")
    source_roster_sha256 = _canonical_digest(source_roster)
    family_roster_sha256 = _canonical_digest(family_roster)
    manifest = {
        "manifest_version": protocol["supported_contracts"]["public_holdout_manifest"],
        "dataset_sha256": _canonical_digest(private_payload),
        "case_roster_sha256": _canonical_digest(roster),
        "case_count": len(roster),
        "case_roster": roster,
        "source_id_sha256s": source_roster,
        "source_roster_sha256": source_roster_sha256,
        "question_family_ids": family_roster,
        "question_family_roster_sha256": family_roster_sha256,
        "question_family_distribution": family_distribution,
        "development_registry_id": development_registry["registry_id"],
        "development_registry_sha256": registry_digest,
        "disjointness_audit": {
            "audit_version": protocol["supported_contracts"]["disjointness_audit"],
            "audited_at": audited_at,
            "development_registry_sha256": registry_digest,
            "development_source_roster_sha256": development_registry["source_roster_sha256"],
            "development_question_family_roster_sha256": development_registry[
                "question_family_roster_sha256"
            ],
            "holdout_source_roster_sha256": source_roster_sha256,
            "holdout_question_family_roster_sha256": family_roster_sha256,
            "source_overlap_id_sha256s": [],
            "question_family_overlap_ids": [],
            "source_disjoint_from_development": True,
            "question_family_disjoint_from_development": True,
        },
        "frozen_before_candidate": True,
        "double_review_required": True,
        "frozen_at": frozen_at,
    }
    try:
        benchmark_harness._semantic_holdout_manifest_payload(
            manifest,
            development_registry=development_registry,
            development_registry_sha256=registry_digest,
        )
    except ValueError:
        _refuse("holdout_manifest_contract_rejected")
    return manifest


def freeze_development_registry(
    request_path: Path,
    output_path: Path,
    *,
    protocol_path: Path = DEFAULT_PROTOCOL,
    attest_no_candidate: bool,
    candidate_created_at: str | None,
) -> dict[str, Any]:
    protocol = load_protocol(protocol_path)
    _require_pre_candidate_guard(
        attest_no_candidate=attest_no_candidate,
        candidate_created_at=candidate_created_at,
    )
    request, _ = _read_json(request_path)
    registry = construct_development_registry(request, protocol=protocol)
    _write_new_public_json(output_path, registry)
    return registry


def freeze_holdout_manifest(
    private_payload_path: Path,
    development_registry_path: Path,
    output_path: Path,
    *,
    audited_at: str,
    frozen_at: str,
    protocol_path: Path = DEFAULT_PROTOCOL,
    attest_no_candidate: bool,
    candidate_created_at: str | None,
) -> dict[str, Any]:
    protocol = load_protocol(protocol_path)
    _require_pre_candidate_guard(
        attest_no_candidate=attest_no_candidate,
        candidate_created_at=candidate_created_at,
    )
    private_payload, _ = _read_json(private_payload_path, private=True)
    registry, registry_sha256 = _load_development_registry(development_registry_path)
    manifest = construct_holdout_manifest(
        private_payload,
        development_registry=registry,
        development_registry_sha256=registry_sha256,
        audited_at=audited_at,
        frozen_at=frozen_at,
        protocol=protocol,
    )
    _write_new_public_json(output_path, manifest)
    return manifest


def validate_development_registry(
    request_path: Path,
    registry_path: Path,
    *,
    protocol_path: Path = DEFAULT_PROTOCOL,
) -> dict[str, Any]:
    protocol = load_protocol(protocol_path)
    request, _ = _read_json(request_path)
    expected = construct_development_registry(request, protocol=protocol)
    observed, _ = _load_development_registry(registry_path)
    if observed != expected:
        _refuse("development_registry_recomputation_mismatch")
    return observed


def validate_holdout_manifest(
    private_payload_path: Path,
    development_registry_path: Path,
    manifest_path: Path,
    *,
    protocol_path: Path = DEFAULT_PROTOCOL,
) -> dict[str, Any]:
    protocol = load_protocol(protocol_path)
    private_payload, _ = _read_json(private_payload_path, private=True)
    registry, registry_sha256 = _load_development_registry(development_registry_path)
    manifest, _ = _read_json(manifest_path)
    try:
        benchmark_harness._semantic_holdout_manifest_payload(
            manifest,
            development_registry=registry,
            development_registry_sha256=registry_sha256,
        )
    except ValueError:
        _refuse("holdout_manifest_contract_rejected")
    audit = manifest.get("disjointness_audit")
    if not isinstance(audit, dict):
        _refuse("holdout_manifest_contract_rejected")
    expected = construct_holdout_manifest(
        private_payload,
        development_registry=registry,
        development_registry_sha256=registry_sha256,
        audited_at=audit.get("audited_at"),
        frozen_at=manifest.get("frozen_at"),
        protocol=protocol,
    )
    if manifest != expected:
        _refuse("holdout_manifest_recomputation_mismatch")
    return manifest


def _summary(kind: str, payload: dict[str, Any], output: Path | None = None) -> dict[str, Any]:
    summary: dict[str, Any] = {"artifact": kind, "status": "verified"}
    if output is not None:
        summary["output"] = os.fspath(_lexical_path(output))
        summary["status"] = "created"
    if kind == "development_registry":
        summary.update(
            {
                "dataset_count": len(payload["datasets"]),
                "question_family_count": len(payload["question_family_ids"]),
                "source_commitment_count": len(payload["source_id_sha256s"]),
            }
        )
    else:
        summary.update(
            {
                "case_count": payload["case_count"],
                "question_family_count": len(payload["question_family_ids"]),
                "source_commitment_count": len(payload["source_id_sha256s"]),
            }
        )
    return summary


def _add_candidate_guard(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--attest-no-candidate",
        action="store_true",
        help="Attest that final-candidate generation has not started.",
    )
    group.add_argument(
        "--candidate-created-at",
        help="Record known candidate start time; freeze will refuse.",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    subparsers = parser.add_subparsers(dest="command", required=True)

    freeze_registry = subparsers.add_parser("freeze-registry")
    freeze_registry.add_argument("--reviewed-roster", type=Path, required=True)
    freeze_registry.add_argument("--output", type=Path, required=True)
    _add_candidate_guard(freeze_registry)

    validate_registry = subparsers.add_parser("validate-registry")
    validate_registry.add_argument("--reviewed-roster", type=Path, required=True)
    validate_registry.add_argument("--registry", type=Path, required=True)

    freeze_manifest = subparsers.add_parser("freeze-manifest")
    freeze_manifest.add_argument("--private-payload", type=Path, required=True)
    freeze_manifest.add_argument("--development-registry", type=Path, required=True)
    freeze_manifest.add_argument("--output", type=Path, required=True)
    freeze_manifest.add_argument("--audited-at", required=True)
    freeze_manifest.add_argument("--frozen-at", required=True)
    _add_candidate_guard(freeze_manifest)

    validate_manifest = subparsers.add_parser("validate-manifest")
    validate_manifest.add_argument("--private-payload", type=Path, required=True)
    validate_manifest.add_argument("--development-registry", type=Path, required=True)
    validate_manifest.add_argument("--manifest", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "freeze-registry":
            payload = freeze_development_registry(
                args.reviewed_roster,
                args.output,
                protocol_path=args.protocol,
                attest_no_candidate=args.attest_no_candidate,
                candidate_created_at=args.candidate_created_at,
            )
            summary = _summary("development_registry", payload, args.output)
        elif args.command == "validate-registry":
            payload = validate_development_registry(
                args.reviewed_roster,
                args.registry,
                protocol_path=args.protocol,
            )
            summary = _summary("development_registry", payload)
        elif args.command == "freeze-manifest":
            payload = freeze_holdout_manifest(
                args.private_payload,
                args.development_registry,
                args.output,
                audited_at=args.audited_at,
                frozen_at=args.frozen_at,
                protocol_path=args.protocol,
                attest_no_candidate=args.attest_no_candidate,
                candidate_created_at=args.candidate_created_at,
            )
            summary = _summary("semantic_holdout_manifest", payload, args.output)
        elif args.command == "validate-manifest":
            payload = validate_holdout_manifest(
                args.private_payload,
                args.development_registry,
                args.manifest,
                protocol_path=args.protocol,
            )
            summary = _summary("semantic_holdout_manifest", payload)
        else:  # pragma: no cover - argparse prevents this.
            _refuse("unsupported_command")
    except FreezeRefusal as error:
        print(
            json.dumps({"reason": error.code, "status": "refused"}, sort_keys=True),
            file=sys.stderr,
        )
        return 2
    except Exception:
        print(
            json.dumps({"reason": "internal_error", "status": "refused"}, sort_keys=True),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
