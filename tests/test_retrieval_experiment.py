from pathlib import Path

import pytest

from firelens.benchmark import (
    apply_relevance_addendum,
    load_benchmark,
    load_relevance_addendum,
)
from firelens.config import FireLensConfig
from firelens.retrieval_experiment import select_retrieval_candidate

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
    assert "two-point" in reason


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
