from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import tempfile
from pathlib import Path

import httpx
import pytest

from firelens.api.middleware import _GUARDED_ROUTES
from scripts.prepare_vercel_firewall import load_plan, render_command
from scripts.qualify_preview import (
    _assert_no_sensitive_retained_fields,
    _assert_safe_retained_preview_report,
    qualify_preview,
)
from scripts.upgrade_benchmark import _preview


def test_firewall_plan_is_enforced_method_scoped_and_not_auto_published() -> None:
    root = Path(__file__).resolve().parents[1]
    plan = load_plan(root / "config/vercel_firewall.v1.json")

    assert {(rule["path"], rule["method"]) for rule in plan["rules"]} == {
        ("/api/v1/ask", "POST"),
        ("/api/v1/feedback", "POST"),
        ("/api/v1/live/map", "GET"),
        ("/api/v1/live/nearby", "POST"),
    }
    assert {rule["path"] for rule in plan["rules"]} == _GUARDED_ROUTES
    for rule in plan["rules"]:
        command = render_command(rule)
        assert command[-2:] == ["--rate-limit-action", "deny"]
        assert "--condition" in command
        assert "--yes" not in command


def test_firewall_plan_rejects_log_only_rules() -> None:
    payload = {
        "schema_version": "firelens.vercel_firewall.v1",
        "observation_period_hours": 24,
        "rules": [
            {
                "name": "observation-only",
                "path": "/api/v1/ask",
                "method": "POST",
                "window_seconds": 60,
                "requests": 150,
                "keys": ["ip"],
                "rate_limit_action": "log",
            }
        ],
    }
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "plan.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(ValueError, match="enforced"):
            load_plan(path)


