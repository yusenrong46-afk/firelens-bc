from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

import httpx
import pytest

from scripts.prepare_vercel_firewall import load_plan, render_command
from scripts.qualify_preview import qualify_preview


def test_firewall_plan_is_enforced_method_scoped_and_not_auto_published() -> None:
    root = Path(__file__).resolve().parents[1]
    plan = load_plan(root / "config/vercel_firewall.v1.json")

    assert {(rule["path"], rule["method"]) for rule in plan["rules"]} == {
        ("/api/v1/ask", "POST"),
        ("/api/v1/live/map", "GET"),
    }
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


def test_preview_qualification_requires_identity_evidence_and_exact_support() -> None:
    evidence = {
        "evidence_id": "E1",
        "primary_text": "Keep water in an emergency kit.",
    }
    claim = {
        "claim_id": "C1",
        "text": "Keep water in the kit.",
        "supports": [{"evidence_id": "E1", "quote": "Keep water"}],
    }
    live_result = {
        "result_id": "incident:1",
        "authority": "BC Wildfire Service",
        "source_url": "https://example.test/source",
        "source_updated_at": "2026-07-29T00:00:00Z",
        "retrieved_at": "2026-07-29T00:01:00Z",
        "status": "Out of Control",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/":
            return httpx.Response(
                200, text="<html></html>", headers={"content-type": "text/html"}
            )
        if request.url.path.endswith("/health/live"):
            return httpx.Response(200, json={"status": "alive"})
        if request.url.path.endswith("/health/ready"):
            return httpx.Response(
                200,
                json={
                    "status": "ready",
                    "release_version": "1.5.0-rc.1",
                    "build_commit": "abc123",
                    "deployment_id": "preview-1",
                    "rate_limit_scope": "instance_local",
                },
            )
        if request.url.path.endswith("/live/map"):
            return httpx.Response(200, json={"results": [live_result]})
        question = json.loads(request.content)["question"]
        if "air quality" in question:
            return httpx.Response(
                200,
                json={"status": "abstention", "response_mode": "abstention", "claims": []},
            )
        if "active wildfires" in question and "emergency kit" in question:
            return httpx.Response(
                200,
                json={
                    "status": "answer",
                    "response_mode": "mixed",
                    "claims": [claim],
                    "evidence": [evidence],
                    "live_results": [live_result],
                },
            )
        if "active wildfires" in question:
            return httpx.Response(
                200,
                json={
                    "status": "answer",
                    "response_mode": "live",
                    "live_results": [live_result],
                },
            )
        return httpx.Response(
            200,
            json={
                "status": "answer",
                "response_mode": "grounded",
                "claims": [claim],
                "evidence": [evidence],
            },
        )

    report = asyncio.run(
        qualify_preview(
            base_url="https://preview.example.test",
            expected_version="1.5.0-rc.1",
            expected_commit="abc123",
            p95_target_ms=4_000,
            transport=httpx.MockTransport(handler),
        )
    )

    assert report["qualified"] is True
    assert all(report["checks"].values())
    assert report["observed"]["deployment_id"] == "preview-1"
