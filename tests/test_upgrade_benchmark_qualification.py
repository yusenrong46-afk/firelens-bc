from __future__ import annotations

# ruff: noqa: F403, F405
from upgrade_benchmark_support import *


def test_hard_probe_parser_accepts_the_complete_qualified_protocol() -> None:
    parsed = _hard_probe(_hard_probe_report(), expected_mode="qualified")

    assert parsed["status"] == "complete"
    assert parsed["executed"] == 105
    assert parsed["pass_rate"] == 1.0
    assert parsed["critical_failures"] == 0
    assert parsed["provider_boundary"] == "openrouter"


def test_hard_probe_parser_rejects_an_unknown_case_id() -> None:
    report = _hard_probe_report()
    report["results"][0]["id"] = "fabricated-case-id"

    with pytest.raises(ValueError, match="case IDs|dataset"):
        _hard_probe(report, expected_mode="qualified")


def test_hard_probe_parser_rejects_tampered_dataset_priority() -> None:
    report = _hard_probe_report()
    critical = next(row for row in report["results"] if row["priority"] == "CRITICAL")
    critical["priority"] = "LOW"

    with pytest.raises(ValueError, match="priorit|dataset"):
        _hard_probe(report, expected_mode="qualified")


def test_hard_probe_parser_rejects_wrong_boundary_and_incomplete_protocol() -> None:
    wrong_boundary = _hard_probe_report()
    wrong_boundary["manifest"]["provider_boundary"] = "offline_double"
    with pytest.raises(ValueError, match="wrong provider boundary"):
        _hard_probe(wrong_boundary, expected_mode="qualified")

    incomplete = _hard_probe_report()
    incomplete["results"].pop()
    incomplete["summary"].update({"executed": 104, "passed": 104})
    with pytest.raises(ValueError, match="exactly 105"):
        _hard_probe(incomplete, expected_mode="qualified")


def test_live_parser_accepts_the_frozen_protocol() -> None:
    parsed = _live(_live_report())

    assert parsed["status"] == "complete"
    assert parsed["qualified"] is True
    assert parsed["cached_p95_ms"] == 25.0
    assert parsed["chat_map_records_match"] is True


def test_live_parser_requires_the_exact_canonical_checks() -> None:
    report = _live_report()
    report["checks"].pop("metadata_complete")

    with pytest.raises(ValueError, match="canonical|checks"):
        _live(report)


def test_live_parser_rejects_incomplete_or_inconsistent_reports() -> None:
    incomplete = _live_report()
    incomplete["cached_api"]["request_count"] = 25
    with pytest.raises(ValueError, match="frozen 26"):
        _live(incomplete)

    inconsistent = _live_report()
    inconsistent["qualified"] = False
    with pytest.raises(ValueError, match="differs from raw"):
        _live(inconsistent)


