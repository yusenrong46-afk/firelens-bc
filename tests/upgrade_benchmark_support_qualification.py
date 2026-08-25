from __future__ import annotations

# ruff: noqa: F401
import gzip
import hashlib
import json
import math
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from PIL import Image

import scripts.upgrade_benchmark as upgrade_benchmark
from firelens.privacy_policy import APPROVED_PRODUCTION_PRIVACY
from scripts.upgrade_benchmark import (
    _assert_recomputed_summary_matches,
    _build_before_snapshot_seal,
    _capture_frontend_surface,
    _deployment,
    _development_retrieval,
    _frontend_bundle,
    _frontend_manual_review_protocol,
    _frontend_surface,
    _hard_probe,
    _live,
    _preview,
    _relevant_untracked_paths,
    _retrieval_qualification,
    _review,
    _semantic_holdout,
    _ux,
    _verify_before_snapshot_seal_payload,
    capture,
    compare_snapshots,
    load_dataset_role_registry,
    load_spec,
    validate_frontend_manual_review,
    validate_semantic_holdout,
)

ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / "data/evaluation/upgrade_benchmark_v1_5_2.yaml"
V3_PROTOCOL_PATH = ROOT / "data/evaluation/benchmark_v1_5_2_sealed_retrieval_v3.protocol.yaml"


def _hard_probe_report(*, mode: str = "qualified") -> dict:
    dataset = yaml.safe_load(
        (ROOT / "data/evaluation/hard_probe.v1.yaml").read_text(encoding="utf-8")
    )
    rows = [
        {
            "id": case["id"],
            "priority": case["priority"],
            "passed": True,
            "latency_ms": 10.0,
        }
        for case in dataset["cases"]
    ]
    return {
        "schema_version": "firelens_hard_probe_report.v1",
        "manifest": {
            "mode": mode,
            "provider_boundary": "openrouter" if mode == "qualified" else "offline_double",
            "commit": "a" * 40,
            "dataset_sha256": "b" * 64,
            "corpus_sha256": "c" * 64,
            "vector_matrix_sha256": "d" * 64,
            "document_context_sha256": None,
            "repairs_sha256": "e" * 64,
            "configuration_sha256": "f" * 64,
            "runtime_configuration": {},
            "models": {},
        },
        "summary": {
            "executed": 105,
            "passed": 105,
            "failed": 0,
            "cost_usd": 0.5 if mode == "qualified" else 0.0,
        },
        "results": rows,
    }


