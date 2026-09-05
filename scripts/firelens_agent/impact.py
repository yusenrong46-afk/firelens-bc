#!/usr/bin/env python3
"""Report deterministic callers, owners, tests, evaluations, and complexity impact."""

import argparse
import json
from collections import deque
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
OWNERSHIP: tuple[dict[str, Any], ...] = (
    {
        "id": "request_understanding",
        "primary": ["src/firelens/answering/intent_automaton.py"],
        "projections": ["src/firelens/answering/request_grammar.py"],
        "duplicates": [],
    },
    {
        "id": "place_recognition",
        "primary": ["src/firelens/understanding/place.py"],
        "projections": "src/firelens/understanding/place_vocabulary.py src/firelens/answering/location_intent.py".split(),
        "duplicates": [],
    },
    {
        "id": "location_resolution",
        "primary": ["src/firelens/live_support.py"],
        "projections": ["src/firelens/live.py"],
        "duplicates": [],
    },
    {
        "id": "query_authority",
        "primary": ["src/firelens/agent/query_plan.py"],
        "projections": ["src/firelens/agent/runtime_tools.py"],
        "duplicates": ["src/firelens/agent/fallback_brain.py"],
        "note": "AgentQueryPlan alone authorizes tools, layers, geography, and static scope.",
    },
    {
        "id": "ask_orchestration",
        "primary": ["src/firelens/agent/coordinator.py"],
        "projections": ["src/firelens/agent/loop.py", "src/firelens/agent/compose.py"],
        "duplicates": ["src/firelens/live_answering.py"],
        "note": "Public Ask uses FireLensAgent; LiveAnswerCoordinator.answer is legacy.",
    },
    {
        "id": "static_rag",
        "primary": ["src/firelens/answering/service.py"],
        "projections": ["src/firelens/retrieval/pipeline.py"],
        "duplicates": [],
    },
    {
        "id": "official_live",
        "primary": ["src/firelens/live.py"],
        "projections": ["src/firelens/live_contracts.py", "src/firelens/live_identity.py"],
        "duplicates": [],
    },
    {
        "id": "publication",
        "primary": ["src/firelens/publication/compiler.py"],
        "projections": ["src/firelens/publication/compiled_validation.py"],
        "duplicates": ["src/firelens/publication/risk.py"],
    },
    {
        "id": "proof_presentation",
        "primary": ["src/firelens/proof_presentation.py"],
        "projections": ["apps/web/src/features/ask/proofPresentation.ts"],
        "duplicates": ["apps/web/src/features/ask/proofPresentation.ts"],
    },
    {
        "id": "api_contract",
        "primary": ["src/firelens/contracts.py", "src/firelens/api_contracts.py"],
        "projections": ["docs/openapi.v1.json", "apps/web/src/shared/api/api-schema.d.ts"],
        "duplicates": ["apps/web/src/shared/api/api.ts"],
        "note": "Backend models own wire shapes; generated OpenAPI/types are projections.",
    },
    {
        "id": "provider_boundary",
        "primary": ["src/firelens/providers/openrouter.py"],
        "projections": ["src/firelens/privacy_policy.py"],
        "duplicates": [],
    },
    {
        "id": "http_api",
        "primary": ["src/firelens/api/factory.py"],
        "projections": [
            "src/firelens/api/answer_routes.py",
            "src/firelens/api/live_routes.py",
        ],
        "duplicates": [],
    },
)
INVARIANTS: tuple[dict[str, Any], ...] = (
    {
        "id": "PLAN-001",
        "owner": "query_authority",
        "severity": "critical",
        "statement": "Only AgentQueryPlan may authorize tools, layers, geography, and scope.",
        "tests": ["tests/test_agent_query_plan.py", "tests/test_agent_query_plan_boundary.py"],
    },
    {
        "id": "PUB-001",
        "owner": "publication",
        "severity": "critical",
        "statement": "Tier A/B facts require structured or exact-source publication.",
        "tests": ["tests/test_structured_publication_architecture.py"],
    },
    {
        "id": "PROOF-001",
        "owner": "proof_presentation",
        "severity": "critical",
        "statement": "Proof presentation never strengthens missing or rejected authority.",
        "tests": [
            "tests/test_proof_presentation.py",
            "tests/test_public_contract_publication.py",
        ],
    },
    {
        "id": "LIVE-001",
        "owner": "official_live",
        "severity": "critical",
        "statement": "Empty, stale, partial, or unavailable records never imply all-clear.",
        "tests": ["tests/test_empty_live_safety.py", "tests/test_live_prose_binding.py"],
    },
    {
        "id": "RET-001",
        "owner": "static_rag",
        "severity": "high",
        "statement": "Incomplete retrieval is never represented as complete support.",
        "tests": ["tests/test_static_rag.py", "tests/test_source_requirement_precedence.py"],
    },
    {
        "id": "PRIV-001",
        "owner": "provider_boundary",
        "severity": "critical",
        "statement": "Production uses OpenRouter deny-collection with fallback disabled.",
        "tests": ["tests/test_api_privacy_boundary.py", "tests/test_stage_privacy_policy.py"],
    },
    {
        "id": "SAFETY-001",
        "owner": "query_authority",
        "severity": "critical",
        "statement": "Personalized safety decisions require authority or explicit refusal.",
        "tests": ["tests/test_productbench_scope_safety.py"],
    },
)
CAPABILITIES: tuple[dict[str, Any], ...] = (
    {
        "id": "reviewed_guidance",
        "endpoint": "POST /api/v1/ask",
        "owner": "static_rag",
        "fallback": "labelled Tier-C background, exact quote, handoff, or abstention",
    },
    {
        "id": "current_official_records",
        "endpoint": "POST /api/v1/ask",
        "owner": "official_live",
        "fallback": "typed unavailable or official handoff",
    },
    {
        "id": "nearby_official_records",
        "endpoint": "POST /api/v1/live/nearby",
        "owner": "location_resolution",
        "fallback": "typed location or upstream failure",
    },
    {
        "id": "official_map",
        "endpoint": "GET /api/v1/live/map",
        "owner": "official_live",
        "fallback": "record list remains usable when tiles fail",
    },
    {
        "id": "proof_cards",
        "endpoint": "POST /api/v1/ask",
        "owner": "proof_presentation",
        "fallback": "fail closed to unknown support",
    },
    {
        "id": "guided_questions",
        "endpoint": "GET /api/v1/guided-questions",
        "owner": "http_api",
        "fallback": "client retry without inferred capability",
    },
)


