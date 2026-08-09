"""Sealed semantic holdout review evidence and verdict validation."""

from __future__ import annotations

import math
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from firelens.evaluation.common import (
    assert_recomputed_summary_matches as _assert_recomputed_summary_matches,
)
from firelens.evaluation.common import (
    file_sha256,
)
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
from firelens.evaluation.semantic_inputs import (
    _semantic_development_registry,
    _semantic_development_registry_payload,
    _semantic_holdout_candidate_report,
    _semantic_holdout_manifest,
    _semantic_holdout_manifest_payload,
)
from firelens.evaluation.semantic_review import _semantic_presentation_history


def _semantic_holdout(
    candidate_report: dict[str, Any] | None,
    review_bundle: dict[str, Any] | None = None,
    *,
    manifest: dict[str, Any] | None = None,
    development_registry: dict[str, Any] | None = None,
    candidate_report_sha256: str | None = None,
    review_bundle_sha256: str | None = None,
    dataset_manifest_sha256: str | None = None,
    development_registry_sha256: str | None = None,
    submitted_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if candidate_report is None and review_bundle is None and submitted_summary is None:
        return {"status": "not_run"}
    if (
        candidate_report is None
        or review_bundle is None
        or manifest is None
        or development_registry is None
    ):
        raise ValueError(
            "semantic holdout requires the candidate report, review bundle, manifest, "
            "and frozen development registry"
        )
    candidate_report_digest = _require_digest(
        candidate_report_sha256, context="semantic holdout candidate report digest"
    )
    review_bundle_digest = _require_digest(
        review_bundle_sha256, context="semantic holdout review bundle digest"
    )
    manifest_digest = _require_digest(
        dataset_manifest_sha256, context="semantic holdout manifest digest"
    )
    development_registry_digest = _require_digest(
        development_registry_sha256,
        context="semantic holdout development registry digest",
    )
    development_registry = _semantic_development_registry_payload(development_registry)
    manifest = _semantic_holdout_manifest_payload(
        manifest,
        development_registry=development_registry,
        development_registry_sha256=development_registry_digest,
    )
    report = _semantic_holdout_candidate_report(
        candidate_report,
        manifest=manifest,
        dataset_manifest_sha256=manifest_digest,
    )
    _require_exact_keys(
        review_bundle,
        {
            "bundle_version",
            "generated_at",
            "candidate_id",
            "candidate_identity_sha256",
            "candidate_report_sha256",
            "dataset_sha256",
            "dataset_manifest_sha256",
            "development_registry_sha256",
            "case_count",
            "case_ids",
            "presentation",
            "presentation_log",
            "reviewer_registry",
            "adjudicator",
            "cases",
        },
        context="semantic holdout review bundle",
    )
    if review_bundle.get("bundle_version") != "firelens_semantic_holdout_review_bundle.v2":
        raise ValueError("semantic holdout review bundle uses an unsupported version")
    bundle_generated_at = _require_timestamp(
        review_bundle.get("generated_at"), context="semantic holdout review bundle generated_at"
    )
    if review_bundle.get("candidate_id") != report["candidate_id"]:
        raise ValueError("semantic holdout review bundle targets the wrong candidate")
    if review_bundle.get("candidate_identity_sha256") != report["candidate_identity_sha256"]:
        raise ValueError("semantic holdout review bundle has the wrong candidate identity")
    if review_bundle.get("candidate_report_sha256") != candidate_report_digest:
        raise ValueError("semantic holdout review bundle does not match the candidate report")
    if review_bundle.get("dataset_sha256") != manifest["dataset_sha256"]:
        raise ValueError("semantic holdout review bundle uses the wrong dataset commitment")
    if review_bundle.get("dataset_manifest_sha256") != manifest_digest:
        raise ValueError("semantic holdout review bundle uses the wrong manifest")
    if review_bundle.get("development_registry_sha256") != development_registry_digest:
        raise ValueError("semantic holdout review bundle uses the wrong development registry")
    case_count = _strict_int(
        review_bundle, "case_count", "semantic holdout review bundle", minimum=25
    )
    if case_count != manifest["case_count"]:
        raise ValueError("semantic holdout review bundle case_count differs from manifest")
    expected_case_ids = [row["case_id"] for row in manifest["case_roster"]]
    if review_bundle.get("case_ids") != expected_case_ids:
        raise ValueError("semantic holdout review bundle roster differs from frozen manifest")

    presentation = review_bundle.get("presentation")
    if not isinstance(presentation, dict):
        raise ValueError("semantic holdout presentation evidence must be an object")
    presentation_log = review_bundle.get("presentation_log")
    if not isinstance(presentation_log, dict):
        raise ValueError("semantic holdout presentation log must be an object")

    reviewer_registry = review_bundle.get("reviewer_registry")
    if not isinstance(reviewer_registry, list) or len(reviewer_registry) != 2:
        raise ValueError("semantic holdout requires exactly two named reviewers")
    reviewers: dict[str, str] = {}
    for index, reviewer in enumerate(reviewer_registry):
        if not isinstance(reviewer, dict):
            raise ValueError(f"semantic holdout reviewer {index} must be an object")
        _require_exact_keys(
            reviewer,
            {"reviewer_id", "name"},
            context=f"semantic holdout reviewer {index}",
        )
        reviewer_id = _require_nonempty_string(
            reviewer.get("reviewer_id"), context=f"semantic holdout reviewer {index} ID"
        )
        name = _require_nonempty_string(
            reviewer.get("name"), context=f"semantic holdout reviewer {index} name"
        )
        if reviewer_id in reviewers:
            raise ValueError("semantic holdout reviewer IDs must be unique")
        reviewers[reviewer_id] = name
    if len(set(reviewers.values())) != len(reviewers):
        raise ValueError("semantic holdout reviewer names must identify distinct people")

    adjudicator = review_bundle.get("adjudicator")
    if not isinstance(adjudicator, dict):
        raise ValueError("semantic holdout adjudicator must be an object")
    _require_exact_keys(
        adjudicator,
        {"adjudicator_id", "name"},
        context="semantic holdout adjudicator",
    )
    adjudicator_id = _require_nonempty_string(
        adjudicator.get("adjudicator_id"), context="semantic holdout adjudicator ID"
    )
    adjudicator_name = _require_nonempty_string(
        adjudicator.get("name"), context="semantic holdout adjudicator name"
    )
    if adjudicator_id in reviewers or adjudicator_name in reviewers.values():
        raise ValueError("semantic holdout adjudicator must be distinct from both reviewers")

    report_generated_at = _require_timestamp(
        report.get("generated_at"), context="semantic holdout report generated_at"
    )
    presentation_history = _semantic_presentation_history(
        presentation,
        presentation_log,
        report=report,
        expected_case_ids=expected_case_ids,
        reviewers=reviewers,
        adjudicator_id=adjudicator_id,
        candidate_report_sha256=candidate_report_digest,
        dataset_manifest_sha256=manifest_digest,
        development_registry_sha256=development_registry_digest,
        report_generated_at=report_generated_at,
        bundle_generated_at=bundle_generated_at,
    )
    report_cases = {case["case_id"]: case for case in report["cases"]}
    bundle_cases = review_bundle.get("cases")
    if not isinstance(bundle_cases, list) or len(bundle_cases) != case_count:
        raise ValueError("semantic holdout review bundle must retain every case")
    if [case.get("case_id") for case in bundle_cases if isinstance(case, dict)] != (
        presentation_history["actor_orders"][("adjudicator", adjudicator_id)]
    ):
        raise ValueError(
            "semantic holdout review rows do not follow the randomized presentation"
        )

    approved_case_count = 0
    unsupported_or_unclear = 0
    dangerous_omission_count = 0
    claim_count = 0
    agreement_count = 0
    first_reviewer_labels: Counter[str] = Counter()
    second_reviewer_labels: Counter[str] = Counter()
    reviewer_ids_used: set[str] = set()
    adjudication_times: list[datetime] = []
    valid_labels = {"supported", "unsupported", "unclear"}
    for case_index, case_review in enumerate(bundle_cases):
        if not isinstance(case_review, dict):
            raise ValueError(f"semantic holdout review case {case_index} must be an object")
        _require_exact_keys(
            case_review,
            {"case_id", "independent_reviews", "adjudication"},
            context=f"semantic holdout review case {case_index}",
        )
        case_id = case_review.get("case_id")
        candidate_case = report_cases.get(case_id)
        if candidate_case is None:
            raise ValueError(
                "semantic holdout review contains a case outside the frozen roster"
            )
        expected_claim_ids = [claim["claim_id"] for claim in candidate_case["claims"]]
        independent_reviews = case_review.get("independent_reviews")
        if not isinstance(independent_reviews, list) or len(independent_reviews) != 2:
            raise ValueError(f"semantic holdout case {case_id} requires exactly two reviews")
        case_reviewer_ids: list[str] = []
        review_times: list[datetime] = []
        review_label_sequences: list[list[str]] = []
        for review_index, review in enumerate(independent_reviews):
            if not isinstance(review, dict):
                raise ValueError(
                    f"semantic holdout case {case_id} review {review_index} must be an object"
                )
            _require_exact_keys(
                review,
                {
                    "reviewer_id",
                    "reviewed_at",
                    "presentation_event_sha256",
                    "independent",
                    "blinded_to_candidate_identity",
                    "blinded_to_other_review",
                    "claim_labels",
                    "dangerous_omission",
                    "case_decision",
                },
                context=f"semantic holdout case {case_id} review {review_index}",
            )
            raw_reviewer_id = review.get("reviewer_id")
            if not isinstance(raw_reviewer_id, str) or raw_reviewer_id not in reviewers:
                raise ValueError(f"semantic holdout case {case_id} uses an unnamed reviewer")
            reviewer_id = raw_reviewer_id
            case_reviewer_ids.append(reviewer_id)
            reviewer_ids_used.add(reviewer_id)
            reviewed_at = _require_timestamp(
                review.get("reviewed_at"),
                context=f"semantic holdout case {case_id} review timestamp",
            )
            if reviewed_at <= report_generated_at:
                raise ValueError(
                    f"semantic holdout case {case_id} review predates candidate generation"
                )
            presentation_event_digest = _require_digest(
                review.get("presentation_event_sha256"),
                context=f"semantic holdout case {case_id} reviewer presentation event",
            )
            review_exposure = presentation_history["events_by_exposure"].get(
                ("reviewer", reviewer_id, case_id)
            )
            if (
                review_exposure is None
                or presentation_event_digest != review_exposure["event"]["event_sha256"]
            ):
                raise ValueError(
                    f"semantic holdout case {case_id} review is not bound to its presentation"
                )
            if review_exposure["presented_at"] >= reviewed_at:
                raise ValueError(
                    f"semantic holdout case {case_id} review predates its presentation"
                )
            review_times.append(reviewed_at)
            for key in (
                "independent",
                "blinded_to_candidate_identity",
                "blinded_to_other_review",
            ):
                if not _strict_bool(review, key, f"semantic holdout case {case_id} review"):
                    raise ValueError(
                        f"semantic holdout case {case_id} review does not establish {key}"
                    )
            dangerous = _strict_bool(
                review, "dangerous_omission", f"semantic holdout case {case_id} review"
            )
            claim_labels = review.get("claim_labels")
            if not isinstance(claim_labels, list):
                raise ValueError(f"semantic holdout case {case_id} claim labels must be a list")
            labels: list[str] = []
            actual_claim_ids: list[str] = []
            for label_index, label_row in enumerate(claim_labels):
                if not isinstance(label_row, dict):
                    raise ValueError(
                        f"semantic holdout case {case_id} label {label_index} must be an object"
                    )
                _require_exact_keys(
                    label_row,
                    {"claim_id", "label"},
                    context=f"semantic holdout case {case_id} label {label_index}",
                )
                claim_id = label_row.get("claim_id")
                if not isinstance(claim_id, str):
                    raise ValueError(f"semantic holdout case {case_id} has an invalid claim ID")
                actual_claim_ids.append(claim_id)
                label = label_row.get("label")
                if label not in valid_labels:
                    raise ValueError(
                        f"semantic holdout case {case_id} has an invalid claim label"
                    )
                labels.append(label)
            if actual_claim_ids != expected_claim_ids:
                raise ValueError(
                    f"semantic holdout case {case_id} review does not label every exact claim"
                )
            expected_decision = (
                "approved"
                if all(label == "supported" for label in labels) and not dangerous
                else "rejected"
            )
            if review.get("case_decision") != expected_decision:
                raise ValueError(
                    f"semantic holdout case {case_id} reviewer decision disagrees with labels"
                )
            review_label_sequences.append(labels)
        if case_reviewer_ids != list(reviewers):
            raise ValueError(
                f"semantic holdout case {case_id} requires two distinct reviewers "
                "in canonical registry order"
            )

        adjudication = case_review.get("adjudication")
        if not isinstance(adjudication, dict):
            raise ValueError(f"semantic holdout case {case_id} adjudication must be an object")
        _require_exact_keys(
            adjudication,
            {
                "adjudicator_id",
                "adjudicated_at",
                "presentation_event_sha256",
                "reviewer_decisions_locked",
                "independent_reviews_sha256",
                "resolution_status",
                "claim_labels",
                "dangerous_omission",
                "case_decision",
            },
            context=f"semantic holdout case {case_id} adjudication",
        )
        if adjudication.get("adjudicator_id") != adjudicator_id:
            raise ValueError(f"semantic holdout case {case_id} uses the wrong adjudicator")
        adjudicated_at = _require_timestamp(
            adjudication.get("adjudicated_at"),
            context=f"semantic holdout case {case_id} adjudication timestamp",
        )
        if adjudicated_at <= max(review_times):
            raise ValueError(
                f"semantic holdout case {case_id} was adjudicated before reviews were complete"
            )
        if adjudicated_at > bundle_generated_at:
            raise ValueError(
                f"semantic holdout case {case_id} adjudication postdates its review bundle"
            )
        adjudication_event_digest = _require_digest(
            adjudication.get("presentation_event_sha256"),
            context=f"semantic holdout case {case_id} adjudication presentation event",
        )
        adjudication_exposure = presentation_history["events_by_exposure"].get(
            ("adjudicator", adjudicator_id, case_id)
        )
        if (
            adjudication_exposure is None
            or adjudication_event_digest != adjudication_exposure["event"]["event_sha256"]
        ):
            raise ValueError(
                f"semantic holdout case {case_id} adjudication is not bound to its presentation"
            )
        if (
            adjudication_exposure["presented_at"] <= max(review_times)
            or adjudication_exposure["presented_at"] >= adjudicated_at
        ):
            raise ValueError(
                f"semantic holdout case {case_id} adjudication presentation is out of order"
            )
        adjudication_times.append(adjudicated_at)
        if not _strict_bool(
            adjudication,
            "reviewer_decisions_locked",
            f"semantic holdout case {case_id} adjudication",
        ):
            raise ValueError(
                f"semantic holdout case {case_id} reviewer decisions were not locked"
            )
        _require_digest(
            adjudication.get("independent_reviews_sha256"),
            context=f"semantic holdout case {case_id} independent-review digest",
        )
        if adjudication["independent_reviews_sha256"] != _sha256_json(independent_reviews):
            raise ValueError(
                f"semantic holdout case {case_id} independent-review digest is inconsistent"
            )
        if (
            adjudication_exposure["event"]["review_material_sha256"]
            != adjudication["independent_reviews_sha256"]
        ):
            raise ValueError(
                f"semantic holdout case {case_id} adjudication presentation uses stale reviews"
            )
        if adjudication.get("resolution_status") != "resolved":
            raise ValueError(f"semantic holdout case {case_id} remains unresolved")
        final_labels = adjudication.get("claim_labels")
        if not isinstance(final_labels, list):
            raise ValueError(
                f"semantic holdout case {case_id} adjudicated claim labels must be a list"
            )
        final_claim_ids: list[str] = []
        final_label_values: list[str] = []
        for label_index, label_row in enumerate(final_labels):
            if not isinstance(label_row, dict):
                raise ValueError(
                    f"semantic holdout case {case_id} adjudicated label {label_index} must be an object"
                )
            _require_exact_keys(
                label_row,
                {"claim_id", "label"},
                context=f"semantic holdout case {case_id} adjudicated label {label_index}",
            )
            claim_id = label_row.get("claim_id")
            if not isinstance(claim_id, str):
                raise ValueError(
                    f"semantic holdout case {case_id} has an invalid adjudicated claim ID"
                )
            final_claim_ids.append(claim_id)
            label = label_row.get("label")
            if label not in valid_labels:
                raise ValueError(
                    f"semantic holdout case {case_id} has an invalid adjudicated label"
                )
            final_label_values.append(label)
        if final_claim_ids != expected_claim_ids:
            raise ValueError(
                f"semantic holdout case {case_id} adjudication does not cover every exact claim"
            )
        final_dangerous = _strict_bool(
            adjudication,
            "dangerous_omission",
            f"semantic holdout case {case_id} adjudication",
        )
        final_decision = (
            "approved"
            if all(label == "supported" for label in final_label_values) and not final_dangerous
            else "rejected"
        )
        if adjudication.get("case_decision") != final_decision:
            raise ValueError(
                f"semantic holdout case {case_id} adjudicated decision disagrees with findings"
            )
        approved_case_count += int(final_decision == "approved")
        unsupported_or_unclear += sum(
            label in {"unsupported", "unclear"} for label in final_label_values
        )
        dangerous_omission_count += int(final_dangerous)
        for first_label, second_label in zip(
            review_label_sequences[0], review_label_sequences[1], strict=True
        ):
            claim_count += 1
            agreement_count += int(first_label == second_label)
            first_reviewer_labels[first_label] += 1
            second_reviewer_labels[second_label] += 1
    if reviewer_ids_used != set(reviewers):
        raise ValueError("semantic holdout reviewer registry contains unused identities")

    agreement_rate = agreement_count / claim_count
    expected_agreement = sum(
        (first_reviewer_labels[label] / claim_count)
        * (second_reviewer_labels[label] / claim_count)
        for label in valid_labels
    )
    if math.isclose(expected_agreement, 1.0, rel_tol=0, abs_tol=1e-15):
        cohens_kappa = 1.0 if math.isclose(agreement_rate, 1.0) else 0.0
    else:
        cohens_kappa = (agreement_rate - expected_agreement) / (1.0 - expected_agreement)
    qualified = (
        approved_case_count == case_count
        and unsupported_or_unclear == 0
        and dangerous_omission_count == 0
    )
    recomputed_summary = {
        "summary_version": "firelens_semantic_holdout_summary.v3",
        "candidate_id": report["candidate_id"],
        "candidate_identity_sha256": report["candidate_identity_sha256"],
        "commit": report["commit"],
        "corpus_sha256": report["corpus_sha256"],
        "vector_matrix_sha256": report["vector_matrix_sha256"],
        "document_context_sha256": report["document_context_sha256"],
        "repairs_sha256": report["repairs_sha256"],
        "configuration_sha256": report["configuration_sha256"],
        "dataset_sha256": report["dataset_sha256"],
        "dataset_manifest_sha256": manifest_digest,
        "development_registry_sha256": development_registry_digest,
        "candidate_report_sha256": candidate_report_digest,
        "review_bundle_sha256": review_bundle_digest,
        "presentation_log_sha256": presentation_history["presentation_log_sha256"],
        "presentation_log_head_sha256": presentation_history["head_event_sha256"],
        "presentation_event_count": presentation_history["event_count"],
        "randomization_context_sha256": presentation_history["randomization_context_sha256"],
        "case_count": case_count,
        "claim_count": claim_count,
        "independent_review_count": case_count * 2,
        "approved_case_count": approved_case_count,
        "unsupported_or_unclear": unsupported_or_unclear,
        "dangerous_omission_count": dangerous_omission_count,
        "unresolved_case_count": 0,
        "reviewers": sorted(reviewers.values()),
        "adjudicator": adjudicator_name,
        "reviewed_at": max(adjudication_times).astimezone(UTC).isoformat(),
        "claim_label_agreement_count": agreement_count,
        "claim_label_agreement_rate": agreement_rate,
        "claim_label_cohens_kappa": cohens_kappa,
        "qualified": qualified,
    }
    if submitted_summary is not None:
        _assert_recomputed_summary_matches(
            submitted_summary,
            recomputed_summary,
            context="semantic holdout",
        )
    return {"status": "complete", **recomputed_summary}


def validate_semantic_holdout(
    candidate_report_path: Path,
    review_bundle_path: Path,
    manifest_path: Path,
    development_registry_path: Path,
    summary_path: Path | None = None,
) -> dict[str, Any]:
    candidate_report = _read_report(candidate_report_path)
    review_bundle = _read_report(review_bundle_path)
    development_registry = _semantic_development_registry(development_registry_path)
    development_registry_digest = file_sha256(development_registry_path)
    manifest = _semantic_holdout_manifest(
        manifest_path,
        development_registry=development_registry,
        development_registry_sha256=development_registry_digest,
    )
    if candidate_report is None or review_bundle is None:
        raise ValueError("semantic holdout raw artifacts are missing")
    return _semantic_holdout(
        candidate_report,
        review_bundle,
        manifest=manifest,
        development_registry=development_registry,
        candidate_report_sha256=file_sha256(candidate_report_path),
        review_bundle_sha256=file_sha256(review_bundle_path),
        dataset_manifest_sha256=file_sha256(manifest_path),
        development_registry_sha256=development_registry_digest,
        submitted_summary=_read_report(summary_path),
    )
