from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import scripts.upgrade_benchmark as upgrade_benchmark


def _preview_report() -> dict:
    commit = "a" * 40
    version = "1.5.2"
    generated_at = "2026-08-06T10:00:00+00:00"
    quote = "Keep water"
    primary_text = "Keep water in an emergency kit."
    quote_digest = hashlib.sha256(quote.encode("utf-8")).hexdigest()

    def support_proof() -> dict:
        return {
            "claims": [
                {
                    "claim_id": "C1",
                    "supports": [
                        {
                            "evidence_id": "E1",
                            "quote_sha256": quote_digest,
                            "quote_length": len(quote),
                            "match_start": 0,
                            "match_end": len(quote),
                            "matched_slice_sha256": quote_digest,
                        }
                    ],
                }
            ],
            "evidence": [
                {
                    "evidence_id": "E1",
                    "primary_text_sha256": hashlib.sha256(
                        primary_text.encode("utf-8")
                    ).hexdigest(),
                    "primary_text_length": len(primary_text),
                }
            ],
        }

    live_record = {
        "result_id": "incident:1",
        "kind": "incident",
        "authority": "BC Wildfire Service",
        "source_url": "https://official.example.test/incident",
        "source_updated_at": generated_at,
        "retrieved_at": generated_at,
        "status": "Active",
    }
    perimeter_record = {
        "result_id": "perimeter:1",
        "kind": "perimeter",
        "authority": "BC Wildfire Service",
        "source_url": "https://official.example.test/perimeter",
        "source_updated_at": generated_at,
        "retrieved_at": generated_at,
        "status": "Active",
    }
    live_records = [live_record, perimeter_record]
    protocol = [
        ("homepage", "GET", "/", {}, {}),
        ("liveness", "GET", "/api/v1/health/live", {}, {"status": "alive"}),
        (
            "readiness",
            "GET",
            "/api/v1/health/ready",
            {},
            {
                "status": "ready",
                "release_version": version,
                "build_commit": commit,
                "deployment_id": "preview-1",
                "rate_limit_scope": "instance_local",
            },
        ),
        (
            "static",
            "POST",
            "/api/v1/ask",
            {"question": "What belongs in an emergency kit?"},
            {
                "status": "answer",
                "response_mode": "grounded",
                "claim_count": 1,
                "evidence_count": 1,
                "live_result_count": 0,
                "exact_support": support_proof(),
            },
        ),
        (
            "unsupported",
            "POST",
            "/api/v1/ask",
            {"question": ("What is the current air quality in Vancouver from wildfire smoke?")},
            {
                "status": "answer",
                "response_mode": "scope_redirect",
                "claim_count": 0,
                "evidence_count": 0,
                "live_result_count": 0,
            },
        ),
        (
            "live",
            "POST",
            "/api/v1/ask",
            {"question": "Are there active wildfires in BC currently?"},
            {
                "status": "answer",
                "response_mode": "live",
                "claim_count": 0,
                "evidence_count": 0,
                "live_result_count": 2,
                "live_records": live_records,
            },
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
            {
                "status": "answer",
                "response_mode": "mixed",
                "claim_count": 1,
                "evidence_count": 1,
                "live_result_count": 2,
                "exact_support": support_proof(),
                "live_records": live_records,
            },
        ),
        (
            "map",
            "GET",
            "/api/v1/live/map",
            {"layers": ["incidents", "perimeters"]},
            {"record_count": 2, "records": live_records},
        ),
    ]
    requests = []
    for case_id, method, path, request_payload, response in protocol:
        response_payload = json.dumps(response, separators=(",", ":"), sort_keys=True)
        requests.append(
            {
                "case_id": case_id,
                "method": method,
                "path": path,
                "request": request_payload,
                "request_body_sha256": (
                    upgrade_benchmark._sha256_json(request_payload)
                    if method == "POST"
                    else None
                ),
                "status_code": 200,
                "latency_ms": 10.0,
                "response_content_type": (
                    "text/html; charset=utf-8" if case_id == "homepage" else "application/json"
                ),
                "response_content_length_bytes": len(response_payload.encode("utf-8")),
                "response_body_sha256": hashlib.sha256(
                    response_payload.encode("utf-8")
                ).hexdigest(),
                "response": response,
            }
        )
    checks = {
        "homepage_anonymous": True,
        "liveness": True,
        "readiness": True,
        "release_identity": True,
        "static_grounded": True,
        "unsupported_fails_closed": True,
        "live_metadata_complete": True,
        "mixed_separates_sources": True,
        "chat_map_records_match": True,
        "static_p95_within_target": True,
    }
    return {
        "report_version": "firelens.preview_qualification.v1",
        "evidence_schema_version": "firelens.preview_qualification.evidence.v1",
        "generated_at": generated_at,
        "base_url": "https://preview.example.test",
        "expected": {"release_version": version, "build_commit": commit},
        "observed": {
            "release_version": version,
            "build_commit": commit,
            "deployment_id": "preview-1",
            "rate_limit_scope": "instance_local",
        },
        "requests": requests,
        "ask_p95_ms": 10.0,
        "p95_target_ms": 4_000.0,
        "checks": checks,
        "qualified": True,
        "elapsed_seconds": 1.0,
        "not_executed": [
            (
                "forced official-source outage requires an approved preview failure-injection "
                "mechanism"
            ),
            "screen-reader and mobile interaction require browser verification",
            "distributed firewall enforcement requires owner review and publication",
        ],
        "raw_response_artifact_sha256": "0" * 64,
    }


def _write_preview_raw_artifact(report: dict, path: Path) -> Path:
    rows = []
    for request in report["requests"]:
        case_id = request["case_id"]
        retained = request["response"]
        if case_id == "homepage":
            raw_response: dict | str = "<html>FireLens</html>"
        elif case_id in {"liveness", "readiness"}:
            raw_response = retained
        elif case_id == "map":
            raw_response = {"results": retained["records"]}
        else:
            raw_response = {
                "status": retained["status"],
                "response_mode": retained["response_mode"],
                "claims": [],
                "evidence": [],
                "live_results": retained.get("live_records", []),
            }
            if case_id in {"static", "mixed"}:
                raw_response["claims"] = [
                    {
                        "claim_id": "C1",
                        "supports": [{"evidence_id": "E1", "quote": "Keep water"}],
                    }
                ]
                raw_response["evidence"] = [
                    {
                        "evidence_id": "E1",
                        "primary_text": "Keep water in an emergency kit.",
                    }
                ]
        body = (
            raw_response.encode("utf-8")
            if isinstance(raw_response, str)
            else json.dumps(raw_response, separators=(",", ":"), sort_keys=True).encode("utf-8")
        )
        request["response_content_length_bytes"] = len(body)
        request["response_body_sha256"] = hashlib.sha256(body).hexdigest()
        rows.append(
            {
                "case_id": request["case_id"],
                "response_body_base64": base64.b64encode(body).decode("ascii"),
                "retained_response_sha256": hashlib.sha256(
                    json.dumps(
                        retained,
                        separators=(",", ":"),
                        sort_keys=True,
                    ).encode("utf-8")
                ).hexdigest(),
            }
        )
    payload = {
        "artifact_version": "firelens.preview_raw_response_artifact.v1",
        "requests": rows,
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)
    report["raw_response_artifact_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    return path


__all__ = [name for name in globals() if not name.startswith("__")]