def test_live_parser_recomputes_roster_latency_metadata_and_digests() -> None:
    wrong_roster = _live_report()
    wrong_roster["cached_api"]["requests"][1]["request_id"] = "cached-5-99"
    with pytest.raises(ValueError, match="request ID|roster"):
        _live(wrong_roster)

    wrong_p95 = _live_report()
    wrong_p95["cached_api"]["requests"][-2]["latency_ms"] = 9_000.0
    with pytest.raises(ValueError, match="p95 differs"):
        _live(wrong_p95)

    wrong_cold_count = _live_report()
    wrong_cold_count["cold"]["records"].pop()
    with pytest.raises(ValueError, match="result_count differs"):
        _live(wrong_cold_count)

    wrong_digest = _live_report()
    wrong_digest["chat_map"]["map_records_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="digest differs"):
        _live(wrong_digest)

    wrong_near_me_page = _live_report()
    wrong_near_me_page["near_me"]["pagination"]["returned_results"] = 0
    with pytest.raises(ValueError, match="checks differ from raw"):
        _live(wrong_near_me_page)

    missing_near_me_fallback = _live_report()
    missing_near_me_fallback["near_me"]["official_fallback_urls"] = []
    with pytest.raises(ValueError, match="checks differ from raw"):
        _live(missing_near_me_fallback)


def test_live_parser_rejects_raw_check_and_cost_mutations() -> None:
    wrong_availability = _live_report()
    wrong_availability["cold"]["unavailable_layers"] = ["incident"]
    with pytest.raises(ValueError, match="checks differ from raw"):
        _live(wrong_availability)

    wrong_check = _live_report()
    wrong_check["checks"]["metadata_complete"] = False
    with pytest.raises(ValueError, match="checks differ from raw"):
        _live(wrong_check)

    injected_cost = _live_report()
    injected_cost["reported_cost_usd"] = 0.0
    with pytest.raises(ValueError, match="canonical schema"):
        _live(injected_cost)


def test_sealed_parser_accepts_a_complete_required_after_only_report() -> None:
    parsed = _retrieval_qualification(_sealed_report())

    assert parsed["status"] == "complete"
    assert parsed["qualified"] is True
    assert parsed["repetitions"] == 3
    assert parsed["min_recall_at_5"] == pytest.approx(46 / 47)


def test_development_retrieval_recomputes_aggregates_from_ranking_ids() -> None:
    report = _development_retrieval_report()
    parsed = _development_retrieval(report)

    assert parsed["case_count"] == 50
    assert parsed["recall_at_5"] == 1.0
    report["candidates"]["current"]["stages"]["reranked"]["recall"] = 0.5
    with pytest.raises(ValueError, match="differs from case-level rankings"):
        _development_retrieval(report)


def test_sealed_parser_rejects_tampered_case_level_ranking_aggregate() -> None:
    report = _sealed_report()
    report["repetition_reports"][0]["recall_at_5"] = 1.0

    with pytest.raises(ValueError, match="differs from case-level rankings"):
        _retrieval_qualification(report)


def test_sealed_parser_rejects_unknown_or_duplicate_ranking_ids() -> None:
    unknown = _sealed_report()
    unknown["repetition_reports"][0]["rows"][0]["reranked_chunk_ids"] = ["invented-chunk"]
    with pytest.raises(ValueError, match="unknown ranking IDs"):
        _retrieval_qualification(unknown)

    duplicate = _sealed_report()
    ranking = duplicate["repetition_reports"][0]["rows"][1]["reranked_chunk_ids"]
    duplicate["repetition_reports"][0]["rows"][1]["reranked_chunk_ids"] = ranking * 2
    with pytest.raises(ValueError, match="repeats ranking IDs"):
        _retrieval_qualification(duplicate)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("tuning_allowed", True),
        ("relevance_addendum_used", True),
        ("cost_budget_exceeded", True),
        ("reported_cost_usd", 0.76),
    ],
)
def test_sealed_parser_rejects_protocol_or_budget_violations(field: str, value: object) -> None:
    report = _sealed_report()
    report[field] = value

    with pytest.raises(ValueError):
        _retrieval_qualification(report)


def test_semantic_holdout_recomputes_canonical_double_review() -> None:
    manifest, report, bundle = _semantic_holdout_evidence()
    parsed = _validate_semantic_holdout_payloads(manifest, report, bundle)

    assert parsed["status"] == "complete"
    assert parsed["summary_version"] == "firelens_semantic_holdout_summary.v3"
    assert parsed["case_count"] == 25
    assert parsed["claim_count"] == 25
    assert parsed["independent_review_count"] == 50
    assert parsed["approved_case_count"] == 25
    assert parsed["reviewers"] == ["Domain Expert A", "Domain Expert B"]
    assert parsed["adjudicator"] == "Domain Adjudicator"
    assert parsed["claim_label_agreement_rate"] == 1.0
    assert parsed["claim_label_cohens_kappa"] == 1.0
    assert parsed["qualified"] is True
    assert parsed["unsupported_or_unclear"] == 0
    assert parsed["dangerous_omission_count"] == 0
    assert parsed["presentation_event_count"] == 75
    assert parsed["development_registry_sha256"] == "4" * 64


def test_semantic_holdout_validates_actual_artifact_hash_chain_and_optional_summary(
    tmp_path: Path,
) -> None:
    (
        report_path,
        bundle_path,
        manifest_path,
        development_registry_path,
        summary_path,
    ) = _write_semantic_holdout_evidence(tmp_path, include_summary=True)

    parsed = validate_semantic_holdout(
        report_path,
        bundle_path,
        manifest_path,
        development_registry_path,
        summary_path,
    )

    assert parsed["candidate_report_sha256"] == upgrade_benchmark.file_sha256(report_path)
    assert parsed["review_bundle_sha256"] == upgrade_benchmark.file_sha256(bundle_path)
    assert parsed["dataset_manifest_sha256"] == upgrade_benchmark.file_sha256(manifest_path)
    assert parsed["development_registry_sha256"] == upgrade_benchmark.file_sha256(
        development_registry_path
    )
    assert parsed["qualified"] is True


