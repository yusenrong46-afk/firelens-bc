from firelens.retrieval_experiment import select_retrieval_candidate


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
            "broader_recall": _summary(0.94, 0.89),
            "wider_evidence": _summary(0.93, 0.91),
        }
    )
    assert selected == "wider_evidence"
