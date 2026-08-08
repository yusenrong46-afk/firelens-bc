from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from firelens.review_workspace.inputs import ReviewInputError, import_retrieval_suite

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data/evaluation/benchmark_v1_5_sealed_retrieval.yaml"
CORPUS = ROOT / "data/processed/firelens_static_corpus.chunks.jsonl"
MANIFEST = ROOT / "data/processed/firelens_static_corpus.manifest.json"


def test_retrieval_import_uses_all_reviewable_cases_and_only_blind_fields() -> None:
    suite = import_retrieval_suite(DATASET, CORPUS, MANIFEST)

    assert suite.suite_kind == "retrieval"
    assert suite.qualification_status == "eligible"
    assert len(suite.cases) == 47
    assert tuple(case.case_id for case in suite.cases) == tuple(
        sorted(case.case_id for case in suite.cases)
    )
    forbidden = {
        "model",
        "provider",
        "candidate",
        "ranking",
        "automated_verdict",
        "latency",
        "cost",
        "route",
        "mode",
    }
    for case in suite.cases:
        payload = case.payload.model_dump(mode="json")
        assert forbidden.isdisjoint(payload)
        assert payload["answer"] is None
        assert payload["claims"] == []
        assert payload["local_source_context"]
    suite.recheck_input_files()


def test_retrieval_import_refuses_a_ranking_report_disguised_as_labels(
    tmp_path: Path,
) -> None:
    payload = yaml.safe_load(DATASET.read_text(encoding="utf-8"))
    payload["rankings"] = [{"case_id": "V1-HOLD-101", "rank": 1}]
    disguised = tmp_path / "ranking.yaml"
    disguised.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(ReviewInputError, match="never a ranking report"):
        import_retrieval_suite(disguised, CORPUS, MANIFEST)
