"""Freeze or verify the public identities for the private semantic holdout."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

from firelens.evaluation.semantic_holdout_freeze_support import (
    DEFAULT_PROTOCOL,
    FreezeRefusal,
    _canonical_digest,
    _case_identifier,
    _content_string,
    _digest,
    _exact_keys,
    _lexical_path,
    _lower_identifier,
    _nonempty_string,
    _read_json,
    _refuse,
    _require_pre_candidate_guard,
    _sorted_unique_strings,
    _timestamp,
    _write_new_public_json,
    load_protocol,
)
from firelens.evaluation.semantic_inputs import (
    _semantic_development_registry_payload,
    _semantic_holdout_manifest_payload,
)


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
        _semantic_development_registry_payload(registry)
    except ValueError:
        _refuse("development_registry_contract_rejected")
    return registry


def _load_development_registry(path: Path) -> tuple[dict[str, Any], str]:
    registry, raw = _read_json(path)
    try:
        _semantic_development_registry_payload(registry)
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
        input_payload = _validate_review_input(row.get("input_payload"), protocol=protocol)
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
        _semantic_holdout_manifest_payload(
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
        _semantic_holdout_manifest_payload(
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
        audited_at=_nonempty_string(audit.get("audited_at"), "holdout_audited_at_invalid"),
        frozen_at=_nonempty_string(manifest.get("frozen_at"), "holdout_frozen_at_invalid"),
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
