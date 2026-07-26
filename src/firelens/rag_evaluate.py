"""Run the existing questions as a diagnostic, without claiming semantic grading."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from firelens.contracts import QueryRequest
from firelens.runtime import Runtime


def load_questions(path: Path) -> tuple[str, list[dict[str, Any]]]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("questions"), list):
        raise ValueError("Gold question file has an invalid shape.")
    questions = payload["questions"]
    if any(
        not isinstance(item, dict)
        or not isinstance(item.get("id"), str)
        or not isinstance(item.get("question"), str)
        for item in questions
    ):
        raise ValueError("Gold question file contains an invalid question.")
    return str(payload.get("dataset_version", "unknown")), questions


async def run_diagnostic(
    runtime: Runtime,
    *,
    gold_path: Path,
    output_path: Path,
    limit: int | None = None,
) -> dict[str, Any]:
    if runtime.service is None:
        raise RuntimeError("FireLens runtime is not ready.")
    dataset_version, questions = load_questions(gold_path)
    if limit is not None:
        questions = questions[:limit]

    rows: list[dict[str, Any]] = []
    for item in questions:
        response = await runtime.service.ask(QueryRequest(question=item["question"]))
        rows.append(
            {
                "id": item["id"],
                "question": item["question"],
                "expected_answerability": item.get("answerability"),
                "expected_live_verification": bool(
                    item.get("requires_live_verification", False)
                ),
                "response": response.model_dump(mode="json"),
            }
        )

    statuses = Counter(row["response"]["status"] for row in rows)
    reason_codes = Counter(
        row["response"].get("reason_code") or "none" for row in rows
    )
    report = {
        "report_version": "firelens_rag_diagnostic.v1",
        "kind": "diagnostic_not_release_benchmark",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset_version": dataset_version,
        "corpus_version": runtime.corpus_version,
        "models": {
            "embedding": runtime.config.embedding_model,
            "rerank": runtime.config.rerank_model,
            "generation": runtime.config.generation_model,
        },
        "question_count": len(rows),
        "status_counts": dict(sorted(statuses.items())),
        "reason_code_counts": dict(sorted(reason_codes.items())),
        "semantic_correctness_scored": False,
        "questions": rows,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report
