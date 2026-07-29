from pathlib import Path

import pytest

from firelens.benchmark import (
    apply_relevance_addendum,
    load_benchmark,
    load_relevance_addendum,
)
from firelens.config import FireLensConfig
from firelens.contracts import QueryPlan, QueryRoute, RetrievalBundle, RetrievalRequest
from firelens.retrieval_experiment import _candidate_row, select_retrieval_candidate

ROOT = Path(__file__).resolve().parents[1]


def test_promoted_retrieval_defaults_match_the_winning_candidate() -> None:
    config = FireLensConfig.from_env(ROOT)

    assert (config.bm25_top_k, config.vector_top_k, config.fused_top_k) == (30, 30, 30)


def test_relevance_addendum_is_hash_bound_and_preserves_locked_labels() -> None:
    dataset_path = ROOT / "data/evaluation/benchmark_v1.yaml"
    dataset = load_benchmark(dataset_path)
    addendum = load_relevance_addendum(
        ROOT / "data/evaluation/benchmark_v1_5_relevance_addendum.yaml",
        dataset_path=dataset_path,
    )

    updated = apply_relevance_addendum(dataset, addendum)
    original_case = next(case for case in dataset.cases if case.id == "V1-DEV-026")
    updated_case = next(case for case in updated.cases if case.id == "V1-DEV-026")

    assert {item.source_id for item in original_case.acceptable_evidence} == {
        "bccdc_smoke_health_factsheet",
        "preparedbc_wildfire_guide",
    }
    assert "bccdc_wildfire_smoke" in {
        item.source_id for item in updated_case.acceptable_evidence
    }


def test_relevance_addendum_rejects_a_changed_base_dataset(tmp_path: Path) -> None:
    dataset_path = tmp_path / "benchmark.yaml"
    dataset_path.write_text(
        (ROOT / "data/evaluation/benchmark_v1.yaml").read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="locked benchmark hash"):
        load_relevance_addendum(
            ROOT / "data/evaluation/benchmark_v1_5_relevance_addendum.yaml",
            dataset_path=dataset_path,
        )


def _summary(recall: float, coverage: float, *, complete: bool = True) -> dict:
    return {
        "complete": complete,
        "stages": {
            "reranked": {
                "recall": recall,
                "mean_source_coverage": coverage,
                "ndcg": recall,
                "mrr": recall,
            }
        },
    }


def test_retrieval_selection_preserves_current_below_two_point_gain() -> None:
    selected, reason = select_retrieval_candidate(
        {
            "current": _summary(0.90, 0.90),
            "broader_recall": _summary(0.91, 0.95),
        }
    )
    assert selected == "current"
    assert "Recall@5 or MRR@5" in reason


def test_retrieval_selection_accepts_material_mrr_gain_at_equal_recall() -> None:
    current = _summary(0.98, 0.90)
    candidate = _summary(0.98, 0.90)
    current["stages"]["reranked"]["mrr"] = 0.90
    candidate["stages"]["reranked"]["mrr"] = 0.94

    selected, reason = select_retrieval_candidate(
        {"current": current, "user_intent_preserved": candidate}
    )

    assert selected == "user_intent_preserved"
    assert "MRR@5" in reason


def test_retrieval_selection_requires_no_source_coverage_loss() -> None:
    selected, _ = select_retrieval_candidate(
        {
            "current": _summary(0.90, 0.90),
            "broader_recall": _summary(0.97, 0.89),
            "wider_evidence": _summary(0.96, 0.91),
        }
    )
    assert selected == "wider_evidence"


def test_retrieval_selection_uses_only_queries_that_invoke_static_retrieval() -> None:
    current = _summary(0.90, 0.90)
    candidate = _summary(0.92, 0.92)
    current["route_eligible_stages"] = _summary(0.94, 0.90)["stages"]
    candidate["route_eligible_stages"] = _summary(0.98, 0.92)["stages"]
    selected, reason = select_retrieval_candidate(
        {"current": current, "rank_sensitive": candidate}
    )
    assert selected == "rank_sensitive"
    assert "route-eligible" in reason


def test_paid_retrieval_row_records_provenance_and_latency() -> None:
    case = load_benchmark(ROOT / "data/evaluation/benchmark_v1.yaml").cases[0]
    plan = QueryPlan(
        route=QueryRoute.RELATED,
        normalized_question=case.question,
        original_question=case.question,
        retrieval_requests=[RetrievalRequest(query=case.question)],
    )
    bundle = RetrievalBundle(
        provider_models={"reranker": "provider/model"},
        provider_attempts={"reranker": 2},
        provider_usage={"reranker": {"prompt_tokens": 10, "total_tokens": 10}},
        timings_ms={"reranker": 12.5},
    )

    row = _candidate_row(
        case,
        plan=plan,
        bundle=bundle,
        chunks_by_id={},
        wall_latency_ms=20.0,
    )

    assert row["provider_models"] == {"reranker": "provider/model"}
    assert row["provider_attempts"] == {"reranker": 2}
    assert row["provider_tokens"]["total_tokens"] == 10
    assert row["provider_timings_ms"] == {"reranker": 12.5}
    assert row["wall_latency_ms"] == 20.0
