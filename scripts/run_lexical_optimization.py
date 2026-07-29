#!/usr/bin/env python3
"""Compare bounded BM25 candidates on development labels without provider calls."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from firelens.benchmark import (
    _mean,
    _ranking_metrics,
    apply_relevance_addendum,
    file_sha256,
    load_benchmark,
    load_relevance_addendum,
)
from firelens.config import FireLensConfig
from firelens.contracts import RetrievalTextStrategy
from firelens.retrieval.bm25 import BM25Index, tokenize, tokenize_with_identifiers
from firelens.retrieval.text import render_retrieval_text
from firelens.runtime import load_corpus_resources
from firelens.storage import atomic_text_writer

ROOT = Path(__file__).resolve().parents[1]


def _field_boosted_text(chunk: Any) -> str:
    base = render_retrieval_text(chunk, RetrievalTextStrategy.METADATA_CONTEXT_V1)
    fields = [f"Search title: {chunk.title}"]
    if chunk.section_title:
        fields.append(f"Search section: {chunk.section_title}")
    if chunk.locator:
        fields.append(f"Search locator: {chunk.locator}")
    return "\n".join([base, *fields])


def _summary(rows: list[dict[str, Any]], *, top_k: int) -> dict[str, float]:
    return {
        "recall": _mean([float(row["metrics"]["hit"]) for row in rows]),
        "mrr": _mean([float(row["metrics"]["reciprocal_rank"]) for row in rows]),
        "ndcg": _mean([float(row["metrics"]["ndcg"]) for row in rows]),
        "mean_source_coverage": _mean(
            [float(row["metrics"]["source_coverage"]) for row in rows]
        ),
        "top_k": float(top_k),
    }


def run(output_path: Path) -> dict[str, Any]:
    config = FireLensConfig.from_env(ROOT)
    chunks, corpus_version = load_corpus_resources(config)
    chunks_by_id = {chunk.chunk_id: chunk for chunk in chunks}
    dataset_path = ROOT / "data/evaluation/benchmark_v1.yaml"
    addendum_path = ROOT / "data/evaluation/benchmark_v1_5_relevance_addendum.yaml"
    dataset = apply_relevance_addendum(
        load_benchmark(dataset_path),
        load_relevance_addendum(addendum_path, dataset_path=dataset_path),
    )
    cases = [
        case
        for case in dataset.cases
        if case.split == "development" and case.acceptable_evidence
    ]
    current_texts = [
        render_retrieval_text(chunk, RetrievalTextStrategy.METADATA_CONTEXT_V1)
        for chunk in chunks
    ]
    boosted_texts = [_field_boosted_text(chunk) for chunk in chunks]
    candidates = {
        "current": BM25Index(chunks, retrieval_texts=current_texts, tokenizer=tokenize),
        "identifier_tokens": BM25Index(
            chunks, retrieval_texts=current_texts, tokenizer=tokenize_with_identifiers
        ),
        "field_boosted": BM25Index(chunks, retrieval_texts=boosted_texts, tokenizer=tokenize),
        "identifier_and_field_boosted": BM25Index(
            chunks, retrieval_texts=boosted_texts, tokenizer=tokenize_with_identifiers
        ),
    }
    details: dict[str, dict[str, list[dict[str, Any]]]] = {}
    summaries: dict[str, dict[str, dict[str, float]]] = {}
    for name, index in candidates.items():
        details[name] = {}
        summaries[name] = {}
        for top_k in (5, 30):
            rows = []
            for case in cases:
                ranking = [
                    result.chunk_id for result in index.search(case.question, top_k=top_k)
                ]
                rows.append(
                    {
                        "id": case.id,
                        "metrics": _ranking_metrics(ranking, case, chunks_by_id),
                        "chunk_ids": ranking,
                    }
                )
            key = f"at_{top_k}"
            details[name][key] = rows
            summaries[name][key] = _summary(rows, top_k=top_k)
    current = summaries["current"]
    eligible = []
    for name, summary in summaries.items():
        if name == "current":
            continue
        recall_gain = summary["at_5"]["recall"] >= current["at_5"]["recall"] + 0.02
        mrr_gain = summary["at_5"]["mrr"] >= current["at_5"]["mrr"] + 0.03
        if (
            summary["at_30"]["recall"] >= current["at_30"]["recall"]
            and summary["at_5"]["mean_source_coverage"]
            >= current["at_5"]["mean_source_coverage"]
            and (recall_gain or mrr_gain)
        ):
            eligible.append(
                (
                    summary["at_5"]["recall"],
                    summary["at_5"]["mrr"],
                    summary["at_5"]["ndcg"],
                    name,
                )
            )
    selected = max(eligible)[-1] if eligible else "current"
    report = {
        "report_version": "firelens_lexical_optimization.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "split": "development",
        "holdout_opened": False,
        "provider_calls": 0,
        "dataset_sha256": file_sha256(dataset_path),
        "relevance_addendum_sha256": file_sha256(addendum_path),
        "corpus_version": corpus_version,
        "case_count": len(cases),
        "summaries": summaries,
        "selected": selected,
        "selection_rule": (
            "preserve Recall@30 and source coverage; gain at least two Recall@5 points "
            "or three MRR@5 points"
        ),
        "details": details,
    }
    with atomic_text_writer(output_path) as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output/benchmark/v1_5_lexical_optimization.json"),
    )
    args = parser.parse_args()
    report = run(ROOT / args.output)
    print(
        json.dumps(
            {
                "case_count": report["case_count"],
                "provider_calls": report["provider_calls"],
                "selected": report["selected"],
                "summaries": report["summaries"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
