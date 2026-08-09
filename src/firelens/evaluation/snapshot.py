"""Benchmark snapshot identity and metric recomputation."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from firelens.evaluation.common import ROOT, file_sha256
from firelens.evaluation.runtime_artifact import (
    _runtime_artifact_metric_values,
    _runtime_candidate_id,
)
from firelens.evaluation.spec_models import BenchmarkSpec, MetricSpec


def _validated_metric_value(metric: MetricSpec, value: Any, *, label: str) -> Any:
    if value is None:
        return None
    if metric.value_type == "boolean":
        if type(value) is not bool:
            raise ValueError(f"{metric.key} {label} value must be a strict boolean")
        return value
    if metric.value_type == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{metric.key} {label} value must be an integer")
        return value
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{metric.key} {label} value must be numeric")
    if not math.isfinite(float(value)):
        raise ValueError(f"{metric.key} {label} value must be finite")
    return value


def _check_report_identity(
    name: str, observed: str | None, commit: str, *, required: bool = True
) -> None:
    if required and observed is None:
        raise ValueError(f"{name} report has no commit identity")
    if observed is not None and observed != commit:
        raise ValueError(f"{name} report commit {observed} does not match {commit}")


def _metrics(snapshot: dict[str, Any]) -> dict[str, float | bool | None]:
    hard = snapshot["hard_probe_offline"]
    qualified_hard = snapshot["hard_probe_qualified"]
    live = snapshot["live"]
    development_retrieval = snapshot["development_retrieval"]
    semantic = snapshot["semantic_review"]
    semantic_holdout = snapshot["semantic_holdout"]
    retrieval_review = snapshot["retrieval_review"]
    retrieval = snapshot["retrieval_qualification"]
    ux = snapshot["ux"]
    preview = snapshot["preview"]
    deployment = snapshot["deployment"]
    frontend_bundle = snapshot["frontend_bundle"]
    frontend_surface = snapshot["frontend_surface"]
    frontend_manual = snapshot["frontend_manual_review"]
    runtime_artifact = _runtime_artifact_metric_values(snapshot)
    frontend_performance = frontend_surface.get("worst_profile_p75") or {}
    return {
        "verification_passed": snapshot["verification"].get("passed"),
        "offline_hard_probe_pass_rate": hard.get("pass_rate"),
        "offline_hard_probe_critical_failures": hard.get("critical_failures"),
        "offline_hard_probe_p95_ms": hard.get("p95_latency_ms"),
        "frontend_initial_route_js_gzip_bytes": frontend_bundle.get("initial_js_gzip_bytes"),
        "frontend_lazy_js_gzip_bytes": frontend_bundle.get("lazy_js_gzip_bytes"),
        "frontend_initial_css_gzip_bytes": frontend_bundle.get("initial_css_gzip_bytes"),
        "frontend_lazy_css_gzip_bytes": frontend_bundle.get("lazy_css_gzip_bytes"),
        "frontend_server_js_gzip_bytes": frontend_bundle.get("server_js_gzip_bytes"),
        "frontend_font_bytes": frontend_bundle.get("font_bytes"),
        "frontend_image_bytes": frontend_bundle.get("image_bytes"),
        "frontend_deployment_metadata_bytes": frontend_bundle.get("deployment_metadata_bytes"),
        "frontend_other_bytes": frontend_bundle.get("other_bytes"),
        "frontend_total_emitted_bytes": frontend_bundle.get("total_emitted_bytes"),
        "frontend_unclassified_output_bytes": frontend_bundle.get("unclassified_bytes"),
        "frontend_surface_qualified": frontend_surface.get("qualified"),
        "frontend_visual_matrix_pass_rate": frontend_surface.get("visual_matrix_pass_rate"),
        "frontend_css_layout_violation_count": frontend_surface.get(
            "css_layout_violation_count"
        ),
        "frontend_axe_wcag_a_aa_finding_count": frontend_surface.get(
            "axe_wcag_a_aa_finding_count"
        ),
        "frontend_runtime_violation_count": frontend_surface.get("runtime_violation_count"),
        "frontend_keyboard_journey_passed": frontend_surface.get("keyboard_journey_passed"),
        "frontend_map_list_parity": frontend_surface.get("map_list_parity"),
        "frontend_map_detail_integrity": frontend_surface.get("map_detail_integrity"),
        "frontend_map_marker_placement_sanity": frontend_surface.get(
            "map_marker_placement_sanity"
        ),
        "frontend_direct_third_party_tile_request_count": frontend_surface.get(
            "direct_third_party_tile_request_count"
        ),
        "frontend_worst_p75_lcp_ms": frontend_performance.get("lcp_ms"),
        "frontend_worst_p75_cls": frontend_performance.get("cls"),
        "frontend_worst_p75_inp_proxy_ms": frontend_performance.get("inp_interaction_proxy_ms"),
        "frontend_worst_p75_map_ready_ms": frontend_performance.get(
            "map_ready_after_interaction_ms"
        ),
        "frontend_manual_accessibility_qualified": frontend_manual.get(
            "accessibility_qualified"
        ),
        "frontend_manual_product_safety_qualified": frontend_manual.get(
            "product_safety_qualified"
        ),
        "frontend_manual_open_findings": frontend_manual.get("open_finding_count"),
        "live_qualified": live.get("qualified"),
        "live_cached_p95_ms": live.get("cached_p95_ms"),
        "development_retrieval_recall_at_5": development_retrieval.get("recall_at_5"),
        "development_retrieval_mrr_at_5": development_retrieval.get("mrr_at_5"),
        "development_retrieval_ndcg_at_5": development_retrieval.get("ndcg_at_5"),
        "development_retrieval_mean_source_coverage": development_retrieval.get(
            "mean_source_coverage"
        ),
        "development_retrieval_cost_usd": development_retrieval.get("reported_cost_usd"),
        "qualified_hard_probe_pass_rate": qualified_hard.get("pass_rate"),
        "qualified_hard_probe_cost_usd": qualified_hard.get("cost_usd"),
        "sealed_retrieval_qualified": retrieval.get("qualified"),
        "sealed_retrieval_repetitions": retrieval.get("repetitions"),
        "sealed_retrieval_min_recall_at_5": retrieval.get("min_recall_at_5"),
        "semantic_review_qualified": semantic.get("qualified"),
        "semantic_review_approval_rate": semantic.get("approval_rate"),
        "semantic_review_unsupported_or_unclear": (
            int(semantic.get("unsupported_verified_claim_count") or 0)
            + int(semantic.get("unclear_claim_count") or 0)
            if semantic.get("status") == "complete"
            else None
        ),
        "semantic_holdout_qualified": semantic_holdout.get("qualified"),
        "semantic_holdout_unsupported_or_unclear": semantic_holdout.get(
            "unsupported_or_unclear"
        ),
        "semantic_holdout_dangerous_omissions": semantic_holdout.get(
            "dangerous_omission_count"
        ),
        "retrieval_review_qualified": retrieval_review.get("qualified"),
        "retrieval_review_approval_rate": retrieval_review.get("approval_rate"),
        "ux_participant_count": ux.get("participant_count"),
        "ux_task_completion_rate": ux.get("task_completion_rate"),
        "ux_min_task_completion_rate": ux.get("min_task_completion_rate"),
        "ux_critical_error_count": ux.get("critical_error_count"),
        "ux_near_me_median_seconds": ux.get("near_me_median_seconds"),
        "ux_median_seq_score": ux.get("median_seq_score"),
        "ux_evidence_comprehension_rate": ux.get("evidence_comprehension_rate"),
        "ux_freshness_comprehension_rate": ux.get("freshness_comprehension_rate"),
        "ux_official_source_open_rate": ux.get("official_source_open_rate"),
        "ux_access_method_sampling_coverage": ux.get("accessibility_coverage"),
        "preview_qualified": preview.get("qualified"),
        "distributed_rate_limit_verified": deployment.get("distributed_rate_limit_verified"),
        "rollback_rehearsal_passed": deployment.get("rollback_rehearsal_passed"),
        **runtime_artifact,
    }


def _validated_snapshot_metrics(
    snapshot: dict[str, Any], spec: BenchmarkSpec, *, label: str
) -> dict[str, float | bool | None]:
    stored = snapshot.get("metrics")
    if not isinstance(stored, dict):
        raise ValueError(f"{label} snapshot has no stored metrics object")
    expected_keys = {metric.key for metric in spec.comparison_metrics}
    if set(stored) != expected_keys:
        missing = sorted(expected_keys - set(stored))
        unknown = sorted(set(stored) - expected_keys)
        raise ValueError(
            f"{label} snapshot metric schema mismatch; missing={missing}, unknown={unknown}"
        )
    try:
        recomputed = _metrics(snapshot)
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(
            f"{label} snapshot cannot recompute metrics from detailed sections"
        ) from error
    if set(recomputed) != expected_keys:
        missing = sorted(expected_keys - set(recomputed))
        unknown = sorted(set(recomputed) - expected_keys)
        raise ValueError(
            f"benchmark metric extractor differs from the specification; "
            f"missing={missing}, unknown={unknown}"
        )
    for metric in spec.comparison_metrics:
        stored_value = _validated_metric_value(metric, stored[metric.key], label=label)
        recomputed_value = _validated_metric_value(
            metric, recomputed[metric.key], label=f"{label} recomputed"
        )
        if type(stored_value) is not type(recomputed_value) or stored_value != recomputed_value:
            raise ValueError(
                f"{label} snapshot stored metric {metric.key} diverges from its "
                "detailed evidence"
            )
    return recomputed


def _candidate_identity(snapshot: dict[str, Any]) -> dict[str, Any]:
    identity = snapshot.get("identity")
    if not isinstance(identity, dict):
        raise ValueError("before snapshot has no candidate identity")
    keys = (
        "commit",
        "branch",
        "candidate_id",
        "release_version",
        "corpus_version",
        "corpus_sha256",
        "vector_matrix_sha256",
        "vector_manifest_sha256",
        "document_context_sha256",
        "repairs_sha256",
        "configuration_sha256",
        "execution_environment",
    )
    missing = [key for key in keys if key not in identity]
    if missing:
        raise ValueError(f"before snapshot candidate identity is incomplete: {missing}")
    if not isinstance(identity.get("commit"), str) or not identity["commit"].strip():
        raise ValueError("before snapshot candidate identity has no commit")
    return {key: identity[key] for key in keys}


def _current_benchmark_identities(
    spec: BenchmarkSpec, spec_path: Path, *, repository_root: Path = ROOT
) -> tuple[str, dict[str, str], dict[str, str]]:
    return (
        file_sha256(spec_path),
        {
            relative: file_sha256(repository_root / relative)
            for relative in spec.identity_inputs
        },
        {relative: file_sha256(repository_root / relative) for relative in spec.harness_inputs},
    )


def _validate_before_snapshot_contract(
    before: dict[str, Any],
    spec: BenchmarkSpec,
    spec_path: Path,
    *,
    repository_root: Path = ROOT,
) -> dict[str, float | bool | None]:
    if before.get("schema_version") != "firelens_upgrade_benchmark_snapshot.v2":
        raise ValueError("before seal requires snapshot schema v2")
    if before.get("benchmark_id") != spec.benchmark_id or before.get("label") != "before":
        raise ValueError("before seal requires the matching before snapshot")
    if before.get("capture_complete") is not True:
        raise ValueError("before seal requires a complete before capture")
    if before.get("missing_required_metrics") not in ([], None):
        raise ValueError("before seal cannot attest a snapshot with missing metrics")
    metrics = _validated_snapshot_metrics(before, spec, label="before")
    missing_paired = sorted(
        metric.key
        for metric in spec.comparison_metrics
        if metric.comparison_mode == "paired" and metrics.get(metric.key) is None
    )
    if missing_paired:
        raise ValueError(f"before seal requires every paired metric; missing={missing_paired}")
    identity = before.get("identity") or {}
    if identity.get("candidate_id") != _runtime_candidate_id(
        spec.benchmark_id, identity.get("commit", "")
    ):
        raise ValueError("before snapshot candidate ID is not canonical for its commit")
    spec_sha256, dataset_identity, harness_identity = _current_benchmark_identities(
        spec, spec_path, repository_root=repository_root
    )
    if identity.get("spec_sha256") != spec_sha256:
        raise ValueError("before snapshot does not match the current benchmark specification")
    if identity.get("identity_input_sha256") != dataset_identity:
        raise ValueError("before snapshot does not match current frozen evaluation inputs")
    if identity.get("harness_input_sha256") != harness_identity:
        raise ValueError("before snapshot does not match the current benchmark harness")
    _candidate_identity(before)
    return metrics
