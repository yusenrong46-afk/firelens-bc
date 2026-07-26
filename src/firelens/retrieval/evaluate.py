"""Evaluate lexical retrieval against the reviewed FireLens gold questions."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from firelens.retrieval.bm25 import BM25Index, RetrievalResult, load_chunk_records


def _is_evidence_hit(result: RetrievalResult, evidence: dict[str, Any]) -> bool:
    if result.source_id != evidence["source_id"]:
        return False
    pages = evidence.get("pdf_pages") or []
    return not pages or result.page_number in pages


def evaluate_retrieval(
    index: BM25Index,
    questions: list[dict[str, Any]],
    *,
    corpus_source_ids: set[str],
    top_k: int = 5,
) -> dict[str, Any]:
    """Calculate evidence hit, reciprocal rank, and static-source coverage."""

    rows: list[dict[str, Any]] = []
    for question in questions:
        static_evidence = [
            evidence
            for evidence in question.get("evidence", [])
            if evidence["source_id"] in corpus_source_ids
        ]
        if not static_evidence:
            rows.append(
                {
                    "id": question["id"],
                    "question": question["question"],
                    "evaluation_status": "skipped_no_static_evidence",
                    "requires_live_verification": question.get(
                        "requires_live_verification", False
                    ),
                }
            )
            continue

        results = index.search(question["question"], top_k=top_k)
        first_hit_rank: int | None = None
        hit_sources: set[str] = set()
        for result in results:
            for evidence in static_evidence:
                if _is_evidence_hit(result, evidence):
                    hit_sources.add(evidence["source_id"])
                    if first_hit_rank is None:
                        first_hit_rank = result.rank

        expected_sources = {item["source_id"] for item in static_evidence}
        rows.append(
            {
                "id": question["id"],
                "question": question["question"],
                "evaluation_status": "evaluated",
                "answerability": question["answerability"],
                "requires_live_verification": question.get("requires_live_verification", False),
                "expected_static_sources": sorted(expected_sources),
                "first_evidence_rank": first_hit_rank,
                "hit_at_k": first_hit_rank is not None,
                "reciprocal_rank": 0.0 if first_hit_rank is None else 1 / first_hit_rank,
                "source_coverage": len(hit_sources) / len(expected_sources),
                "results": [
                    {
                        "rank": result.rank,
                        "score": result.score,
                        "source_id": result.source_id,
                        "locator": result.locator,
                        "section_title": result.section_title,
                        "is_evidence": any(
                            _is_evidence_hit(result, evidence) for evidence in static_evidence
                        ),
                    }
                    for result in results
                ],
            }
        )

    evaluated = [row for row in rows if row["evaluation_status"] == "evaluated"]
    count = len(evaluated)
    metrics = {
        "evaluated_question_count": count,
        "skipped_question_count": len(rows) - count,
        f"hit_at_{top_k}": (
            sum(row["hit_at_k"] for row in evaluated) / count if count else 0.0
        ),
        f"mrr_at_{top_k}": (
            sum(row["reciprocal_rank"] for row in evaluated) / count if count else 0.0
        ),
        f"mean_source_coverage_at_{top_k}": (
            sum(row["source_coverage"] for row in evaluated) / count if count else 0.0
        ),
    }
    return {"metrics": metrics, "questions": rows}


def write_report(report: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "evaluation_version": "bm25_evaluation.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        **report,
    }
    with output_path.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate BM25 on gold questions.")
    parser.add_argument("--chunks", type=Path, required=True)
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--top-k", type=int, default=5)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    records = load_chunk_records(args.chunks)
    gold = yaml.safe_load(args.gold.read_text(encoding="utf-8"))
    report = evaluate_retrieval(
        BM25Index(records),
        gold["questions"],
        corpus_source_ids={record.source_id for record in records},
        top_k=args.top_k,
    )
    write_report(report, args.output)
    print(json.dumps(report["metrics"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