def _load(root: Path) -> tuple[dict[str, Any], ...]:
    directory = root / "docs/firelens-map"
    names = ("module-index.json", "symbol-index.json", "import-graph.json", "test-map.json")
    return tuple(json.loads((directory / name).read_text(encoding="utf-8")) for name in names)


def analyze_impact(query: str, root: Path = ROOT) -> dict[str, Any]:
    modules, symbols, graph, tests = _load(root)
    normalized = {item["id"]: item["primary"][0] for item in OWNERSHIP}.get(query, query)
    normalized = normalized.replace("\\", "/").lstrip("./")
    changed = {
        item["path"]
        for item in modules["modules"]
        if normalized in {item["path"], item["module"]} or item["path"].endswith(normalized)
    }
    changed.update(
        item["module_path"]
        for item in symbols["symbols"]
        if normalized in {item["id"], item["name"], item["qualname"]}
    )
    if not changed:
        raise ValueError(f"no mapped file or symbol matches {query!r}")
    reverse: dict[str, set[str]] = {}
    for edge in graph["edges"]:
        reverse.setdefault(edge["target"], set()).add(edge["source"])
    distance = {path: 0 for path in changed}
    queue = deque(sorted(changed))
    while queue:
        target = queue.popleft()
        if distance[target] >= 4:
            continue
        for caller in sorted(reverse.get(target, ())):
            if caller not in distance:
                distance[caller] = distance[target] + 1
                queue.append(caller)
    production = {item["path"] for item in modules["modules"] if item["kind"] != "test"}
    owners = [
        item
        for item in OWNERSHIP
        if changed.intersection(item["primary"] + item["projections"] + item["duplicates"])
    ]
    owner_ids = {item["id"] for item in owners}
    impacted_tests = []
    for test in tests["tests"]:
        target_distances = [
            distance[target] + 1 for target in test["direct_targets"] if target in distance
        ]
        if test["path"] in distance or target_distances:
            impacted_tests.append(
                {
                    "path": test["path"],
                    "distance": min(target_distances, default=distance.get(test["path"], 0)),
                    "evaluation_families": test["evaluation_families"],
                }
            )
    families = {family for test in impacted_tests for family in test["evaluation_families"]}
    return {
        "schema_version": "firelens.impact.v1",
        "changed": sorted(changed),
        "owners": owners,
        "invariants": [item for item in INVARIANTS if item["owner"] in owner_ids],
        "direct_callers": sorted(path for path, value in distance.items() if value == 1),
        "downstream": [
            {
                "path": path,
                "distance": value,
                "impact": "HIGH" if value <= 1 else "MEDIUM" if value <= 3 else "LOW",
            }
            for path, value in sorted(distance.items(), key=lambda item: (item[1], item[0]))
            if path not in changed and path in production
        ],
        "tests": sorted(impacted_tests, key=lambda item: (item["distance"], item["path"])),
        "evaluation_families": sorted(families),
        "complexity": [
            {
                key: item[key]
                for key in (
                    "path",
                    "loc",
                    "branch_score",
                    "fan_in",
                    "fan_out",
                    "production_fan_in",
                    "test_fan_in",
                )
            }
            for item in modules["modules"]
            if item["path"] in changed
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = analyze_impact(args.query)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
        return
    print("Changed:", ", ".join(result["changed"]))
    print("Owners:", ", ".join(item["id"] for item in result["owners"]) or "unassigned")
    for tier in ("HIGH", "MEDIUM", "LOW"):
        paths = [item["path"] for item in result["downstream"] if item["impact"] == tier]
        if paths:
            print(f"{tier}:", ", ".join(paths))
    print("Evaluation families:", ", ".join(result["evaluation_families"]) or "none mapped")
    print("Tests:", ", ".join(item["path"] for item in result["tests"]) or "none mapped")


if __name__ == "__main__":
    main()
