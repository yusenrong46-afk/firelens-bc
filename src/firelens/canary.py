"""Cost-bounded repeated-generation canary for status stability."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from firelens.benchmark import _percentile, _usage_cost
from firelens.contracts import QueryRequest
from firelens.runtime import Runtime
from firelens.storage import atomic_text_writer


async def run_variability_canary(
    runtime: Runtime,
    *,
    question: str,
    calls: int,
    output_path: Path,
    max_cost_usd: float,
) -> dict[str, Any]:
    if runtime.service is None:
        raise RuntimeError("FireLens runtime is not ready")
    rows: list[dict[str, Any]] = []
    reported_cost = 0.0
    for index in range(1, calls + 1):
        if reported_cost >= max_cost_usd:
            break
        started = perf_counter()
        response = await runtime.service.ask(QueryRequest(question=question))
        latency_ms = (perf_counter() - started) * 1_000
        trace_path = runtime.config.trace_dir / f"{response.trace_id}.json"
        trace = json.loads(trace_path.read_text(encoding="utf-8"))
        usage = {
            "retrieval": next(
                event.get("provider_usage", {})
                for event in trace["events"]
                if event["operation"] == "search"
            ),
            "generation": next(
                event.get("generation_usage", {})
                for event in trace["events"]
                if event["operation"] == "ask"
            ),
        }
        cost = _usage_cost(usage)
        reported_cost += cost
        rows.append(
            {
                "call": index,
                "status": response.status.value,
                "reason_code": response.reason_code,
                "validation_accepted": bool(
                    response.validation and response.validation.accepted
                ),
                "answer_sha256": (
                    hashlib.sha256(response.answer.encode("utf-8")).hexdigest()
                    if response.answer
                    else None
                ),
                "latency_ms": latency_ms,
                "reported_cost_usd": cost,
            }
        )
    statuses = sorted({row["status"] for row in rows})
    reason_codes = sorted({str(row["reason_code"]) for row in rows})
    latencies = [float(row["latency_ms"]) for row in rows]
    report = {
        "report_version": "firelens_variability_canary.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "question_sha256": hashlib.sha256(question.encode("utf-8")).hexdigest(),
        "requested_calls": calls,
        "completed_calls": len(rows),
        "complete": len(rows) == calls,
        "cost_budget_usd": max_cost_usd,
        "reported_cost_usd": reported_cost,
        "statuses": statuses,
        "reason_codes": reason_codes,
        "status_variance": len(statuses) > 1,
        "reason_code_variance": len(reason_codes) > 1,
        "all_structurally_accepted": all(row["validation_accepted"] for row in rows),
        "latency_ms_p50": _percentile(latencies, 0.50),
        "latency_ms_p95": _percentile(latencies, 0.95),
        "rows": rows,
    }
    with atomic_text_writer(output_path) as stream:
        stream.write(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return report