def test_firewall_plan_rejects_missing_guarded_routes(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    payload = json.loads((root / "config/vercel_firewall.v1.json").read_text())
    payload["rules"] = payload["rules"][:-1]
    path = tmp_path / "incomplete-plan.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="every guarded public route"):
        load_plan(path)


def test_preview_qualification_requires_identity_evidence_and_exact_support(
    tmp_path: Path,
) -> None:
    commit = "a" * 40
    answer_canary = "CANARY_ANSWER_PLAINTEXT_MUST_NOT_SURVIVE_7F91"
    source_canary = "CANARY_SOURCE_PASSAGE_MUST_NOT_SURVIVE_4C22"
    private_header_canary = "CANARY_PRIVATE_HEADER_MUST_NOT_SURVIVE_8D03"
    latitude_canary = 49.987654321
    longitude_canary = -123.123456789
    primary_text = f"Keep water in an emergency kit. {source_canary}"
    evidence = {
        "evidence_id": "E1",
        "primary_text": primary_text,
    }
    claim = {
        "claim_id": "C1",
        "text": "Keep water in the kit.",
        "supports": [{"evidence_id": "E1", "quote": "Keep water"}],
    }
    live_result = {
        "result_id": "incident:1",
        "kind": "incident",
        "authority": "BC Wildfire Service",
        "source_url": (
            "https://example.test/source?latitude="
            f"{latitude_canary}&private={private_header_canary}"
        ),
        "source_updated_at": "2026-07-29T00:00:00Z",
        "retrieved_at": "2026-07-29T00:01:00Z",
        "status": "Out of Control",
        "latitude": latitude_canary,
        "longitude": longitude_canary,
        "geometry": {
            "type": "Point",
            "coordinates": [longitude_canary, latitude_canary],
        },
    }
    raw_response_digests: list[str] = []

    def retained(response: httpx.Response) -> httpx.Response:
        raw_response_digests.append(hashlib.sha256(response.content).hexdigest())
        return response

    def json_response(payload: dict) -> httpx.Response:
        return retained(
            httpx.Response(
                200,
                json=payload,
                headers={"x-preview-private-canary": private_header_canary},
            )
        )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/":
            return retained(
                httpx.Response(
                    200,
                    text=f"<html>{answer_canary}</html>",
                    headers={
                        "content-type": "text/html; charset=utf-8",
                        "x-preview-private-canary": private_header_canary,
                    },
                )
            )
        if request.url.path.endswith("/health/live"):
            return json_response({"status": "alive"})
        if request.url.path.endswith("/health/ready"):
            return json_response(
                {
                    "status": "ready",
                    "release_version": "1.5.0-rc.1",
                    "build_commit": commit,
                    "deployment_id": "preview-1",
                    "rate_limit_scope": "instance_local",
                    "private_header_echo": private_header_canary,
                },
            )
        if request.url.path.endswith("/live/map"):
            return json_response({"results": [live_result]})
        question = json.loads(request.content)["question"]
        if "air quality" in question:
            return json_response(
                {
                    "status": "answer",
                    "response_mode": "scope_redirect",
                    "answer": answer_canary,
                    "claims": [],
                }
            )
        if "active wildfires" in question and "emergency kit" in question:
            return json_response(
                {
                    "status": "answer",
                    "response_mode": "mixed",
                    "answer": answer_canary,
                    "claims": [claim],
                    "evidence": [evidence],
                    "live_results": [live_result],
                },
            )
        if "active wildfires" in question:
            return json_response(
                {
                    "status": "answer",
                    "response_mode": "live",
                    "answer": answer_canary,
                    "live_results": [live_result],
                },
            )
        return json_response(
            {
                "status": "answer",
                "response_mode": "grounded",
                "answer": answer_canary,
                "claims": [claim],
                "evidence": [evidence],
            },
        )

    raw_artifact = tmp_path / "preview-raw.json"
    report = asyncio.run(
        qualify_preview(
            base_url="https://preview.example.test",
            expected_version="1.5.0-rc.1",
            expected_commit=commit,
            p95_target_ms=4_000,
            raw_response_artifact_path=raw_artifact,
            transport=httpx.MockTransport(handler),
        )
    )

    assert report["qualified"] is True
    assert all(report["checks"].values())
    assert report["observed"]["deployment_id"] == "preview-1"
    assert report["evidence_schema_version"] == "firelens.preview_qualification.evidence.v1"

    requests = {row["case_id"]: row for row in report["requests"]}
    assert set(requests) == {
        "homepage",
        "liveness",
        "readiness",
        "static",
        "unsupported",
        "live",
        "mixed",
        "map",
    }
    assert requests["static"]["request"] == {"question": "What belongs in an emergency kit?"}
    assert requests["map"]["request"] == {"layers": ["incidents", "perimeters"]}
    assert [row["response_body_sha256"] for row in report["requests"]] == raw_response_digests
    assert [row["response_content_type"] for row in report["requests"]] == [
        "text/html",
        *("application/json" for _ in range(7)),
    ]

    support = requests["static"]["response"]["exact_support"]
    assert support["evidence"] == [
        {
            "evidence_id": "E1",
            "primary_text_sha256": support["evidence"][0]["primary_text_sha256"],
            "primary_text_length": len(primary_text),
        }
    ]
    proof = support["claims"][0]["supports"][0]
    assert proof["match_start"] == 0
    assert proof["match_end"] == len("Keep water")
    assert proof["quote_sha256"] == proof["matched_slice_sha256"]
    assert (
        support["evidence"][0]["primary_text_sha256"]
        == hashlib.sha256(primary_text.encode("utf-8")).hexdigest()
    )
    assert "primary_text" not in support["evidence"][0]
    assert "answer" not in requests["static"]["response"]

    expected_public_record = {
        key: live_result[key]
        for key in (
            "result_id",
            "kind",
            "authority",
            "source_url",
            "source_updated_at",
            "retrieved_at",
            "status",
        )
    }
    expected_public_record["source_url"] = "https://example.test/source"
    assert requests["live"]["response"]["live_records"] == [expected_public_record]
    assert (
        requests["map"]["response"]["records"] == requests["live"]["response"]["live_records"]
    )
    serialized = json.dumps(report, ensure_ascii=False, sort_keys=True)
    for canary in (
        answer_canary,
        source_canary,
        private_header_canary,
        str(latitude_canary),
        str(longitude_canary),
    ):
        assert canary not in serialized
    for forbidden_key in (
        '"answer":',
        '"primary_text":',
        '"geometry":',
        '"coordinates":',
        '"latitude":',
        '"longitude":',
        '"headers":',
    ):
        assert forbidden_key not in serialized
    assert raw_artifact.stat().st_mode & 0o777 == 0o600
    assert _preview(report, raw_response_artifact=raw_artifact)["qualified"] is True

    mutated = copy.deepcopy(report)
    mutated["requests"][3]["response"]["answer"] = answer_canary
    with pytest.raises(ValueError, match="retained-evidence schema|forbidden retained"):
        _assert_safe_retained_preview_report(mutated)


@pytest.mark.parametrize(
    "payload",
    [
        {"answer": "SYNTHETIC_SECRET"},
        {"primary_text": "SYNTHETIC_SOURCE_PASSAGE"},
        {"headers": {"x-private": "SYNTHETIC_HEADER"}},
        {"geometry": {"coordinates": [-123.123456789, 49.987654321]}},
        {"latitude": 49.987654321, "longitude": -123.123456789},
        {"response_body": "SYNTHETIC_RAW_BODY"},
    ],
)
def test_preview_retention_guard_rejects_sensitive_field_mutations(payload: dict) -> None:
    with pytest.raises(ValueError, match="forbidden retained field"):
        _assert_no_sensitive_retained_fields(payload)
