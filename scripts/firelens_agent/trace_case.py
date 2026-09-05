#!/usr/bin/env python3
"""Trace deterministic request understanding and planning without I/O providers."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


def build_trace(
    question: str,
    *,
    location_label: str | None = None,
    include_question: bool = False,
    root: Path = ROOT,
) -> dict[str, Any]:
    source_root = str(root / "src")
    if source_root in sys.path:
        sys.path.remove(source_root)
    sys.path.insert(0, source_root)
    from firelens.agent.query_plan import plan_agent_request
    from firelens.answering.intent_automaton import parse_request_intent
    from firelens.contracts import QueryRequest
    from firelens.live_contracts import LocationInput

    request = QueryRequest(
        question=question,
        location=LocationInput(label=location_label) if location_label else None,
    )
    parsed = parse_request_intent(request.question)
    plan = plan_agent_request(request)
    plan_payload = plan.model_dump(mode="json")
    if not include_question:
        for key in ("location_label", "static_subrequest"):
            if plan_payload[key] is not None:
                plan_payload[key] = "[redacted]"
        for call in plan_payload["tool_calls"]:
            call["arguments"] = {key: "[redacted]" for key in call["arguments"]}
    clauses = []
    for index, clause in enumerate(parsed.clauses, start=1):
        item = {
            "index": index,
            "kind": clause.kind.value,
            "temporal_scope": clause.temporal_scope.value,
            "operation": clause.operation.value if clause.operation else None,
            "live_layers": [layer.value for layer in clause.live_layers],
            "has_location_candidate": clause.live_location_candidate is not None,
        }
        if include_question:
            item["text"] = clause.text
            item["location_candidate"] = clause.live_location_candidate
        clauses.append(item)
    map_digest = None
    module_index = root / "docs/firelens-map/module-index.json"
    if module_index.is_file():
        map_digest = json.loads(module_index.read_text(encoding="utf-8"))["source_digest"]
    trace = {
        "schema_version": "firelens.offline_request_trace.v1",
        "execution_mode": "planning_only_offline",
        "network_calls": 0,
        "provider_calls": 0,
        "question_sha256": hashlib.sha256(request.question.encode()).hexdigest(),
        "map_source_digest": map_digest,
        "understanding": {
            "owner": "src/firelens/answering/intent_automaton.py",
            "requests_non_bc_scope": parsed.requests_non_bc_scope,
            "clauses": clauses,
        },
        "planning": {
            "owner": "src/firelens/agent/query_plan.py",
            **plan_payload,
        },
        "unexecuted_stages": [
            "location_binding",
            "live_fetch",
            "retrieval",
            "reranking",
            "generation",
            "validation",
            "composition",
            "frontend",
        ],
    }
    if include_question:
        trace["question"] = request.question
        trace["location_label"] = location_label
    return trace


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question")
    parser.add_argument("--location-label")
    parser.add_argument("--include-question", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            build_trace(
                args.question,
                location_label=args.location_label,
                include_question=args.include_question,
            ),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
