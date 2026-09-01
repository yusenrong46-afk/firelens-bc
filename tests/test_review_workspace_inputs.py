from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml
from test_freeze_semantic_holdout import _development_request, _private_payload, _write_json
from upgrade_benchmark_support import _semantic_holdout_candidate_report

import scripts.freeze_semantic_holdout as freeze
from firelens.review_workspace.inputs import (
    ReviewInputError,
    import_retrieval_suite,
    import_semantic_holdout_suite,
)

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


@pytest.mark.parametrize(
    ("field", "value", "match"),
    (
        ("admission_warnings", [{"bad": "shape"}], "admission warning"),
        (
            "quarantined_pages",
            [
                {
                    "source_id": "firesmart_begins_at_home",
                    "page_number": 10,
                    "document_sha256": "0" * 64,
                    "review_status": "pending_owner_review",
                    "reason": "not bound to the admitted source revision",
                }
            ],
            "quarantined page",
        ),
    ),
)
def test_retrieval_import_validates_current_admission_manifest_fields(
    tmp_path: Path, field: str, value: object, match: str
) -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest[field] = value
    changed = tmp_path / "manifest.json"
    changed.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ReviewInputError, match=match):
        import_retrieval_suite(DATASET, CORPUS, changed)


def test_semantic_holdout_import_recomputes_overlap_from_the_bound_registry(
    tmp_path: Path,
) -> None:
    request_path = tmp_path / "development-request.json"
    registry_path = tmp_path / "development-registry.json"
    private_path = tmp_path / "private.json"
    manifest_path = tmp_path / "manifest.json"
    report_path = tmp_path / "candidate-report.json"
    _write_json(request_path, _development_request())
    freeze.freeze_development_registry(
        request_path,
        registry_path,
        attest_no_candidate=True,
        candidate_created_at=None,
    )
    private = _private_payload()
    _write_json(private_path, private)
    manifest = freeze.freeze_holdout_manifest(
        private_path,
        registry_path,
        manifest_path,
        audited_at="2026-08-06T17:00:00+00:00",
        frozen_at="2026-08-06T17:05:00+00:00",
        attest_no_candidate=True,
        candidate_created_at=None,
    )
    valid_report_path = tmp_path / "valid-candidate-report.json"
    valid_report = _semantic_holdout_candidate_report(
        manifest,
        manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
    )
    valid_report["generated_at"] = "2026-08-06T18:00:00+00:00"
    _write_json(valid_report_path, valid_report)
    valid_suite = import_semantic_holdout_suite(
        private_path,
        manifest_path,
        valid_report_path,
        registry_path,
    )
    assert valid_suite.qualification_status == "eligible"
    assert {identity.label for identity in valid_suite.input_files} == {
        "holdout_candidate_report",
        "holdout_manifest",
        "private_holdout_payload",
        "semantic_development_registry",
    }

    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    overlap = private["cases"][0]["source_id_sha256s"][0]
    development_sources = sorted({*registry["datasets"][0]["source_id_sha256s"], overlap})
    registry["datasets"][0]["source_id_sha256s"] = development_sources
    registry["dataset_roster_sha256"] = freeze._canonical_digest(registry["datasets"])
    registry["source_id_sha256s"] = development_sources
    registry["source_roster_sha256"] = freeze._canonical_digest(development_sources)
    _write_json(registry_path, registry)
    with pytest.raises(ReviewInputError, match="semantic_development_registry"):
        valid_suite.recheck_input_files()
    registry_sha256 = hashlib.sha256(registry_path.read_bytes()).hexdigest()
    manifest["development_registry_sha256"] = registry_sha256
    manifest["disjointness_audit"]["development_registry_sha256"] = registry_sha256
    manifest["disjointness_audit"]["development_source_roster_sha256"] = registry[
        "source_roster_sha256"
    ]
    _write_json(manifest_path, manifest)
    report = _semantic_holdout_candidate_report(
        manifest,
        manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
    )
    report["generated_at"] = "2026-08-06T18:00:00+00:00"
    _write_json(report_path, report)

    with pytest.raises(ReviewInputError, match="source-overlap audit is inconsistent"):
        import_semantic_holdout_suite(
            private_path,
            manifest_path,
            report_path,
            registry_path,
        )
