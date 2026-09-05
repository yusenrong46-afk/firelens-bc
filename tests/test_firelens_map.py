from __future__ import annotations

import json
from pathlib import Path

import yaml

from scripts.firelens_agent.build_map import OUTPUT_NAMES, build_artifacts
from scripts.firelens_agent.docs_drift import architecture_size_findings
from scripts.firelens_agent.impact import OWNERSHIP, analyze_impact
from scripts.firelens_agent.trace_case import build_trace
from scripts.firelens_agent.validate_map import validate_repository_map

ROOT = Path(__file__).resolve().parents[1]


def test_repository_map_build_is_deterministic_and_cross_referenced() -> None:
    first = build_artifacts(ROOT)
    second = build_artifacts(ROOT)
    assert first == second
    assert tuple(first) == OUTPUT_NAMES
    command_prefix = "PYTHONPATH=src:tests .venv/bin/python scripts/firelens_agent/"
    for command in ("build_map.py", "validate_map.py", "impact.py", "trace_case.py"):
        assert command_prefix + command in first["README.md"]
    assert "`python scripts/firelens_agent/" not in first["README.md"]
    assert "`python " not in first["request-lifecycle.md"]

    modules = json.loads(first["module-index.json"])
    symbols = json.loads(first["symbol-index.json"])
    graph = json.loads(first["import-graph.json"])
    semantic = yaml.safe_load(first["ownership.yaml"])
    digest = modules["source_digest"]
    assert len(digest) == 64
    assert "fastapi==0.140.0" in modules["dependencies"]["python"]
    assert "dev" in modules["dependencies"]["python_optional"]
    assert "POST /api/v1/ask" in modules["endpoints"]
    assert symbols["source_digest"] == digest
    assert graph["source_digest"] == digest
    assert semantic["source_digest"] == digest
    assert semantic["schema_version"] == "firelens.ownership.v1"
    assert semantic["domains"][0]["duplicates"] == []

    by_path = {item["path"]: item for item in modules["modules"]}
    assert by_path["apps/web/worker/index.js"]["language"] == "javascript"
    query_plan = by_path["src/firelens/agent/query_plan.py"]
    assert query_plan["module"] == "firelens.agent.query_plan"
    assert query_plan["production_fan_in"] > 0
    assert not query_plan["statically_unreferenced"]
    assert any(item["name"] == "AgentQueryPlan" for item in symbols["symbols"])
    assert len({item["id"] for item in symbols["symbols"]}) == len(symbols["symbols"])
    assert len({(item["source"], item["target"]) for item in graph["edges"]}) == len(
        graph["edges"]
    )


def test_checked_in_repository_map_is_current() -> None:
    assert validate_repository_map(ROOT) == []


def test_symbol_impact_finds_authority_callers_and_tests() -> None:
    result = analyze_impact("AgentQueryPlan", ROOT)
    assert result["changed"] == ["src/firelens/agent/query_plan.py"]
    assert {item["id"] for item in result["owners"]} == {"query_authority"}
    assert result["direct_callers"]
    assert any(item["path"] == "tests/test_agent_query_plan.py" for item in result["tests"])
    assert result["complexity"][0]["production_fan_in"] > 0
    location = analyze_impact("location_resolution", ROOT)
    assert location["changed"] == ["src/firelens/live_support.py"]
    assert {item["id"] for item in location["owners"]} == {"location_resolution"}
    place_owner = next(item for item in OWNERSHIP if item["id"] == "place_recognition")
    assert "src/firelens/understanding/place_vocabulary.py" in place_owner["projections"]
    for owner in OWNERSHIP:
        result = analyze_impact(owner["id"], ROOT)
        assert result["changed"]
        assert owner["id"] in {item["id"] for item in result["owners"]}


def test_case_trace_executes_only_deterministic_planning() -> None:
    trace = build_trace("Show active fires near Kelowna", root=ROOT)
    assert trace["execution_mode"] == "planning_only_offline"
    assert trace["network_calls"] == 0
    assert trace["provider_calls"] == 0
    assert trace["planning"]["mode"] == "live"
    assert trace["planning"]["tool_calls"] == [
        {"name": "list_official_fires", "arguments": {"place_label": "[redacted]"}}
    ]
    assert trace["planning"]["location_label"] == "[redacted]"
    assert "Kelowna" not in json.dumps(trace)
    assert "question" not in trace
    assert trace["map_source_digest"]


def test_architecture_size_drift_reports_documented_and_actual_loc(
    tmp_path: Path,
) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "src/firelens").mkdir(parents=True)
    (tmp_path / "src/firelens/example.py").write_text("one\ntwo\n", encoding="utf-8")
    (tmp_path / "docs/ARCHITECTURE_V1_6.md").write_text(
        "| Module | Baseline | Current | Note |\n"
        "| --- | --- | --- | --- |\n"
        "| `src/firelens/example.py` | 1 | 1 | stale |\n",
        encoding="utf-8",
    )
    assert architecture_size_findings(tmp_path) == [
        "documented LOC drift: src/firelens/example.py says 1, actual 2"
    ]