def test_semantic_holdout_rejects_candidate_report_tampered_after_review(
    tmp_path: Path,
) -> None:
    report_path, bundle_path, manifest_path, development_registry_path, _ = (
        _write_semantic_holdout_evidence(tmp_path)
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["cases"][0]["response"] = "Substituted response."
    report["cases"][0]["response_sha256"] = hashlib.sha256(
        report["cases"][0]["response"].encode()
    ).hexdigest()
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    with pytest.raises(ValueError, match="does not match the candidate report"):
        validate_semantic_holdout(
            report_path, bundle_path, manifest_path, development_registry_path
        )


def test_semantic_holdout_rejects_manifest_roster_tampering(tmp_path: Path) -> None:
    report_path, bundle_path, manifest_path, development_registry_path, _ = (
        _write_semantic_holdout_evidence(tmp_path)
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["case_roster"][0]["input_sha256"] = "a" * 64
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    with pytest.raises(ValueError, match="case-roster digest"):
        validate_semantic_holdout(
            report_path, bundle_path, manifest_path, development_registry_path
        )


def test_semantic_holdout_recomputes_source_and_family_disjointness() -> None:
    development_registry = _semantic_development_registry_payload()
    manifest = _semantic_holdout_manifest_payload()

    parsed = upgrade_benchmark._semantic_holdout_manifest_payload(
        manifest,
        development_registry=development_registry,
        development_registry_sha256="4" * 64,
    )

    assert parsed["disjointness_audit"]["source_overlap_id_sha256s"] == []
    assert parsed["disjointness_audit"]["question_family_overlap_ids"] == []


@pytest.mark.parametrize("overlap_kind", ["source", "question_family"])
def test_semantic_holdout_rejects_falsely_asserted_disjointness(
    overlap_kind: str,
) -> None:
    development_registry = _semantic_development_registry_payload()
    manifest = _semantic_holdout_manifest_payload()
    if overlap_kind == "source":
        manifest["case_roster"][0]["source_id_sha256s"] = [
            development_registry["source_id_sha256s"][0]
        ]
        source_roster = sorted(
            {source for row in manifest["case_roster"] for source in row["source_id_sha256s"]}
        )
        manifest["source_id_sha256s"] = source_roster
        manifest["source_roster_sha256"] = upgrade_benchmark._sha256_json(source_roster)
        manifest["disjointness_audit"]["holdout_source_roster_sha256"] = manifest[
            "source_roster_sha256"
        ]
        message = "source-overlap audit"
    else:
        manifest["case_roster"][0]["question_family_id"] = development_registry[
            "question_family_ids"
        ][0]
        family_roster = sorted({row["question_family_id"] for row in manifest["case_roster"]})
        manifest["question_family_ids"] = family_roster
        manifest["question_family_roster_sha256"] = upgrade_benchmark._sha256_json(
            family_roster
        )
        manifest["question_family_distribution"] = {
            family: sum(row["question_family_id"] == family for row in manifest["case_roster"])
            for family in family_roster
        }
        manifest["disjointness_audit"]["holdout_question_family_roster_sha256"] = manifest[
            "question_family_roster_sha256"
        ]
        message = "question-family-overlap audit"
    manifest["case_roster_sha256"] = upgrade_benchmark._sha256_json(manifest["case_roster"])

    with pytest.raises(ValueError, match=message):
        upgrade_benchmark._semantic_holdout_manifest_payload(
            manifest,
            development_registry=development_registry,
            development_registry_sha256="4" * 64,
        )


def test_semantic_holdout_rejects_rewritten_development_registry(tmp_path: Path) -> None:
    report_path, bundle_path, manifest_path, development_registry_path, _ = (
        _write_semantic_holdout_evidence(tmp_path)
    )
    development_registry = json.loads(development_registry_path.read_text(encoding="utf-8"))
    development_registry["frozen_at"] = "2026-08-06T08:01:00+00:00"
    development_registry_path.write_text(
        json.dumps(development_registry, indent=2), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="does not bind the development registry"):
        validate_semantic_holdout(
            report_path, bundle_path, manifest_path, development_registry_path
        )


def test_semantic_holdout_rejects_broken_presentation_hash_chain() -> None:
    manifest, report, bundle = _semantic_holdout_evidence()
    event = bundle["presentation_log"]["events"][0]
    event["presented_at"] = "2026-08-06T10:01:00.500000+00:00"
    event["event_sha256"] = upgrade_benchmark._semantic_presentation_event_sha256(event)

    with pytest.raises(ValueError, match="presentation hash chain is broken"):
        _validate_semantic_holdout_payloads(manifest, report, bundle)


def test_semantic_holdout_rejects_review_without_matching_presentation() -> None:
    manifest, report, bundle = _semantic_holdout_evidence()
    bundle["cases"][0]["independent_reviews"][0]["presentation_event_sha256"] = "a" * 64

    with pytest.raises(ValueError, match="review is not bound to its presentation"):
        _validate_semantic_holdout_payloads(manifest, report, bundle)


def test_semantic_holdout_rejects_incomplete_presentation_exposure_roster() -> None:
    manifest, report, bundle = _semantic_holdout_evidence()
    bundle["presentation_log"]["events"].pop()
    bundle["presentation_log"]["event_count"] -= 1

    with pytest.raises(ValueError, match="incomplete event roster"):
        _validate_semantic_holdout_payloads(manifest, report, bundle)


def test_semantic_holdout_rejects_candidate_identity_as_blinded_label() -> None:
    manifest, report, bundle = _semantic_holdout_evidence()
    bundle["presentation"]["blinded_candidate_label"] = report["candidate_id"]

    with pytest.raises(ValueError, match="exposes the candidate identity"):
        _validate_semantic_holdout_payloads(manifest, report, bundle)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("candidate_identity", "candidate identity"),
        ("unblinded", "requires candidate_identity_blinded"),
        ("unrandomized", "requires randomized"),
        ("presentation_roster", "actor presentation order"),
        ("duplicate_reviewers", "reviewer IDs must be unique"),
        ("late_review", "adjudicated before reviews"),
        ("unlocked_reviews", "reviewer decisions were not locked"),
        ("changed_review_after_lock", "independent-review digest"),
        ("missing_claim_label", "every exact claim"),
        ("unresolved", "remains unresolved"),
        ("wrong_adjudicator", "wrong adjudicator"),
    ],
)
def test_semantic_holdout_rejects_protocol_and_adjudication_mutations(
    mutation: str, message: str
) -> None:
    manifest, report, bundle = _semantic_holdout_evidence()
    case = bundle["cases"][0]
    if mutation == "candidate_identity":
        report["candidate_id"] = "substituted-candidate"
    elif mutation == "unblinded":
        bundle["presentation"]["candidate_identity_blinded"] = False
    elif mutation == "unrandomized":
        bundle["presentation"]["randomized"] = False
    elif mutation == "presentation_roster":
        bundle["presentation"]["actor_orders"][0]["case_ids"][0] = "unknown-case"
    elif mutation == "duplicate_reviewers":
        bundle["reviewer_registry"][1]["reviewer_id"] = "reviewer-a"
    elif mutation == "late_review":
        case["independent_reviews"][1]["reviewed_at"] = "2026-08-06T12:30:00+00:00"
        case["adjudication"]["independent_reviews_sha256"] = upgrade_benchmark._sha256_json(
            case["independent_reviews"]
        )
    elif mutation == "unlocked_reviews":
        case["adjudication"]["reviewer_decisions_locked"] = False
    elif mutation == "changed_review_after_lock":
        case["independent_reviews"][0]["claim_labels"][0]["label"] = "unclear"
        case["independent_reviews"][0]["case_decision"] = "rejected"
    elif mutation == "missing_claim_label":
        case["independent_reviews"][0]["claim_labels"] = []
        case["adjudication"]["independent_reviews_sha256"] = upgrade_benchmark._sha256_json(
            case["independent_reviews"]
        )
    elif mutation == "unresolved":
        case["adjudication"]["resolution_status"] = "unresolved"
    else:
        case["adjudication"]["adjudicator_id"] = "someone-else"

    with pytest.raises(ValueError, match=message):
        _validate_semantic_holdout_payloads(manifest, report, bundle)


