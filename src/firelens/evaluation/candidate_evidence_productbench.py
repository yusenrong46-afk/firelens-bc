"""ProductBench and structural-evaluation checks for candidate evidence."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from firelens.evaluation.candidate_evidence_common import file_record, load_json, strict_file

# ProductBench reports preserve the legacy aggregate ``generate`` counter for
# observability and also record the concrete generation paths.  Candidate
# evidence must bind the complete v2 shape so a report cannot hide a new call
# class by omitting it.
_PROVIDER_CALL_COUNTERS = frozenset(
    {
        "plan",
        "embed",
        "rerank",
        "generate",
        "generate_contexts",
        "generate_grounded",
        "generate_background",
        "chat_turn",
    }
)
_CANONICAL_BILLABLE_COUNTERS = frozenset(
    {
        "plan",
        "embed",
        "rerank",
        "generate_contexts",
        "generate_grounded",
        "generate_background",
        "chat_turn",
    }
)


def _nonnegative_number(value: Any, label: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{label} is invalid")
    return float(value)


def validate_productbench_deterministic(
    value: Any,
    *,
    root: Path,
    commit: str,
    tree: str,
    exact_object: Callable[[Any, set[str], str], dict[str, Any]],
    nonempty_string: Callable[[Any, str], str],
    validate_timestamp: Callable[[str], str],
) -> dict[str, Any]:
    """Bind one complete zero-cost ProductBench run to this exact candidate tree."""

    report = exact_object(
        value,
        {
            "schema_version",
            "generated_at",
            "identity",
            "provider_boundary",
            "execution_complete",
            "passed",
            "failed",
            "case_count",
            "cost",
            "provider_activity",
            "results",
            "offline_execution",
        },
        "ProductBench deterministic evidence",
    )
    if report["schema_version"] != "firelens.productbench_report.v2":
        raise ValueError("ProductBench deterministic evidence schema is invalid")
    validate_timestamp(nonempty_string(report["generated_at"], "ProductBench generated_at"))
    manifest = load_json(
        strict_file(root, "data/evaluation/productbench_v2.manifest.json"),
        "ProductBench manifest",
    )
    if not isinstance(manifest, dict):
        raise ValueError("ProductBench manifest is invalid")
    tiers = manifest.get("tiers")
    expected_ids = tiers.get("offline_fake") if isinstance(tiers, dict) else None
    if (
        manifest.get("schema_version") != "firelens.productbench_manifest.v2"
        or manifest.get("status") != "development_unsealed"
        or not isinstance(expected_ids, list)
        or not expected_ids
        or any(not isinstance(case_id, str) or not case_id for case_id in expected_ids)
        or len(expected_ids) != len(set(expected_ids))
    ):
        raise ValueError("ProductBench manifest offline tier is invalid")
    identity = exact_object(
        report["identity"],
        {
            "commit",
            "tree",
            "catalog_path",
            "manifest_path",
            "raw_catalog_sha256",
            "manifest_sha256",
            "contract_sha256",
            "executable_catalog_sha256",
            "schema_version",
            "tier",
            "status",
            "case_ids",
            "git_clean",
            "status_sha256",
            "tracked_diff_sha256",
            "untracked_content_sha256",
            "untracked_file_count",
        },
        "ProductBench identity",
    )
    catalog_record = file_record(root, "data/evaluation/productbench_journeys_50.json")
    manifest_record = file_record(root, "data/evaluation/productbench_v2.manifest.json")
    if (
        identity
        != {
            "commit": commit,
            "tree": tree,
            "catalog_path": "data/evaluation/productbench_journeys_50.json",
            "manifest_path": "data/evaluation/productbench_v2.manifest.json",
            "raw_catalog_sha256": manifest.get("raw_catalog_sha256"),
            "manifest_sha256": manifest_record["sha256"],
            "contract_sha256": manifest.get("contract_sha256"),
            "executable_catalog_sha256": manifest.get("executable_catalog_sha256"),
            "schema_version": manifest.get("schema_version"),
            "tier": "offline_fake",
            "status": "development_unsealed",
            "case_ids": expected_ids,
            "git_clean": True,
            "status_sha256": hashlib.sha256(b"").hexdigest(),
            "tracked_diff_sha256": hashlib.sha256(b"").hexdigest(),
            "untracked_content_sha256": hashlib.sha256(b"[]").hexdigest(),
            "untracked_file_count": 0,
        }
        or manifest.get("raw_catalog_sha256") != catalog_record["sha256"]
    ):
        raise ValueError("ProductBench deterministic evidence is stale or mismatched")
    if (
        report["provider_boundary"] != "offline_fake"
        or report["execution_complete"] is not True
        or report["case_count"] != len(expected_ids)
        or report["passed"] != len(expected_ids)
        or report["failed"] != 0
    ):
        raise ValueError("ProductBench deterministic execution did not pass")
    provider_activity = exact_object(
        report["provider_activity"],
        {"call_counts", "total_calls"},
        "ProductBench provider activity",
    )
    call_counts = provider_activity["call_counts"]
    if (
        not isinstance(call_counts, dict)
        or set(call_counts) != _PROVIDER_CALL_COUNTERS
        or any(
            not isinstance(count, int) or isinstance(count, bool) or count < 0
            for count in call_counts.values()
        )
        or call_counts["generate"]
        != call_counts["generate_grounded"] + call_counts["generate_background"]
        or provider_activity["total_calls"]
        != sum(call_counts[name] for name in _CANONICAL_BILLABLE_COUNTERS)
    ):
        raise ValueError("ProductBench deterministic provider activity is invalid")
    cost = exact_object(
        report["cost"],
        {"max_cost_usd", "reported_cost_usd", "ceiling_exceeded"},
        "ProductBench cost evidence",
    )
    if (
        _nonnegative_number(cost["max_cost_usd"], "ProductBench max cost") != 0.0
        or _nonnegative_number(cost["reported_cost_usd"], "ProductBench reported cost") != 0.0
        or cost["ceiling_exceeded"] is not False
    ):
        raise ValueError("ProductBench deterministic evidence is not zero-cost")
    offline_execution = exact_object(
        report["offline_execution"],
        {"live_fixture", "fake_provider_calls"},
        "ProductBench offline execution",
    )
    calls = offline_execution["fake_provider_calls"]
    if (
        offline_execution["live_fixture"] != "productbench_official_record_double.v1"
        or not isinstance(calls, dict)
        or set(calls) != {"plan", "embed", "rerank", "generate"}
        or any(
            not isinstance(count, int) or isinstance(count, bool) or count < 0
            for count in calls.values()
        )
    ):
        raise ValueError("ProductBench deterministic offline boundary is invalid")
    results = report["results"]
    if not isinstance(results, list) or len(results) != len(expected_ids):
        raise ValueError("ProductBench deterministic result roster is invalid")
    observed_ids: list[str] = []
    for row in results:
        result = exact_object(
            row,
            {
                "id",
                "passed",
                "issues",
                "contract",
                "latency_ms",
                "call_evidence",
                "scope_evidence",
                "trace",
                "cost_usd",
            },
            "ProductBench deterministic result",
        )
        case_id = nonempty_string(result["id"], "ProductBench result id")
        observed_ids.append(case_id)
        if (
            result["passed"] is not True
            or result["issues"] != []
            or not isinstance(result["contract"], dict)
            or _nonnegative_number(result["latency_ms"], "ProductBench result latency") < 0
            or _nonnegative_number(result["cost_usd"], "ProductBench result cost") != 0.0
        ):
            raise ValueError(f"ProductBench deterministic result failed: {case_id}")
        trace = exact_object(
            result["trace"],
            {"trace_id", "tool_names", "response_sha256"},
            "ProductBench deterministic trace",
        )
        if (
            not isinstance(trace["trace_id"], str)
            or not trace["trace_id"]
            or not isinstance(trace["tool_names"], list)
            or any(not isinstance(name, str) or not name for name in trace["tool_names"])
            or not isinstance(trace["response_sha256"], str)
            or re.fullmatch(r"[0-9a-f]{64}", trace["response_sha256"]) is None
        ):
            raise ValueError(f"ProductBench deterministic trace is invalid: {case_id}")
        call_evidence = exact_object(
            result["call_evidence"],
            {"tool_names", "tool_attempts", "provider_calls"},
            "ProductBench deterministic call evidence",
        )
        if (
            not isinstance(call_evidence["tool_names"], list)
            or any(
                not isinstance(name, str) or not name for name in call_evidence["tool_names"]
            )
            or call_evidence["tool_attempts"] != len(call_evidence["tool_names"])
            or not isinstance(call_evidence["provider_calls"], dict)
            or set(call_evidence["provider_calls"]) != _PROVIDER_CALL_COUNTERS
            or any(
                not isinstance(count, int) or isinstance(count, bool) or count < 0
                for count in call_evidence["provider_calls"].values()
            )
            or call_evidence["provider_calls"]["generate"]
            != call_evidence["provider_calls"]["generate_grounded"]
            + call_evidence["provider_calls"]["generate_background"]
        ):
            raise ValueError(
                f"ProductBench deterministic execution evidence is invalid: {case_id}"
            )
        scope_evidence = exact_object(
            result["scope_evidence"],
            {"observed_location_labels", "selected_result_id"},
            "ProductBench deterministic scope evidence",
        )
        if (
            not isinstance(scope_evidence["observed_location_labels"], list)
            or any(
                not isinstance(label, str) or not label
                for label in scope_evidence["observed_location_labels"]
            )
            or (
                scope_evidence["selected_result_id"] is not None
                and (
                    not isinstance(scope_evidence["selected_result_id"], str)
                    or not scope_evidence["selected_result_id"]
                )
            )
        ):
            raise ValueError(f"ProductBench deterministic scope evidence is invalid: {case_id}")
    if observed_ids != expected_ids:
        raise ValueError("ProductBench deterministic result roster does not match the manifest")
    return {
        "tier": "offline_fake",
        "case_count": len(expected_ids),
        "passed": len(expected_ids),
        "catalog_sha256": catalog_record["sha256"],
        "manifest_sha256": manifest_record["sha256"],
    }


def validate_structured_eval(value: Any, *, root: Path) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("structured-publication evidence must be an object")
    structural = value.get("structural_gates")
    architecture = value.get("architecture")
    if value.get("evidence_class") != "EXECUTED" or value.get("structural_pass") is not True:
        raise ValueError("structured-publication evidence did not pass")
    if (
        not isinstance(structural, dict)
        or not structural
        or any(
            not isinstance(item, int) or isinstance(item, bool) or item != 0
            for item in structural.values()
        )
    ):
        raise ValueError("structured-publication structural leak counters are invalid")
    if (
        not isinstance(architecture, dict)
        or architecture.get("compiler_exclusivity_offenders") != []
        or architecture.get("serving_broad_exception") != []
    ):
        raise ValueError("structured-publication architecture evidence did not pass")
    hashes = value.get("hashes")
    expected_hashes = {
        "hard_probe": file_record(root, "data/evaluation/hard_probe.v1.yaml")["sha256"],
        "typed_inventory": file_record(root, "data/typed_claims/high_risk_v1.yaml")["sha256"],
    }
    if not isinstance(hashes, dict) or any(
        hashes.get(name) != expected for name, expected in expected_hashes.items()
    ):
        raise ValueError("structured-publication evidence artifact hashes are invalid")
    return value
