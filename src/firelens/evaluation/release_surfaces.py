"""Preview safety, deployment evidence, and qualification template validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from firelens.evaluation.common import (
    blank_rollback_evidence as _blank_rollback_evidence,
)
from firelens.evaluation.common import (
    file_sha256,
)
from firelens.evaluation.common import (
    p95 as _p95,
)
from firelens.evaluation.common import (
    read_report as _read_report,
)
from firelens.evaluation.common import (
    require_digest as _require_digest,
)
from firelens.evaluation.common import (
    require_environment_snapshot as _require_environment_snapshot,
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
from firelens.evaluation.common import (
    strict_number as _strict_number,
)
from firelens.evaluation.preview_raw_evidence import (
    _validate_preview_raw_response_artifact,
)
from firelens.evaluation.qualification_reports import _validated_public_live_rows
from firelens.evaluation.spec_models import BenchmarkSpec


def _validate_artifact_digest(value: Any, context: str) -> str:
    digest = str(value or "")
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise ValueError(f"{context} must declare a lowercase SHA-256 digest")
    return digest


def _bind_raw_deployment_evidence(
    *,
    report: dict[str, Any],
    evidence_key: str,
    digest_key: str,
    artifact_path: Path | None,
    context: str,
) -> dict[str, Any]:
    if artifact_path is None or not artifact_path.is_file():
        raise ValueError(f"{context} raw artifact is required")
    declared_digest = _validate_artifact_digest(report.get(digest_key), context)
    observed_digest = file_sha256(artifact_path)
    if observed_digest != declared_digest:
        raise ValueError(f"{context} raw artifact digest does not match the report")
    raw_evidence = _read_report(artifact_path)
    embedded_evidence = report.get(evidence_key)
    if raw_evidence != embedded_evidence:
        raise ValueError(f"{context} raw artifact does not match embedded evidence")
    if not isinstance(raw_evidence, dict):
        raise ValueError(f"{context} raw artifact must be an object")
    return raw_evidence


def _preview_exact_support(
    proof: Any,
    *,
    expected_claim_count: int,
    expected_evidence_count: int,
    context: str,
) -> bool:
    if not isinstance(proof, dict):
        raise ValueError(f"{context} must be an object")
    _require_exact_keys(proof, {"claims", "evidence"}, context=context)
    claims = proof.get("claims")
    evidence = proof.get("evidence")
    if not isinstance(claims, list) or not isinstance(evidence, list):
        raise ValueError(f"{context} claims and evidence must be lists")
    if len(claims) != expected_claim_count or len(evidence) != expected_evidence_count:
        raise ValueError(f"{context} roster differs from the response counts")

    evidence_lengths: dict[str, int] = {}
    for index, row in enumerate(evidence):
        row_context = f"{context} evidence {index}"
        if not isinstance(row, dict):
            raise ValueError(f"{row_context} must be an object")
        _require_exact_keys(
            row,
            {"evidence_id", "primary_text_sha256", "primary_text_length"},
            context=row_context,
        )
        evidence_id = _require_nonempty_string(
            row.get("evidence_id"), context=f"{row_context} evidence_id"
        )
        if evidence_id in evidence_lengths:
            raise ValueError(f"{context} evidence IDs must be unique")
        _require_digest(
            row.get("primary_text_sha256"),
            context=f"{row_context} primary-text digest",
        )
        evidence_lengths[evidence_id] = _strict_int(
            row, "primary_text_length", row_context, minimum=1
        )

    claim_ids: set[str] = set()
    for index, claim in enumerate(claims):
        claim_context = f"{context} claim {index}"
        if not isinstance(claim, dict):
            raise ValueError(f"{claim_context} must be an object")
        _require_exact_keys(claim, {"claim_id", "supports"}, context=claim_context)
        claim_id = _require_nonempty_string(
            claim.get("claim_id"), context=f"{claim_context} claim_id"
        )
        if claim_id in claim_ids:
            raise ValueError(f"{context} claim IDs must be unique")
        claim_ids.add(claim_id)
        supports = claim.get("supports")
        if not isinstance(supports, list):
            raise ValueError(f"{claim_context} supports must be a list")
        if not supports:
            return False
        for support_index, support in enumerate(supports):
            support_context = f"{claim_context} support {support_index}"
            if not isinstance(support, dict):
                raise ValueError(f"{support_context} must be an object")
            _require_exact_keys(
                support,
                {
                    "evidence_id",
                    "quote_sha256",
                    "quote_length",
                    "match_start",
                    "match_end",
                    "matched_slice_sha256",
                },
                context=support_context,
            )
            evidence_id = _require_nonempty_string(
                support.get("evidence_id"), context=f"{support_context} evidence_id"
            )
            if evidence_id not in evidence_lengths:
                raise ValueError(f"{support_context} references unknown evidence")
            quote_digest = _require_digest(
                support.get("quote_sha256"), context=f"{support_context} quote digest"
            )
            slice_digest = _require_digest(
                support.get("matched_slice_sha256"),
                context=f"{support_context} matched-slice digest",
            )
            quote_length = _strict_int(support, "quote_length", support_context, minimum=1)
            match_start = _strict_int(support, "match_start", support_context, minimum=0)
            match_end = _strict_int(support, "match_end", support_context, minimum=1)
            if quote_digest != slice_digest:
                raise ValueError(f"{support_context} quote and matched-slice digests differ")
            if match_end != match_start + quote_length:
                raise ValueError(f"{support_context} offsets differ from quote length")
            if match_end > evidence_lengths[evidence_id]:
                raise ValueError(f"{support_context} extends beyond the evidence text")
    return bool(claims) and bool(evidence)


def _preview(
    report: dict[str, Any] | None,
    *,
    raw_response_artifact: Path | None = None,
) -> dict[str, Any]:
    if report is None:
        if raw_response_artifact is not None:
            raise ValueError("preview raw response artifact requires a preview report")
        return {"status": "not_run", "qualified": None}
    _require_exact_keys(
        report,
        {
            "report_version",
            "evidence_schema_version",
            "generated_at",
            "base_url",
            "expected",
            "observed",
            "requests",
            "ask_p95_ms",
            "p95_target_ms",
            "checks",
            "qualified",
            "elapsed_seconds",
            "not_executed",
            "raw_response_artifact_sha256",
        },
        context="preview report",
    )
    if report.get("report_version") != "firelens.preview_qualification.v1":
        raise ValueError("preview report uses an unsupported report_version")
    if report.get("evidence_schema_version") != "firelens.preview_qualification.evidence.v1":
        raise ValueError("preview report raw evidence uses an unsupported schema")
    _require_timestamp(report.get("generated_at"), context="preview generated_at")
    _strict_number(report, "elapsed_seconds", "preview report", minimum=0)
    qualified = _strict_bool(report, "qualified", "preview report")
    checks = report.get("checks")
    if not isinstance(checks, dict) or not checks:
        raise ValueError("preview report has no checks")
    expected_checks = {
        "homepage_anonymous",
        "liveness",
        "readiness",
        "release_identity",
        "static_grounded",
        "unsupported_fails_closed",
        "live_metadata_complete",
        "mixed_separates_sources",
        "chat_map_records_match",
        "static_p95_within_target",
    }
    if set(checks) != expected_checks:
        raise ValueError("preview report does not contain the frozen canonical checks")
    if not all(type(value) is bool for value in checks.values()):
        raise ValueError("preview report checks must be strict booleans")
    expected = report.get("expected") or {}
    observed = report.get("observed") or {}
    if not isinstance(expected, dict) or not isinstance(observed, dict):
        raise ValueError("preview report identity blocks are invalid")
    _require_exact_keys(
        expected, {"release_version", "build_commit"}, context="preview expected identity"
    )
    _require_exact_keys(
        observed,
        {"release_version", "build_commit", "deployment_id", "rate_limit_scope"},
        context="preview observed identity",
    )
    expected_version = _require_nonempty_string(
        expected.get("release_version"), context="preview expected release version"
    )
    expected_commit = _require_nonempty_string(
        expected.get("build_commit"), context="preview expected build commit"
    )
    if len(expected_commit) != 40 or any(
        character not in "0123456789abcdef" for character in expected_commit
    ):
        raise ValueError("preview expected commit must be a full lowercase Git SHA")
    deployment_id = _require_nonempty_string(
        observed.get("deployment_id"), context="preview deployment identity"
    )
    _require_nonempty_string(
        observed.get("rate_limit_scope"), context="preview rate-limit scope"
    )
    if not str(report.get("base_url") or "").startswith("https://"):
        raise ValueError("preview qualification requires an HTTPS deployment")
    requests = report.get("requests")
    if not isinstance(requests, list) or len(requests) != 8:
        raise ValueError("preview report must contain all eight canonical requests")

    expected_protocol = [
        ("homepage", "GET", "/", {}),
        ("liveness", "GET", "/api/v1/health/live", {}),
        ("readiness", "GET", "/api/v1/health/ready", {}),
        (
            "static",
            "POST",
            "/api/v1/ask",
            {"question": "What belongs in an emergency kit?"},
        ),
        (
            "unsupported",
            "POST",
            "/api/v1/ask",
            {"question": ("What is the current air quality in Vancouver from wildfire smoke?")},
        ),
        (
            "live",
            "POST",
            "/api/v1/ask",
            {"question": "Are there active wildfires in BC currently?"},
        ),
        (
            "mixed",
            "POST",
            "/api/v1/ask",
            {
                "question": (
                    "Are there active wildfires in BC currently, and what belongs in an "
                    "emergency kit?"
                )
            },
        ),
        ("map", "GET", "/api/v1/live/map", {"layers": ["incidents"]}),
    ]
    request_keys = {
        "case_id",
        "method",
        "path",
        "request",
        "request_body_sha256",
        "status_code",
        "latency_ms",
        "response_content_type",
        "response_content_length_bytes",
        "response_body_sha256",
        "response",
    }
    rows_by_case: dict[str, dict[str, Any]] = {}
    for index, request in enumerate(requests):
        if not isinstance(request, dict):
            raise ValueError("preview request evidence must be an object")
        context = f"preview request {index}"
        _require_exact_keys(request, request_keys, context=context)
        case_id, method, path, request_payload = expected_protocol[index]
        if (
            request.get("case_id") != case_id
            or request.get("method") != method
            or request.get("path") != path
            or request.get("request") != request_payload
        ):
            raise ValueError("preview request roster differs from the canonical protocol")
        expected_body_digest = _sha256_json(request_payload) if method == "POST" else None
        if request.get("request_body_sha256") != expected_body_digest:
            raise ValueError("preview request body digest differs from the canonical payload")
        _strict_int(request, "status_code", context, minimum=100, maximum=599)
        _strict_number(request, "latency_ms", context, minimum=0)
        content_type = _require_nonempty_string(
            request.get("response_content_type"), context=f"{context} content type"
        )
        expected_content_type = "text/html" if case_id == "homepage" else "application/json"
        if expected_content_type not in content_type.casefold():
            raise ValueError(f"{context} content type differs from the canonical response")
        _strict_int(
            request,
            "response_content_length_bytes",
            context,
            minimum=0,
        )
        _require_digest(
            request.get("response_body_sha256"), context=f"{context} response-body digest"
        )
        response = request.get("response")
        if not isinstance(response, dict):
            raise ValueError(f"{context} response evidence must be an object")
        rows_by_case[case_id] = request

    homepage_response = rows_by_case["homepage"]["response"]
    _require_exact_keys(homepage_response, set(), context="preview homepage response")

    liveness_response = rows_by_case["liveness"]["response"]
    _require_exact_keys(liveness_response, {"status"}, context="preview liveness response")
    readiness_response = rows_by_case["readiness"]["response"]
    _require_exact_keys(
        readiness_response,
        {
            "status",
            "release_version",
            "build_commit",
            "deployment_id",
            "rate_limit_scope",
        },
        context="preview readiness response",
    )
    for field in ("release_version", "build_commit", "deployment_id", "rate_limit_scope"):
        if readiness_response.get(field) != observed.get(field):
            raise ValueError(f"preview observed {field} differs from readiness evidence")

    base_ask_keys = {
        "status",
        "response_mode",
        "claim_count",
        "evidence_count",
        "live_result_count",
    }
    ask_evidence: dict[str, dict[str, Any]] = {}
    exact_support: dict[str, bool] = {}
    live_rows: dict[str, list[dict[str, Any]]] = {}
    for case_id in ("static", "unsupported", "live", "mixed"):
        response = rows_by_case[case_id]["response"]
        expected_keys = set(base_ask_keys)
        if case_id in {"static", "mixed"}:
            expected_keys.add("exact_support")
        if case_id in {"live", "mixed"}:
            expected_keys.add("live_records")
        _require_exact_keys(response, expected_keys, context=f"preview {case_id} response")
        claim_count = _strict_int(
            response, "claim_count", f"preview {case_id} response", minimum=0
        )
        evidence_count = _strict_int(
            response, "evidence_count", f"preview {case_id} response", minimum=0
        )
        live_result_count = _strict_int(
            response, "live_result_count", f"preview {case_id} response", minimum=0
        )
        if case_id in {"static", "mixed"}:
            exact_support[case_id] = _preview_exact_support(
                response["exact_support"],
                expected_claim_count=claim_count,
                expected_evidence_count=evidence_count,
                context=f"preview {case_id} exact support",
            )
        if case_id in {"live", "mixed"}:
            live_rows[case_id] = _validated_public_live_rows(
                response["live_records"], context=f"preview {case_id} live records"
            )
            if live_result_count != len(live_rows[case_id]):
                raise ValueError(
                    f"preview {case_id} live-result count differs from raw records"
                )
        ask_evidence[case_id] = response

    map_response = rows_by_case["map"]["response"]
    _require_exact_keys(
        map_response, {"record_count", "records"}, context="preview map response"
    )
    map_rows = _validated_public_live_rows(
        map_response.get("records"), context="preview map records"
    )
    if _strict_int(map_response, "record_count", "preview map response", minimum=0) != len(
        map_rows
    ):
        raise ValueError("preview map record count differs from raw records")

    ask_latencies = [
        float(rows_by_case[case_id]["latency_ms"])
        for case_id in ("static", "unsupported", "live", "mixed")
    ]
    ask_p95 = _p95(ask_latencies)
    assert ask_p95 is not None
    if _strict_number(report, "ask_p95_ms", "preview report", minimum=0) != ask_p95:
        raise ValueError("preview ask p95 differs from raw request latencies")
    p95_target = _strict_number(report, "p95_target_ms", "preview report", minimum=0.0000001)

    live_pairs = {(str(row["result_id"]), str(row["status"])) for row in live_rows["live"]}
    map_pairs = {(str(row["result_id"]), str(row["status"])) for row in map_rows}
    live_metadata_complete = bool(live_rows["live"])
    mixed_metadata_complete = bool(live_rows["mixed"])
    recomputed_checks = {
        "homepage_anonymous": (
            rows_by_case["homepage"]["status_code"] == 200
            and "text/html" in str(rows_by_case["homepage"]["response_content_type"]).casefold()
        ),
        "liveness": (
            rows_by_case["liveness"]["status_code"] == 200
            and liveness_response.get("status") == "alive"
        ),
        "readiness": (
            rows_by_case["readiness"]["status_code"] == 200
            and readiness_response.get("status") == "ready"
        ),
        "release_identity": (
            readiness_response.get("release_version") == expected_version
            and readiness_response.get("build_commit") == expected_commit
        ),
        "static_grounded": (
            rows_by_case["static"]["status_code"] == 200
            and ask_evidence["static"].get("status") == "answer"
            and ask_evidence["static"].get("response_mode")
            in {"grounded", "partial", "conflict"}
            and ask_evidence["static"]["live_result_count"] == 0
            and exact_support["static"]
        ),
        "unsupported_fails_closed": (
            rows_by_case["unsupported"]["status_code"] == 200
            and ask_evidence["unsupported"].get("status") == "abstention"
            and ask_evidence["unsupported"].get("response_mode") == "abstention"
            and ask_evidence["unsupported"]["claim_count"] == 0
            and ask_evidence["unsupported"]["evidence_count"] == 0
            and ask_evidence["unsupported"]["live_result_count"] == 0
        ),
        "live_metadata_complete": (
            rows_by_case["live"]["status_code"] == 200
            and ask_evidence["live"].get("status") == "answer"
            and ask_evidence["live"].get("response_mode") == "live"
            and ask_evidence["live"]["claim_count"] == 0
            and ask_evidence["live"]["evidence_count"] == 0
            and live_metadata_complete
        ),
        "mixed_separates_sources": (
            rows_by_case["mixed"]["status_code"] == 200
            and ask_evidence["mixed"].get("status") == "answer"
            and ask_evidence["mixed"].get("response_mode") == "mixed"
            and mixed_metadata_complete
            and exact_support["mixed"]
        ),
        "chat_map_records_match": bool(live_pairs) and live_pairs.issubset(map_pairs),
        "static_p95_within_target": ask_p95 <= p95_target,
    }
    if checks != recomputed_checks:
        raise ValueError("preview checks differ from raw validated evidence")
    if qualified != all(recomputed_checks.values()):
        raise ValueError("preview qualified flag differs from raw validated evidence")
    expected_not_executed = [
        (
            "forced official-source outage requires an approved preview failure-injection "
            "mechanism"
        ),
        "screen-reader and mobile interaction require browser verification",
        "distributed firewall enforcement requires owner review and publication",
    ]
    if report.get("not_executed") != expected_not_executed:
        raise ValueError("preview not-executed roster differs from the canonical protocol")
    _validate_preview_raw_response_artifact(report, requests, raw_response_artifact)
    return {
        "status": "complete",
        "commit": expected_commit,
        "deployment_id": deployment_id,
        "qualified": qualified,
        "checks": checks,
    }


def _deployment(
    report: dict[str, Any] | None,
    *,
    rate_limit_artifact: Path | None = None,
    rollback_artifact: Path | None = None,
) -> dict[str, Any]:
    if report is None:
        if rate_limit_artifact is not None or rollback_artifact is not None:
            raise ValueError("raw deployment evidence requires a deployment report")
        return {
            "status": "not_run",
            "distributed_rate_limit_verified": None,
            "rollback_rehearsal_passed": None,
        }
    if report.get("schema_version") != "firelens_deployment_benchmark_report.v2":
        raise ValueError("deployment report uses an unsupported schema_version")
    distributed = _strict_bool(report, "distributed_rate_limit_verified", "deployment report")
    rollback = _strict_bool(report, "rollback_rehearsal_passed", "deployment report")
    if not isinstance(report.get("reviewed_by"), str) or not report["reviewed_by"].strip():
        raise ValueError("deployment report requires a named reviewer")
    if not isinstance(report.get("reviewed_at"), str) or not report["reviewed_at"].strip():
        raise ValueError("deployment report requires a review timestamp")
    rate_limit = report.get("rate_limit_evidence")
    rollback_evidence = report.get("rollback_evidence")
    candidate_deployment_id: str | None = None
    restored_deployment_id: str | None = None
    if distributed:
        rate_limit = _bind_raw_deployment_evidence(
            report=report,
            evidence_key="rate_limit_evidence",
            digest_key="rate_limit_artifact_sha256",
            artifact_path=rate_limit_artifact,
            context="distributed rate-limit proof",
        )
        if rate_limit.get("platform") != "vercel_firewall":
            raise ValueError("distributed rate-limit proof must name the platform boundary")
        candidate_deployment_id = str(rate_limit.get("candidate_deployment_id") or "").strip()
        shared_key_sha256 = str(rate_limit.get("shared_key_sha256") or "").strip()
        observations = rate_limit.get("observations")
        if not candidate_deployment_id or not str(rate_limit.get("rule_id") or "").strip():
            raise ValueError("distributed rate-limit proof is incomplete")
        if len(shared_key_sha256) != 64 or any(
            character not in "0123456789abcdef" for character in shared_key_sha256
        ):
            raise ValueError("distributed rate-limit proof requires a hashed shared test key")
        configured_limit = _strict_int(
            rate_limit, "configured_limit", "distributed rate-limit proof", minimum=1
        )
        first_rejection = _strict_int(
            rate_limit,
            "first_rejected_combined_ordinal",
            "distributed rate-limit proof",
            minimum=1,
        )
        if first_rejection > configured_limit + 1:
            raise ValueError("distributed rate limit rejected too late for its declared rule")
        if not isinstance(observations, list) or len(observations) < 2:
            raise ValueError("distributed rate-limit proof needs multiple observations")
        clients: set[str] = set()
        regions: set[str] = set()
        ordinals: set[int] = set()
        status_codes: set[int] = set()
        status_by_ordinal: dict[int, int] = {}
        for observation in observations:
            if not isinstance(observation, dict):
                raise ValueError("rate-limit observation must be an object")
            client_id = str(observation.get("client_id") or "").strip()
            region = str(observation.get("region") or "").strip()
            observed_at = str(observation.get("observed_at") or "").strip()
            if not client_id or not region or not observed_at:
                raise ValueError("rate-limit observation identity is incomplete")
            clients.add(client_id)
            regions.add(region)
            ordinal = _strict_int(
                observation, "combined_ordinal", "rate-limit observation", minimum=1
            )
            if ordinal in ordinals:
                raise ValueError("rate-limit observation ordinals must be unique")
            ordinals.add(ordinal)
            status_code = _strict_int(
                observation,
                "status_code",
                "rate-limit observation",
                minimum=100,
                maximum=599,
            )
            status_codes.add(status_code)
            status_by_ordinal[ordinal] = status_code
        if (
            len(clients) < 2
            or len(regions) < 2
            or 429 not in status_codes
            or not any(200 <= status < 300 for status in status_codes)
        ):
            raise ValueError("distributed rate-limit proof is incomplete")
        rejected_ordinals = sorted(
            ordinal for ordinal, status in status_by_ordinal.items() if status == 429
        )
        if first_rejection != rejected_ordinals[0]:
            raise ValueError(
                "distributed rate-limit proof first rejected ordinal is inconsistent"
            )
    elif (
        rate_limit_artifact is not None or report.get("rate_limit_artifact_sha256") is not None
    ):
        raise ValueError("unverified rate-limit evidence cannot be attached to the report")
    if rollback:
        rollback_evidence = _bind_raw_deployment_evidence(
            report=report,
            evidence_key="rollback_evidence",
            digest_key="rollback_artifact_sha256",
            artifact_path=rollback_artifact,
            context="rollback proof",
        )
        required = {
            "candidate_deployment_id",
            "candidate_commit",
            "restored_deployment_id",
            "restored_commit",
            "verified_at",
            "candidate_artifact_sha256",
            "restored_artifact_sha256",
        }
        if not all(str(rollback_evidence.get(key) or "").strip() for key in required):
            raise ValueError("rollback proof is incomplete")
        _validate_artifact_digest(
            rollback_evidence.get("candidate_artifact_sha256"),
            "rollback candidate artifact",
        )
        _validate_artifact_digest(
            rollback_evidence.get("restored_artifact_sha256"),
            "rollback restored artifact",
        )
        rollback_candidate_deployment_id = str(rollback_evidence["candidate_deployment_id"])
        if (
            candidate_deployment_id is not None
            and candidate_deployment_id != rollback_candidate_deployment_id
        ):
            raise ValueError("deployment proofs refer to different candidates")
        candidate_deployment_id = rollback_candidate_deployment_id
        restored_deployment_id = str(rollback_evidence["restored_deployment_id"])
        if candidate_deployment_id == restored_deployment_id:
            raise ValueError("rollback must restore a distinct deployment")
        if rollback_evidence.get("candidate_commit") != report.get("commit"):
            raise ValueError("rollback proof candidate commit does not match the report")
        if rollback_evidence.get("restored_commit") == report.get("commit"):
            raise ValueError("rollback proof did not restore a prior commit")
        _require_environment_snapshot(
            rollback_evidence.get("candidate_environment_snapshot"),
            commit=str(rollback_evidence["candidate_commit"]),
            context="rollback candidate",
        )
        _require_environment_snapshot(
            rollback_evidence.get("restored_environment_snapshot"),
            commit=str(rollback_evidence["restored_commit"]),
            context="rollback restored",
        )
        rollback_checks = rollback_evidence.get("checks")
        expected_rollback_checks = {
            "readiness_restored",
            "homepage_anonymous",
            "release_identity_restored",
            "environment_snapshot_restored",
            "grounded_smoke_passed",
            "live_smoke_passed",
        }
        if (
            not isinstance(rollback_checks, dict)
            or set(rollback_checks) != expected_rollback_checks
            or not all(value is True for value in rollback_checks.values())
        ):
            raise ValueError("rollback proof lacks the canonical restored-state checks")
    elif rollback_artifact is not None or report.get("rollback_artifact_sha256") is not None:
        raise ValueError("unverified rollback evidence cannot be attached to the report")
    return {
        "status": "complete",
        "label": report.get("label"),
        "commit": report.get("commit"),
        "distributed_rate_limit_verified": distributed,
        "rollback_rehearsal_passed": rollback,
        "candidate_deployment_id": candidate_deployment_id,
        "restored_deployment_id": restored_deployment_id,
        "rate_limit_artifact_sha256": report.get("rate_limit_artifact_sha256"),
        "rollback_artifact_sha256": report.get("rollback_artifact_sha256"),
        "notes": report.get("notes") or "",
    }


def _write_ux_template(path: Path, label: str, spec: BenchmarkSpec) -> None:
    if path.exists():
        return
    participants = []
    for index in range(12):
        device_class = "desktop" if index % 2 == 0 else "mobile"
        if index == 0:
            access_method = "keyboard"
        elif index == 1:
            access_method = "screen_reader"
        else:
            access_method = "pointer" if device_class == "desktop" else "touch"
        participants.append(
            {
                "participant_id": f"P{index + 1:02d}",
                "cohort": "novice_bc_resident" if index < 6 else "wildfire_aware",
                "device_class": device_class,
                "access_methods": [access_method],
            }
        )
    attempts = []
    for participant in participants:
        for task in spec.ux_tasks:
            attempt: dict[str, Any] = {
                "participant_id": participant["participant_id"],
                "task_id": task.id,
                "criterion_results": {
                    criterion.id: None for criterion in task.completion_criteria
                },
                "critical_error_codes": [],
                "critical_error_notes": {},
                "duration_seconds": None,
                "seq_score": None,
                "confidence": None,
                "observed_outcome": "",
            }
            attempts.append(attempt)
    payload: dict[str, Any] = {
        "schema_version": "firelens_ux_benchmark_report.v3",
        "label": label,
        "protocol_id": spec.benchmark_id,
        "commit": None,
        "deployment_id": None,
        "moderator": None,
        "observed_at": None,
        "participant_count": len(participants),
        "recruitment_constraint": (
            "Recruit twelve independent participants under the frozen cohort, device, and "
            "access-method allocation; replace IDs only with pseudonymous identifiers."
        ),
        "participants": participants,
        "attempts": attempts,
        "task_reference": [task.model_dump() for task in spec.ux_tasks],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _write_deployment_template(path: Path, label: str) -> None:
    if path.exists():
        return
    payload: dict[str, Any] = {
        "schema_version": "firelens_deployment_benchmark_report.v2",
        "label": label,
        "commit": None,
        "reviewed_by": None,
        "reviewed_at": None,
        "distributed_rate_limit_verified": None,
        "rollback_rehearsal_passed": None,
        "rate_limit_artifact_sha256": None,
        "rollback_artifact_sha256": None,
        "rate_limit_evidence": {
            "platform": "vercel_firewall",
            "rule_id": None,
            "candidate_deployment_id": None,
            "shared_key_sha256": None,
            "configured_limit": None,
            "first_rejected_combined_ordinal": None,
            "observations": [],
        },
        "rollback_evidence": _blank_rollback_evidence(),
        "notes": "",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