@pytest.mark.parametrize("final_label", ["unsupported", "unclear"])
def test_semantic_holdout_recomputes_failed_claim_findings(final_label: str) -> None:
    manifest, report, bundle = _semantic_holdout_evidence()
    adjudication = bundle["cases"][0]["adjudication"]
    adjudication["claim_labels"][0]["label"] = final_label
    adjudication["case_decision"] = "rejected"

    parsed = _validate_semantic_holdout_payloads(manifest, report, bundle)

    assert parsed["approved_case_count"] == 24
    assert parsed["unsupported_or_unclear"] == 1
    assert parsed["qualified"] is False


def test_semantic_holdout_recomputes_dangerous_omission_failure() -> None:
    manifest, report, bundle = _semantic_holdout_evidence()
    adjudication = bundle["cases"][0]["adjudication"]
    adjudication["dangerous_omission"] = True
    adjudication["case_decision"] = "rejected"

    parsed = _validate_semantic_holdout_payloads(manifest, report, bundle)

    assert parsed["approved_case_count"] == 24
    assert parsed["dangerous_omission_count"] == 1
    assert parsed["qualified"] is False


def test_semantic_holdout_rejects_summary_that_differs_from_recomputation() -> None:
    manifest, report, bundle = _semantic_holdout_evidence()
    recomputed = _validate_semantic_holdout_payloads(manifest, report, bundle)
    summary = {key: value for key, value in recomputed.items() if key != "status"}
    summary["approved_case_count"] = 24

    with pytest.raises(ValueError, match="summary differs from raw validated evidence"):
        _validate_semantic_holdout_payloads(manifest, report, bundle, summary)