def _live_report() -> dict:
    generated_at = "2026-08-06T10:00:00+00:00"
    source_urls = {
        "incident": "https://official.example.test/incident",
        "perimeter": "https://official.example.test/perimeter",
        "evacuation": "https://official.example.test/evacuation",
    }
    cold_records = [
        {
            "result_id": f"{kind}:1",
            "kind": kind,
            "authority": "BC Wildfire Service",
            "source_url": f"https://official.example.test/{kind}",
            "source_updated_at": generated_at,
            "retrieved_at": generated_at,
            "status": "Active",
        }
        for kind in ("incident", "perimeter", "evacuation")
    ]
    chat_records = [{"result_id": "incident:1", "status": "Active"}]
    map_records = [
        {"result_id": "incident:1", "status": "Active"},
        {"result_id": "incident:2", "status": "Being Held"},
    ]
    map_pairs = sorted((row["result_id"], row["status"]) for row in map_records)
    map_digest = hashlib.sha256(
        json.dumps(map_pairs, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    cached_requests = [
        {
            "request_id": f"cached-{concurrency}-{request_index:02d}",
            "method": "GET",
            "path": "/api/v1/live/map",
            "layers": ["incidents", "perimeters", "evacuations"],
            "concurrency": concurrency,
            "request_index": request_index,
            "status_code": 200,
            "latency_ms": float(len(previous) + request_index),
            "result_count": 3,
        }
        for concurrency, previous in ((1, []), (5, [None]), (20, [None] * 6))
        for request_index in range(1, concurrency + 1)
    ]
    cached_p95 = upgrade_benchmark._p95([float(row["latency_ms"]) for row in cached_requests])
    assert cached_p95 is not None
    by_concurrency = {}
    for concurrency in (1, 5, 20):
        rows = [row for row in cached_requests if row["concurrency"] == concurrency]
        by_concurrency[str(concurrency)] = {
            "request_count": len(rows),
            "status_codes": [200],
            "p95_latency_ms": upgrade_benchmark._p95(
                [float(row["latency_ms"]) for row in rows]
            ),
        }
    checks = {
        "all_official_layers_available": True,
        "metadata_complete": True,
        "chat_map_records_match": True,
        "all_api_requests_succeeded": True,
        "cached_p95_within_target": True,
        "near_me_contract_valid": True,
    }
    return {
        "report_version": "firelens.live_qualification.v2",
        "evidence_schema_version": "firelens.live_qualification.evidence.v2",
        "generated_at": generated_at,
        "commit": "a" * 40,
        "source_urls": source_urls,
        "qualified": True,
        "checks": checks,
        "cold": {
            "latency_ms": 100.0,
            "result_count": 3,
            "requested_layers": ["incident", "perimeter", "evacuation"],
            "unavailable_layers": [],
            "records": cold_records,
            "metadata_complete": True,
        },
        "cached_api": {
            "p95_target_ms": 4_000.0,
            "p95_latency_ms": cached_p95,
            "request_count": 26,
            "requests": cached_requests,
            "by_concurrency": by_concurrency,
        },
        "chat_map": {
            "chat_request": {
                "method": "POST",
                "path": "/api/v1/ask",
                "question": "Are there active wildfires in BC currently?",
            },
            "map_request": {
                "method": "GET",
                "path": "/api/v1/live/map",
                "layers": ["incidents"],
            },
            "chat_status_code": 200,
            "map_status_code": 200,
            "chat_record_count": 1,
            "map_record_count": 2,
            "chat_records": chat_records,
            "map_records": map_records,
            "matching_ids_and_statuses": True,
            "map_records_sha256": map_digest,
        },
        "near_me": {
            "request": {
                "method": "POST",
                "path": "/api/v1/live/nearby",
                "body": {
                    "location": {
                        "latitude": 49.28,
                        "longitude": -123.12,
                        "radius_km": 50.0,
                    },
                    "layers": ["incident", "perimeter", "evacuation"],
                    "page": 1,
                    "page_size": 200,
                },
            },
            "status_code": 200,
            "requested_radius_km": 50.0,
            "requested_layers": ["incident", "perimeter", "evacuation"],
            "resolved_location": {"latitude": 49.28, "longitude": -123.12},
            "viewport": {
                "west": -123.8,
                "south": 48.8,
                "east": -122.4,
                "north": 49.8,
            },
            "pagination": {
                "page": 1,
                "page_size": 200,
                "total_results": 1,
                "total_pages": 1,
                "returned_results": 1,
                "has_previous": False,
                "has_next": False,
            },
            "result_count": 1,
            "records": chat_records,
            "unavailable_layers": [],
            "layer_statuses": [
                {
                    "kind": kind,
                    "authority": "BC Wildfire Service",
                    "source_url": source_urls[kind],
                    "available": True,
                    "source_updated_at": generated_at,
                    "retrieved_at": generated_at,
                    "freshness": "fresh",
                    "matching_result_count": 1 if kind == "incident" else 0,
                }
                for kind in ("incident", "perimeter", "evacuation")
            ],
            "official_fallback_urls": ["https://official.example.test/map"],
        },
        "elapsed_seconds": 1.0,
    }


def _sealed_report() -> dict:
    dataset = upgrade_benchmark.load_benchmark(
        ROOT / "data/evaluation/benchmark_v1_5_sealed_retrieval.yaml",
        require_release_shape=False,
    )
    cases = [
        case for case in dataset.cases if case.split == "holdout" and case.acceptable_evidence
    ]
    config = upgrade_benchmark.FireLensConfig.from_env(ROOT)
    chunks = {
        chunk.chunk_id: chunk
        for chunk in upgrade_benchmark.load_chunk_records(config.corpus_path)
    }
    ranking_by_case: dict[str, list[str]] = {}
    for case in cases:
        matching = next(
            (
                chunk_id
                for chunk_id in chunks
                if upgrade_benchmark._ranking_metrics([chunk_id], case, chunks)["hit"] == 1
            ),
            None,
        )
        assert matching is not None
        ranking_by_case[case.id] = [matching]
    cost_per_case = 0.5 / (3 * len(cases))
    repetition_reports = []
    total_cost = 0.0
    for repetition in range(1, 4):
        rows = []
        for index, case in enumerate(cases):
            ranking = [] if index == 0 else ranking_by_case[case.id]
            metrics = upgrade_benchmark._ranking_metrics(ranking, case, chunks)
            rows.append(
                {
                    "id": case.id,
                    "complete": True,
                    "reranked_chunk_ids": ranking,
                    "metrics": metrics,
                    "reported_cost_usd": cost_per_case,
                }
            )
            total_cost += cost_per_case
        repetition_reports.append(
            {
                "repetition": repetition,
                "complete": True,
                "case_count": len(rows),
                "recall_at_5": sum(float(row["metrics"]["hit"]) for row in rows) / len(rows),
                "mrr_at_5": sum(float(row["metrics"]["reciprocal_rank"]) for row in rows)
                / len(rows),
                "ndcg_at_5": sum(float(row["metrics"]["ndcg"]) for row in rows) / len(rows),
                "mean_source_coverage": sum(
                    float(row["metrics"]["source_coverage"]) for row in rows
                )
                / len(rows),
                "rows": rows,
            }
        )
    return {
        "report_version": "firelens_frozen_retrieval_qualification.v1",
        "evaluation_role": "sealed_release_qualification",
        "baseline_policy": "required_after_only",
        "commit": "a" * 40,
        "corpus_sha256": "b" * 64,
        "vector_matrix_sha256": "c" * 64,
        "configuration_sha256": "d" * 64,
        "document_context_sha256": None,
        "repairs_sha256": "e" * 64,
        "dataset_sha256": "f" * 64,
        "dataset_manifest_sha256": "0" * 64,
        "split": "holdout",
        "tuning_allowed": False,
        "relevance_addendum_used": False,
        "owner_approved": True,
        "repetitions": 3,
        "case_count_per_repetition": 47,
        "cost_budget_usd": 0.75,
        "cost_budget_exceeded": False,
        "reported_cost_usd": total_cost,
        "repeated_rankings_match": True,
        "qualified": True,
        "repetition_reports": repetition_reports,
    }


def _development_retrieval_report() -> dict:
    dataset_path = ROOT / "data/evaluation/benchmark_v1.yaml"
    dataset = upgrade_benchmark.load_benchmark(dataset_path)
    dataset = upgrade_benchmark.apply_relevance_addendum(
        dataset,
        upgrade_benchmark.load_relevance_addendum(
            ROOT / "data/evaluation/benchmark_v1_5_relevance_addendum.yaml",
            dataset_path=dataset_path,
        ),
    )
    cases = [
        case
        for case in dataset.cases
        if case.split == "development" and case.acceptable_evidence
    ]
    config = upgrade_benchmark.FireLensConfig.from_env(ROOT)
    chunks = {
        chunk.chunk_id: chunk
        for chunk in upgrade_benchmark.load_chunk_records(config.corpus_path)
    }
    rows = []
    for case in cases:
        matching = next(
            chunk_id
            for chunk_id in chunks
            if upgrade_benchmark._ranking_metrics([chunk_id], case, chunks)["hit"] == 1
        )
        rankings = {stage: [matching] for stage in ("bm25", "vector", "fused", "reranked")}
        rows.append(
            {
                "id": case.id,
                "retrieval_eligible": True,
                "complete": True,
                "rankings": rankings,
                "stage_metrics": {
                    stage: upgrade_benchmark._ranking_metrics(ranking, case, chunks)
                    for stage, ranking in rankings.items()
                },
                "reported_cost_usd": 0.001,
            }
        )
    summary = upgrade_benchmark._candidate_summary(rows)
    return {
        "report_version": "firelens_retrieval_comparison.v2",
        "commit": "a" * 40,
        "corpus_sha256": "b" * 64,
        "vector_matrix_sha256": "c" * 64,
        "document_context_sha256": None,
        "repairs_sha256": "d" * 64,
        "dataset_sha256": "e" * 64,
        "relevance_addendum_sha256": "f" * 64,
        "split": "development",
        "holdout_opened": False,
        "development_case_roster": [case.id for case in cases],
        "candidates": {"current": {"configuration": {}, **summary}},
        "details": {"current": rows},
    }


def _semantic_development_registry_payload() -> dict:
    datasets = [
        {
            "dataset_id": "development-conversation-v1",
            "dataset_sha256": "a" * 64,
            "source_id_sha256s": sorted(
                hashlib.sha256(value.encode()).hexdigest()
                for value in ("dev-source-a", "dev-source-b")
            ),
            "question_family_ids": [
                "dev-adjacent",
                "dev-capability",
                "dev-followup",
                "dev-safety",
                "dev-tangent",
            ],
        }
    ]
    sources = sorted(
        {source for dataset in datasets for source in dataset["source_id_sha256s"]}
    )
    families = sorted(
        {family for dataset in datasets for family in dataset["question_family_ids"]}
    )
    return {
        "registry_version": "firelens_semantic_development_exposure_registry.v1",
        "registry_id": "firelens-v1-5-2-development-exposure",
        "frozen_at": "2026-08-06T08:00:00+00:00",
        "dataset_roster_sha256": upgrade_benchmark._sha256_json(datasets),
        "datasets": datasets,
        "source_id_sha256s": sources,
        "source_roster_sha256": upgrade_benchmark._sha256_json(sources),
        "question_family_ids": families,
        "question_family_roster_sha256": upgrade_benchmark._sha256_json(families),
    }


def _semantic_holdout_manifest_payload(*, development_registry_sha256: str = "4" * 64) -> dict:
    family_ids = ["evidence", "evacuation", "limitations", "location", "status"]
    roster = [
        {
            "case_id": f"SH{index:03d}",
            "input_sha256": hashlib.sha256(f"private-input-{index}".encode()).hexdigest(),
            "source_id_sha256s": [
                hashlib.sha256(f"holdout-source-{((index - 1) % 5) + 1}".encode()).hexdigest()
            ],
            "question_family_id": family_ids[(index - 1) % len(family_ids)],
        }
        for index in range(1, 26)
    ]
    source_roster = sorted({source for row in roster for source in row["source_id_sha256s"]})
    question_family_roster = sorted({row["question_family_id"] for row in roster})
    family_distribution = {
        family: sum(row["question_family_id"] == family for row in roster)
        for family in question_family_roster
    }
    development_registry = _semantic_development_registry_payload()
    return {
        "manifest_version": "firelens_semantic_holdout_manifest.v3",
        "dataset_sha256": "f" * 64,
        "case_roster_sha256": upgrade_benchmark._sha256_json(roster),
        "case_count": 25,
        "case_roster": roster,
        "source_id_sha256s": source_roster,
        "source_roster_sha256": upgrade_benchmark._sha256_json(source_roster),
        "question_family_ids": question_family_roster,
        "question_family_roster_sha256": upgrade_benchmark._sha256_json(question_family_roster),
        "question_family_distribution": family_distribution,
        "development_registry_id": development_registry["registry_id"],
        "development_registry_sha256": development_registry_sha256,
        "disjointness_audit": {
            "audit_version": "firelens_semantic_disjointness_audit.v1",
            "audited_at": "2026-08-06T09:00:00+00:00",
            "development_registry_sha256": development_registry_sha256,
            "development_source_roster_sha256": development_registry["source_roster_sha256"],
            "development_question_family_roster_sha256": development_registry[
                "question_family_roster_sha256"
            ],
            "holdout_source_roster_sha256": upgrade_benchmark._sha256_json(source_roster),
            "holdout_question_family_roster_sha256": upgrade_benchmark._sha256_json(
                question_family_roster
            ),
            "source_overlap_id_sha256s": [],
            "question_family_overlap_ids": [],
            "source_disjoint_from_development": True,
            "question_family_disjoint_from_development": True,
        },
        "frozen_before_candidate": True,
        "double_review_required": True,
        "frozen_at": "2026-08-06T09:30:00+00:00",
    }


def _semantic_holdout_candidate_report(
    manifest: dict, *, manifest_sha256: str = "0" * 64
) -> dict:
    cases = []
    for roster_row in manifest["case_roster"]:
        case_id = roster_row["case_id"]
        response = f"Grounded response for {case_id}."
        claim = f"Supported claim for {case_id}."
        cases.append(
            {
                "case_id": case_id,
                "input_sha256": roster_row["input_sha256"],
                "response": response,
                "response_sha256": hashlib.sha256(response.encode()).hexdigest(),
                "claims": [
                    {
                        "claim_id": "claim-1",
                        "text": claim,
                        "text_sha256": hashlib.sha256(claim.encode()).hexdigest(),
                    }
                ],
            }
        )
    candidate_identity = {
        "candidate_id": "candidate-v1-5-2",
        "commit": "a" * 40,
        "corpus_sha256": "b" * 64,
        "vector_matrix_sha256": "c" * 64,
        "document_context_sha256": None,
        "repairs_sha256": "d" * 64,
        "configuration_sha256": "9" * 64,
    }
    return {
        "report_version": "firelens_semantic_holdout_report.v1",
        **candidate_identity,
        "candidate_identity_sha256": upgrade_benchmark._sha256_json(candidate_identity),
        "generated_at": "2026-08-06T10:00:00+00:00",
        "dataset_sha256": manifest["dataset_sha256"],
        "dataset_manifest_sha256": manifest_sha256,
        "case_count": manifest["case_count"],
        "cases": cases,
    }


def _semantic_holdout_review_bundle(
    report: dict,
    *,
    candidate_report_sha256: str = "1" * 64,
    manifest_sha256: str = "0" * 64,
    development_registry_sha256: str = "4" * 64,
) -> dict:
    case_ids = [case["case_id"] for case in report["cases"]]
    report_cases = {case["case_id"]: case for case in report["cases"]}
    reviewer_registry = [
        {"reviewer_id": "reviewer-a", "name": "Domain Expert A"},
        {"reviewer_id": "reviewer-b", "name": "Domain Expert B"},
    ]
    adjudicator = {
        "adjudicator_id": "adjudicator-a",
        "name": "Domain Adjudicator",
    }
    randomization_context = upgrade_benchmark._semantic_randomization_context_sha256(
        candidate_report_sha256=candidate_report_sha256,
        candidate_identity_sha256=report["candidate_identity_sha256"],
        dataset_manifest_sha256=manifest_sha256,
        development_registry_sha256=development_registry_sha256,
    )
    actors = [("reviewer", reviewer["reviewer_id"]) for reviewer in reviewer_registry] + [
        ("adjudicator", adjudicator["adjudicator_id"])
    ]
    actor_orders = []
    order_by_actor = {}
    for actor_role, actor_id in actors:
        order = upgrade_benchmark._semantic_actor_case_order(
            case_ids,
            randomization_context_sha256=randomization_context,
            actor_role=actor_role,
            actor_id=actor_id,
        )
        order_by_actor[(actor_role, actor_id)] = order
        actor_orders.append(
            {
                "actor_role": actor_role,
                "actor_id": actor_id,
                "case_ids": order,
                "case_order_sha256": upgrade_benchmark._sha256_json(order),
            }
        )

    case_reviews = {}
    for case_id in case_ids:
        claim_ids = [claim["claim_id"] for claim in report_cases[case_id]["claims"]]
        independent_reviews = [
            {
                "reviewer_id": reviewer_id,
                "reviewed_at": reviewed_at,
                "presentation_event_sha256": None,
                "independent": True,
                "blinded_to_candidate_identity": True,
                "blinded_to_other_review": True,
                "claim_labels": [
                    {"claim_id": claim_id, "label": "supported"} for claim_id in claim_ids
                ],
                "dangerous_omission": False,
                "case_decision": "approved",
            }
            for reviewer_id, reviewed_at in (
                ("reviewer-a", "2026-08-06T11:00:00+00:00"),
                ("reviewer-b", "2026-08-06T11:05:00+00:00"),
            )
        ]
        case_reviews[case_id] = {
            "case_id": case_id,
            "independent_reviews": independent_reviews,
            "adjudication": None,
        }

    events = []
    prior_digest = None

    def append_event(
        *,
        actor_role: str,
        actor_id: str,
        case_id: str,
        case_position: int,
        presented_at: datetime,
        review_material_sha256: str | None,
    ) -> str:
        candidate_case = report_cases[case_id]
        event = {
            "sequence": len(events) + 1,
            "event_id": f"PE{len(events) + 1:06d}",
            "event_type": (
                "independent_review_presentation"
                if actor_role == "reviewer"
                else "adjudication_presentation"
            ),
            "actor_role": actor_role,
            "actor_id": actor_id,
            "case_id": case_id,
            "case_position": case_position,
            "blinded_candidate_label": "Candidate A",
            "candidate_position": 1,
            "candidate_identity_sha256": report["candidate_identity_sha256"],
            "candidate_report_sha256": candidate_report_sha256,
            "input_sha256": candidate_case["input_sha256"],
            "response_sha256": candidate_case["response_sha256"],
            "claim_roster_sha256": upgrade_benchmark._semantic_claim_roster_sha256(
                candidate_case
            ),
            "review_material_sha256": review_material_sha256,
            "displayed_payload_sha256": None,
            "presented_at": presented_at.isoformat(),
            "previous_event_sha256": prior_digest,
        }
        event["displayed_payload_sha256"] = (
            upgrade_benchmark._semantic_displayed_payload_sha256(event)
        )
        event["event_sha256"] = upgrade_benchmark._semantic_presentation_event_sha256(event)
        events.append(event)
        return event["event_sha256"]

    reviewer_event_time = datetime(2026, 8, 6, 10, 1, tzinfo=UTC)
    for reviewer_index, reviewer in enumerate(reviewer_registry):
        reviewer_id = reviewer["reviewer_id"]
        for position, case_id in enumerate(order_by_actor[("reviewer", reviewer_id)], start=1):
            prior_digest = append_event(
                actor_role="reviewer",
                actor_id=reviewer_id,
                case_id=case_id,
                case_position=position,
                presented_at=reviewer_event_time,
                review_material_sha256=None,
            )
            reviewer_event_time += timedelta(seconds=1)
            case_reviews[case_id]["independent_reviews"][reviewer_index][
                "presentation_event_sha256"
            ] = prior_digest

    adjudication_event_time = datetime(2026, 8, 6, 11, 10, tzinfo=UTC)
    for position, case_id in enumerate(
        order_by_actor[("adjudicator", adjudicator["adjudicator_id"])], start=1
    ):
        independent_reviews = case_reviews[case_id]["independent_reviews"]
        review_digest = upgrade_benchmark._sha256_json(independent_reviews)
        prior_digest = append_event(
            actor_role="adjudicator",
            actor_id=adjudicator["adjudicator_id"],
            case_id=case_id,
            case_position=position,
            presented_at=adjudication_event_time,
            review_material_sha256=review_digest,
        )
        adjudication_event_time += timedelta(seconds=1)
        claim_ids = [claim["claim_id"] for claim in report_cases[case_id]["claims"]]
        case_reviews[case_id]["adjudication"] = {
            "adjudicator_id": adjudicator["adjudicator_id"],
            "adjudicated_at": "2026-08-06T12:00:00+00:00",
            "presentation_event_sha256": prior_digest,
            "reviewer_decisions_locked": True,
            "independent_reviews_sha256": review_digest,
            "resolution_status": "resolved",
            "claim_labels": [
                {"claim_id": claim_id, "label": "supported"} for claim_id in claim_ids
            ],
            "dangerous_omission": False,
            "case_decision": "approved",
        }

    cases = [
        case_reviews[case_id]
        for case_id in order_by_actor[("adjudicator", adjudicator["adjudicator_id"])]
    ]
    presentation_log = {
        "log_version": "firelens_semantic_holdout_presentation_log.v1",
        "log_id": "semantic-holdout-presentation-fixture",
        "append_only": True,
        "created_at": "2026-08-06T10:00:30+00:00",
        "finalized_at": "2026-08-06T11:20:00+00:00",
        "candidate_identity_sha256": report["candidate_identity_sha256"],
        "candidate_report_sha256": candidate_report_sha256,
        "dataset_manifest_sha256": manifest_sha256,
        "development_registry_sha256": development_registry_sha256,
        "randomization_context_sha256": randomization_context,
        "event_count": len(events),
        "events": events,
        "head_event_sha256": prior_digest,
    }
    return {
        "bundle_version": "firelens_semantic_holdout_review_bundle.v2",
        "generated_at": "2026-08-06T13:00:00+00:00",
        "candidate_id": report["candidate_id"],
        "candidate_identity_sha256": report["candidate_identity_sha256"],
        "candidate_report_sha256": candidate_report_sha256,
        "dataset_sha256": report["dataset_sha256"],
        "dataset_manifest_sha256": manifest_sha256,
        "development_registry_sha256": development_registry_sha256,
        "case_count": report["case_count"],
        "case_ids": [case["case_id"] for case in report["cases"]],
        "presentation": {
            "candidate_identity_blinded": True,
            "reviewers_blinded_to_each_other": True,
            "randomized": True,
            "randomization_algorithm": "sha256_identity_bound_sort.v1",
            "randomization_context_sha256": randomization_context,
            "blinded_candidate_label": "Candidate A",
            "actor_orders": actor_orders,
            "presentation_log_sha256": upgrade_benchmark._sha256_json(presentation_log),
        },
        "presentation_log": presentation_log,
        "reviewer_registry": reviewer_registry,
        "adjudicator": adjudicator,
        "cases": cases,
    }


def _semantic_holdout_evidence() -> tuple[dict, dict, dict]:
    manifest = _semantic_holdout_manifest_payload()
    report = _semantic_holdout_candidate_report(manifest)
    bundle = _semantic_holdout_review_bundle(report)
    return manifest, report, bundle


def _validate_semantic_holdout_payloads(
    manifest: dict, report: dict, bundle: dict, summary: dict | None = None
) -> dict:
    return _semantic_holdout(
        report,
        bundle,
        manifest=manifest,
        development_registry=_semantic_development_registry_payload(),
        candidate_report_sha256="1" * 64,
        review_bundle_sha256="3" * 64,
        dataset_manifest_sha256="0" * 64,
        development_registry_sha256="4" * 64,
        submitted_summary=summary,
    )


def _write_semantic_holdout_evidence(
    tmp_path: Path, *, include_summary: bool = False
) -> tuple[Path, Path, Path, Path, Path | None]:
    development_registry = _semantic_development_registry_payload()
    development_registry_path = tmp_path / "semantic-development-registry.json"
    development_registry_path.write_text(
        json.dumps(development_registry, indent=2), encoding="utf-8"
    )
    development_registry_sha256 = upgrade_benchmark.file_sha256(development_registry_path)
    manifest = _semantic_holdout_manifest_payload(
        development_registry_sha256=development_registry_sha256
    )
    manifest_path = tmp_path / "semantic-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    manifest_sha256 = upgrade_benchmark.file_sha256(manifest_path)
    report = _semantic_holdout_candidate_report(manifest, manifest_sha256=manifest_sha256)
    report_path = tmp_path / "semantic-report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    bundle = _semantic_holdout_review_bundle(
        report,
        candidate_report_sha256=upgrade_benchmark.file_sha256(report_path),
        manifest_sha256=manifest_sha256,
        development_registry_sha256=development_registry_sha256,
    )
    bundle_path = tmp_path / "semantic-review-bundle.json"
    bundle_path.write_text(json.dumps(bundle, indent=2), encoding="utf-8")
    summary_path = None
    if include_summary:
        recomputed = validate_semantic_holdout(
            report_path,
            bundle_path,
            manifest_path,
            development_registry_path,
        )
        summary = {key: value for key, value in recomputed.items() if key != "status"}
        summary["generated_at"] = "2026-08-06T13:01:00+00:00"
        summary_path = tmp_path / "semantic-summary.json"
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return (
        report_path,
        bundle_path,
        manifest_path,
        development_registry_path,
        summary_path,
    )


def _ux_report() -> dict:
    spec = load_spec(SPEC_PATH)
    participants = []
    for index in range(12):
        device_class = "mobile" if index % 2 == 0 else "desktop"
        access_methods = ["touch" if device_class == "mobile" else "pointer"]
        if index == 0:
            access_methods.append("keyboard")
        elif index == 1:
            access_methods.append("screen_reader")
        participants.append(
            {
                "participant_id": f"P{index + 1:02d}",
                "cohort": "novice_bc_resident" if index < 4 else "wildfire_aware",
                "device_class": device_class,
                "access_methods": access_methods,
            }
        )
    attempts = []
    for participant in participants:
        for task in spec.ux_tasks:
            row = {
                "participant_id": participant["participant_id"],
                "task_id": task.id,
                "criterion_results": {
                    criterion.id: True for criterion in task.completion_criteria
                },
                "critical_error_codes": [],
                "critical_error_notes": {},
                "duration_seconds": 30.0,
                "seq_score": 6,
                "confidence": 6,
                "observed_outcome": "Completed using the expected evidence path.",
            }
            attempts.append(row)
    return {
        "schema_version": "firelens_ux_benchmark_report.v3",
        "label": "before",
        "protocol_id": spec.benchmark_id,
        "commit": "a" * 40,
        "deployment_id": "local-before",
        "moderator": "Morgan Lee",
        "observed_at": "2026-08-06T12:00:00+00:00",
        "participant_count": 12,
        "recruitment_constraint": "Twelve participants complete the frozen baseline round.",
        "participants": participants,
        "attempts": attempts,
        "task_reference": [task.model_dump() for task in spec.ux_tasks],
    }


def _deployment_report() -> dict:
    return {
        "schema_version": "firelens_deployment_benchmark_report.v2",
        "label": "after",
        "commit": "a" * 40,
        "reviewed_by": "Release Owner",
        "reviewed_at": "2026-08-06T12:00:00+00:00",
        "distributed_rate_limit_verified": True,
        "rollback_rehearsal_passed": True,
        "rate_limit_evidence": {
            "platform": "vercel_firewall",
            "rule_id": "firewall-rule-1",
            "candidate_deployment_id": "candidate-a",
            "shared_key_sha256": "c" * 64,
            "configured_limit": 5,
            "first_rejected_combined_ordinal": 6,
            "observations": [
                {
                    "client_id": "client-a",
                    "region": "iad1",
                    "observed_at": "2026-08-06T12:00:00+00:00",
                    "combined_ordinal": 1,
                    "status_code": 200,
                },
                {
                    "client_id": "client-b",
                    "region": "sfo1",
                    "observed_at": "2026-08-06T12:00:01+00:00",
                    "combined_ordinal": 6,
                    "status_code": 429,
                },
            ],
        },
        "rollback_evidence": {
            "candidate_deployment_id": "candidate-a",
            "candidate_commit": "a" * 40,
            "restored_deployment_id": "previous-a",
            "restored_commit": "b" * 40,
            "verified_at": "2026-08-06T12:05:00+00:00",
            "candidate_artifact_sha256": "d" * 64,
            "restored_artifact_sha256": "e" * 64,
            "candidate_environment_snapshot": {
                "release_version": "1.5.3-rc.1",
                "build_commit": "a" * 40,
                "candidate_id": "firelens-v1-5-2:" + "a" * 40,
                "embedding_model": "openai/text-embedding-3-small",
                "rerank_model": "cohere/rerank-4-pro",
                "generation_model": "openai/gpt-5.6-luna",
                **APPROVED_PRODUCTION_PRIVACY.candidate_fields(),
            },
            "restored_environment_snapshot": {
                "release_version": "1.5.2",
                "build_commit": "b" * 40,
                "candidate_id": "firelens-v1-5-2:" + "b" * 40,
                "embedding_model": "openai/text-embedding-3-small",
                "rerank_model": "cohere/rerank-4-pro",
                "generation_model": "openai/gpt-5.6-luna",
                **APPROVED_PRODUCTION_PRIVACY.candidate_fields(),
            },
            "checks": {
                "readiness_restored": True,
                "homepage_anonymous": True,
                "release_identity_restored": True,
                "environment_snapshot_restored": True,
                "grounded_smoke_passed": True,
                "live_smoke_passed": True,
            },
        },
        "notes": "",
    }


def _write_deployment_evidence(tmp_path: Path, report: dict) -> tuple[Path, Path]:
    rate_limit_path = tmp_path / "rate-limit-evidence.json"
    rollback_path = tmp_path / "rollback-evidence.json"
    rate_limit_path.write_text(
        json.dumps(report["rate_limit_evidence"], sort_keys=True), encoding="utf-8"
    )
    rollback_path.write_text(
        json.dumps(report["rollback_evidence"], sort_keys=True), encoding="utf-8"
    )
    report["rate_limit_artifact_sha256"] = upgrade_benchmark.file_sha256(rate_limit_path)
    report["rollback_artifact_sha256"] = upgrade_benchmark.file_sha256(rollback_path)
    return rate_limit_path, rollback_path


__all__ = [name for name in globals() if not name.startswith("__")]