def test_semantic_holdout_rejects_noncanonical_extra_fields() -> None:
    manifest, report, bundle = _semantic_holdout_evidence()
    report["copied_aggregate"] = {"qualified": True}

    with pytest.raises(ValueError, match="canonical schema"):
        _validate_semantic_holdout_payloads(manifest, report, bundle)


def test_preview_parser_accepts_exact_canonical_evidence(tmp_path: Path) -> None:
    report = _preview_report()
    raw_artifact = _write_preview_raw_artifact(report, tmp_path / "preview-raw.json")
    parsed = _preview(report, raw_response_artifact=raw_artifact)

    assert parsed == {
        "status": "complete",
        "commit": "a" * 40,
        "deployment_id": "preview-1",
        "qualified": True,
        "checks": report["checks"],
    }


def test_preview_parser_rejects_extra_checks_or_missing_deployment_identity() -> None:
    extra_check = _preview_report()
    extra_check["checks"]["self_attested_only"] = True
    with pytest.raises(ValueError, match="canonical checks"):
        _preview(extra_check)

    missing_identity = _preview_report()
    missing_identity["observed"]["deployment_id"] = ""
    with pytest.raises(ValueError, match="deployment identity"):
        _preview(missing_identity)


def test_preview_parser_requires_https_and_all_eight_requests() -> None:
    insecure = _preview_report()
    insecure["base_url"] = "http://preview.example.test"
    with pytest.raises(ValueError, match="HTTPS"):
        _preview(insecure)

    incomplete = _preview_report()
    incomplete["requests"].pop()
    with pytest.raises(ValueError, match="eight canonical requests"):
        _preview(incomplete)


def test_preview_parser_recomputes_roster_status_identity_and_p95() -> None:
    changed_prompt = _preview_report()
    static = next(row for row in changed_prompt["requests"] if row["case_id"] == "static")
    static["request"]["question"] = "A substituted prompt"
    with pytest.raises(ValueError, match="roster|canonical"):
        _preview(changed_prompt)

    wrong_content_type = _preview_report()
    homepage = next(
        row for row in wrong_content_type["requests"] if row["case_id"] == "homepage"
    )
    homepage["response_content_type"] = "application/json"
    with pytest.raises(ValueError, match="content type"):
        _preview(wrong_content_type)

    wrong_identity = _preview_report()
    readiness = next(row for row in wrong_identity["requests"] if row["case_id"] == "readiness")
    readiness["response"]["build_commit"] = "b" * 40
    with pytest.raises(ValueError, match="differs from readiness evidence"):
        _preview(wrong_identity)

    wrong_p95 = _preview_report()
    live = next(row for row in wrong_p95["requests"] if row["case_id"] == "live")
    live["latency_ms"] = 9_000.0
    with pytest.raises(ValueError, match="p95 differs"):
        _preview(wrong_p95)


def test_preview_parser_rejects_response_count_hash_and_support_mutations() -> None:
    wrong_count = _preview_report()
    live = next(row for row in wrong_count["requests"] if row["case_id"] == "live")
    live["response"]["claim_count"] = 1
    with pytest.raises(ValueError, match="checks differ from raw"):
        _preview(wrong_count)

    malformed_body_digest = _preview_report()
    malformed_body_digest["requests"][0]["response_body_sha256"] = "not-a-digest"
    with pytest.raises(ValueError, match="SHA-256"):
        _preview(malformed_body_digest)

    wrong_support_digest = _preview_report()
    static = next(row for row in wrong_support_digest["requests"] if row["case_id"] == "static")
    static["response"]["exact_support"]["claims"][0]["supports"][0]["quote_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="digests differ"):
        _preview(wrong_support_digest)

    wrong_support_offset = _preview_report()
    static = next(row for row in wrong_support_offset["requests"] if row["case_id"] == "static")
    static["response"]["exact_support"]["claims"][0]["supports"][0]["match_end"] += 1
    with pytest.raises(ValueError, match="offsets differ"):
        _preview(wrong_support_offset)


def test_preview_parser_rejects_unsafe_scope_redirect_payload() -> None:
    unsafe = _preview_report()
    unsupported = next(
        row for row in unsafe["requests"] if row["case_id"] == "unsupported"
    )
    unsupported["response"]["claim_count"] = 1

    with pytest.raises(ValueError, match="checks differ from raw"):
        _preview(unsafe)


def test_preview_parser_rejects_non_incident_map_records() -> None:
    non_incident = _preview_report()
    map_request = next(row for row in non_incident["requests"] if row["case_id"] == "map")
    map_request["response"]["records"] = [
        dict(record) for record in map_request["response"]["records"]
    ]
    map_request["response"]["records"][0] = {
        **map_request["response"]["records"][0],
        "kind": "perimeter",
    }

    with pytest.raises(ValueError, match="checks differ from raw"):
        _preview(non_incident)


def test_preview_parser_rejects_incident_status_mismatch_between_chat_and_map() -> None:
    mismatch = _preview_report()
    map_request = next(row for row in mismatch["requests"] if row["case_id"] == "map")
    map_request["response"]["records"] = [
        dict(record) for record in map_request["response"]["records"]
    ]
    map_request["response"]["records"][0] = {
        **map_request["response"]["records"][0],
        "status": "Being Held",
    }

    with pytest.raises(ValueError, match="checks differ from raw"):
        _preview(mismatch)


def test_preview_parser_rejects_missing_perimeter_from_map() -> None:
    missing = _preview_report()
    map_request = next(row for row in missing["requests"] if row["case_id"] == "map")
    records = map_request["response"]["records"][:-1]
    map_request["response"]["records"] = records
    map_request["response"]["record_count"] = len(records)

    with pytest.raises(ValueError, match="checks differ from raw"):
        _preview(missing)


def test_preview_parser_rejects_perimeter_status_mismatch_between_chat_and_map() -> None:
    mismatch = _preview_report()
    map_request = next(row for row in mismatch["requests"] if row["case_id"] == "map")
    map_request["response"]["records"] = [
        dict(record) for record in map_request["response"]["records"]
    ]
    map_request["response"]["records"][-1] = {
        **map_request["response"]["records"][-1],
        "status": "Retired",
    }

    with pytest.raises(ValueError, match="checks differ from raw"):
        _preview(mismatch)


def test_preview_parser_rejects_summary_flag_and_cost_mutations() -> None:
    wrong_check = _preview_report()
    wrong_check["checks"]["static_grounded"] = False
    with pytest.raises(ValueError, match="checks differ from raw"):
        _preview(wrong_check)

    wrong_qualified = _preview_report()
    wrong_qualified["qualified"] = False
    with pytest.raises(ValueError, match="qualified flag differs"):
        _preview(wrong_qualified)

    injected_cost = _preview_report()
    injected_cost["reported_cost_usd"] = 0.0
    with pytest.raises(ValueError, match="canonical schema"):
        _preview(injected_cost)


def test_deployment_parser_accepts_cross_region_rate_limit_and_rollback_proof(
    tmp_path: Path,
) -> None:
    report = _deployment_report()
    rate_limit_path, rollback_path = _write_deployment_evidence(tmp_path, report)
    parsed = _deployment(
        report,
        rate_limit_artifact=rate_limit_path,
        rollback_artifact=rollback_path,
    )

    assert parsed["status"] == "complete"
    assert parsed["distributed_rate_limit_verified"] is True
    assert parsed["rollback_rehearsal_passed"] is True
    assert parsed["candidate_deployment_id"] == "candidate-a"
    assert parsed["restored_deployment_id"] == "previous-a"


def test_deployment_parser_rejects_first_rejection_ordinal_that_was_not_rejected(
    tmp_path: Path,
) -> None:
    report = _deployment_report()
    report["rate_limit_evidence"]["first_rejected_combined_ordinal"] = 1
    rate_limit_path, rollback_path = _write_deployment_evidence(tmp_path, report)

    with pytest.raises(ValueError, match="first rejected ordinal"):
        _deployment(
            report,
            rate_limit_artifact=rate_limit_path,
            rollback_artifact=rollback_path,
        )


def test_deployment_parser_rejects_an_earlier_observed_rejection(tmp_path: Path) -> None:
    report = _deployment_report()
    report["rate_limit_evidence"]["observations"].insert(
        1,
        {
            "client_id": "client-a",
            "region": "iad1",
            "observed_at": "2026-08-06T12:00:00.500000+00:00",
            "combined_ordinal": 2,
            "status_code": 429,
        },
    )
    rate_limit_path, rollback_path = _write_deployment_evidence(tmp_path, report)

    with pytest.raises(ValueError, match="first rejected ordinal"):
        _deployment(
            report,
            rate_limit_artifact=rate_limit_path,
            rollback_artifact=rollback_path,
        )


def test_deployment_parser_rejects_same_deployment_rollback(tmp_path: Path) -> None:
    report = _deployment_report()
    report["rollback_evidence"]["restored_deployment_id"] = "candidate-a"
    rate_limit_path, rollback_path = _write_deployment_evidence(tmp_path, report)

    with pytest.raises(ValueError, match="distinct deployment"):
        _deployment(
            report,
            rate_limit_artifact=rate_limit_path,
            rollback_artifact=rollback_path,
        )


def test_deployment_parser_requires_rollback_environment_snapshots(
    tmp_path: Path,
) -> None:
    report = _deployment_report()
    del report["rollback_evidence"]["candidate_environment_snapshot"]
    rate_limit_path, rollback_path = _write_deployment_evidence(tmp_path, report)

    with pytest.raises(ValueError, match="environment snapshot"):
        _deployment(
            report,
            rate_limit_artifact=rate_limit_path,
            rollback_artifact=rollback_path,
        )


def test_deployment_parser_rejects_single_client_rate_limit_attestation(
    tmp_path: Path,
) -> None:
    report = _deployment_report()
    report["rate_limit_evidence"]["observations"][1]["client_id"] = "client-a"
    rate_limit_path, rollback_path = _write_deployment_evidence(tmp_path, report)

    with pytest.raises(ValueError, match="rate-limit proof is incomplete"):
        _deployment(
            report,
            rate_limit_artifact=rate_limit_path,
            rollback_artifact=rollback_path,
        )


def test_deployment_parser_requires_raw_artifacts_for_positive_proof() -> None:
    with pytest.raises(ValueError, match="raw artifact is required"):
        _deployment(_deployment_report())


def test_deployment_parser_rejects_tampered_or_unbound_raw_artifacts(
    tmp_path: Path,
) -> None:
    report = _deployment_report()
    rate_limit_path, rollback_path = _write_deployment_evidence(tmp_path, report)
    rate_limit_path.write_text('{"tampered": true}', encoding="utf-8")

    with pytest.raises(ValueError, match="digest does not match"):
        _deployment(
            report,
            rate_limit_artifact=rate_limit_path,
            rollback_artifact=rollback_path,
        )

    report = _deployment_report()
    rate_limit_path, rollback_path = _write_deployment_evidence(tmp_path, report)
    report["rate_limit_evidence"]["rule_id"] = "substituted-after-hash"
    with pytest.raises(ValueError, match="does not match embedded evidence"):
        _deployment(
            report,
            rate_limit_artifact=rate_limit_path,
            rollback_artifact=rollback_path,
        )
