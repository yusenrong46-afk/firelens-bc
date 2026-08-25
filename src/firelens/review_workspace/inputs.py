"""Strict import boundary for blinded human-review inputs.

The importers in this module deliberately build a new, small display contract
instead of passing benchmark reports through to a review surface.  Source files
remain hash/stat bound for later rechecks, while model, provider, candidate,
runtime, automated-verdict, metric, cost, latency, route, mode, and ranking
fields never enter :class:`BlindCasePayload`.
"""

# Compact compatibility imports keep this facade below the production line budget.
# ruff: noqa: I001

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from firelens.benchmark import BenchmarkDataset
from firelens.evaluation.semantic_inputs import (
    _semantic_development_registry_payload,
    _semantic_holdout_manifest_payload,
)
from firelens.review_workspace.input_common import (
    CHUNK_KEYS,
    HOLDOUT_MANIFEST_KEYS,
    HOLDOUT_REPORT_KEYS,
    _COMMIT,
    _CONVERSATION_CASE_KEYS,
    _CONVERSATION_REPORT_KEYS,
    _DIGEST,
    _EVIDENCE_KEYS,
    BlindCasePayload as _BlindCasePayload,
    BlindClaim as _BlindClaim,
    BlindHistoryTurn as _BlindHistoryTurn,
    BlindLocalSourceContext as _BlindLocalSourceContext,
    BlindRubric as _BlindRubric,
    BlindSupport as _BlindSupport,
    ImportedReviewCase as _ImportedReviewCase,
    ImportedReviewSuite as _ImportedReviewSuite,
    InputFileIdentity as _InputFileIdentity,
    ReviewInputError as _ReviewInputError,
    _build_suite,
    _content,
    _digest,
    _duplicate_rejecting_object,
    _exact_keys,
    _nonempty,
    _read_bound_file,
    _read_json,
    _read_yaml,
    _reject_constant,
    _string_tuple,
    _timestamp,
    canonical_sha256 as _canonical_sha256,
    input_file_roster_sha256 as _input_file_roster_sha256,
)
from firelens.review_workspace.input_semantic import (
    validate_private_input as _validate_private_input,
)

BlindCasePayload = _BlindCasePayload
BlindClaim = _BlindClaim
BlindHistoryTurn = _BlindHistoryTurn
BlindLocalSourceContext = _BlindLocalSourceContext
BlindRubric = _BlindRubric
BlindSupport = _BlindSupport
ImportedReviewCase = _ImportedReviewCase
ImportedReviewSuite = _ImportedReviewSuite
InputFileIdentity = _InputFileIdentity
ReviewInputError = _ReviewInputError
canonical_sha256 = _canonical_sha256
input_file_roster_sha256 = _input_file_roster_sha256


def import_conversation_suite(
    report_path: Path,
    *,
    nonqualifying_dry_run: bool = False,
) -> ImportedReviewSuite:
    """Import one current or explicitly nonqualifying V1.1 conversation report."""

    report, report_identity = _read_json(report_path, "conversation_report")
    _exact_keys(report, _CONVERSATION_REPORT_KEYS, "conversation report")
    if report.get("report_version") != "firelens_conversation_benchmark_report.v1_1":
        raise ReviewInputError("conversation report version is unsupported")
    _timestamp(report.get("generated_at"), "conversation report generated_at")
    cases_value = report.get("cases")
    if not isinstance(cases_value, list) or not cases_value:
        raise ReviewInputError("conversation report must contain cases")
    if type(report.get("case_count")) is not int or report["case_count"] != len(cases_value):
        raise ReviewInputError("conversation report case_count is inconsistent")
    if type(report.get("selected_case_count")) is not int or report[
        "selected_case_count"
    ] != len(cases_value):
        raise ReviewInputError("conversation report selected_case_count is inconsistent")
    if (
        type(report.get("complete")) is not bool
        or type(report.get("cost_budget_exceeded")) is not bool
    ):
        raise ReviewInputError("conversation report completion fields must be booleans")

    reasons: list[str] = []
    if report.get("execution_mode") != "live_provider":
        reasons.append("execution_mode_not_live_provider")
    if report.get("complete") is not True:
        reasons.append("report_incomplete")
    if report.get("cost_budget_exceeded") is not False:
        reasons.append("cost_budget_exceeded")
    if len(cases_value) != 50:
        reasons.append("full_50_case_roster_missing")

    identity_fields = (
        "dataset_sha256",
        "corpus_sha256",
        "corpus_manifest_sha256",
        "vector_matrix_sha256",
        "vector_manifest_sha256",
        "document_context_sha256",
        "repairs_sha256",
        "configuration_sha256",
    )
    for key in identity_fields:
        try:
            _digest(report.get(key), f"conversation report {key}")
        except ReviewInputError:
            reasons.append(f"missing_or_invalid_{key}")
    commit = report.get("commit")
    if not isinstance(commit, str) or _COMMIT.fullmatch(commit) is None:
        reasons.append("missing_or_invalid_commit")
    for key in ("dataset_version", "corpus_version"):
        try:
            _nonempty(report.get(key), f"conversation report {key}")
        except ReviewInputError:
            reasons.append(f"missing_or_invalid_{key}")

    imported_cases: list[ImportedReviewCase] = []
    seen_ids: set[str] = set()
    for index, case_value in enumerate(cases_value):
        case = _exact_keys(case_value, _CONVERSATION_CASE_KEYS, f"conversation case {index}")
        case_id = _nonempty(case.get("id"), f"conversation case {index} id")
        if case_id in seen_ids:
            raise ReviewInputError("conversation report repeats case IDs")
        seen_ids.add(case_id)
        question = _content(case.get("question"), f"conversation case {case_id} question")
        history_value = case.get("history")
        if not isinstance(history_value, list):
            raise ReviewInputError(f"conversation case {case_id} history must be an array")
        history: list[BlindHistoryTurn] = []
        for message_index, message_value in enumerate(history_value):
            message = _exact_keys(
                message_value,
                {"role", "content"},
                f"conversation case {case_id} history {message_index}",
            )
            history.append(BlindHistoryTurn.model_validate(message))

        claims_value = case.get("claims")
        evidence_value = case.get("evidence")
        if not isinstance(claims_value, list) or not isinstance(evidence_value, list):
            raise ReviewInputError(f"conversation case {case_id} review material is malformed")
        local_context: list[BlindLocalSourceContext] = []
        evidence_by_id: dict[str, dict[str, Any]] = {}
        source_commitments: set[str] = set()
        for evidence_index, evidence_value_row in enumerate(evidence_value):
            evidence = _exact_keys(
                evidence_value_row,
                _EVIDENCE_KEYS,
                f"conversation case {case_id} evidence {evidence_index}",
            )
            evidence_id = _nonempty(evidence.get("evidence_id"), "evidence ID")
            if evidence_id in evidence_by_id:
                raise ReviewInputError(f"conversation case {case_id} repeats evidence IDs")
            evidence_by_id[evidence_id] = evidence
            source_id = _nonempty(evidence.get("source_id"), "evidence source ID")
            source_commitments.add(hashlib.sha256(source_id.encode("utf-8")).hexdigest())
            context_text = _content(evidence.get("context_text"), "evidence context text")
            local_context.append(
                BlindLocalSourceContext(
                    context_id=evidence_id,
                    title=_nonempty(evidence.get("title"), "evidence title"),
                    publisher=_nonempty(evidence.get("publisher"), "evidence publisher"),
                    locator=(
                        _nonempty(evidence["locator"], "evidence locator")
                        if evidence.get("locator") is not None
                        else None
                    ),
                    text=context_text,
                )
            )
        claims: list[BlindClaim] = []
        supports: list[BlindSupport] = []
        for claim_index, claim_value in enumerate(claims_value):
            claim = _exact_keys(
                claim_value,
                {"claim_id", "text", "evidence_status", "supports"},
                f"conversation case {case_id} claim {claim_index}",
            )
            claim_id = _nonempty(claim.get("claim_id"), "claim ID")
            claims.append(
                BlindClaim(claim_id=claim_id, text=_content(claim.get("text"), "claim text"))
            )
            support_values = claim.get("supports")
            if not isinstance(support_values, list):
                raise ReviewInputError("conversation claim supports must be an array")
            for support_index, support_value in enumerate(support_values):
                support = _exact_keys(
                    support_value,
                    {"evidence_id", "quote"},
                    f"conversation case {case_id} support {support_index}",
                )
                context_id = _nonempty(support.get("evidence_id"), "support evidence ID")
                if context_id not in evidence_by_id:
                    raise ReviewInputError("conversation support references unknown evidence")
                supports.append(
                    BlindSupport(
                        support_id=f"{claim_id}:{support_index + 1}",
                        claim_id=claim_id,
                        context_id=context_id,
                        quote=_content(support.get("quote"), "support quote"),
                    )
                )
        answer = case.get("answer")
        if answer is not None:
            answer = _content(answer, f"conversation case {case_id} answer")
        payload = BlindCasePayload(
            question=question,
            history=tuple(history),
            rubric=BlindRubric(
                required_concepts=_string_tuple(
                    case.get("required_concepts"), "required concepts"
                ),
                forbidden_claims=_string_tuple(
                    case.get("forbidden_claims"), "forbidden claims"
                ),
                required_limitations=_string_tuple(
                    case.get("required_limitations"), "required limitations"
                ),
            ),
            answer=answer,
            claims=tuple(claims),
            supports=tuple(supports),
            local_source_context=tuple(local_context),
        )
        imported_cases.append(
            ImportedReviewCase(
                case_id=case_id,
                payload=payload,
                payload_sha256=canonical_sha256(payload.model_dump(mode="json")),
                source_id_sha256s=tuple(sorted(source_commitments)),
            )
        )

    dataset_digest = report.get("dataset_sha256")
    if not isinstance(dataset_digest, str) or _DIGEST.fullmatch(dataset_digest) is None:
        dataset_digest = report_identity.sha256
    return _build_suite(
        suite_kind="conversation",
        qualifying=not reasons,
        nonqualifying_reasons=reasons,
        nonqualifying_dry_run=nonqualifying_dry_run,
        dataset_sha256=dataset_digest,
        input_files=(report_identity,),
        cases=tuple(imported_cases),
    )


def _read_chunks(
    path: Path,
) -> tuple[dict[str, dict[str, Any]], InputFileIdentity, dict[str, int]]:
    raw, identity = _read_bound_file(path, "governed_corpus")
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise ReviewInputError("governed corpus must be UTF-8 JSONL") from exc
    chunks: dict[str, dict[str, Any]] = {}
    counts: dict[str, int] = {}
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(
                line,
                object_pairs_hook=_duplicate_rejecting_object,
                parse_constant=_reject_constant,
            )
        except (json.JSONDecodeError, ValueError) as exc:
            raise ReviewInputError(
                f"invalid governed corpus record at line {line_number}"
            ) from exc
        chunk = _exact_keys(value, CHUNK_KEYS, f"governed corpus line {line_number}")
        if chunk.get("schema_version") != "chunk_record.v2":
            raise ReviewInputError("governed corpus chunk version is unsupported")
        chunk_id = _nonempty(chunk.get("chunk_id"), "governed chunk ID")
        if chunk_id in chunks:
            raise ReviewInputError("governed corpus repeats chunk IDs")
        text = _content(chunk.get("text"), "governed chunk text")
        if type(chunk.get("char_count")) is not int or chunk["char_count"] != len(text):
            raise ReviewInputError("governed corpus char_count is inconsistent")
        _digest(chunk.get("document_sha256"), "governed chunk document digest")
        _timestamp(chunk.get("retrieved_at"), "governed chunk retrieved_at")
        if chunk.get("review_provenance") not in {"native_text", "human_verified_repair"}:
            raise ReviewInputError("governed chunk has unsupported review provenance")
        source_id = _nonempty(chunk.get("source_id"), "governed chunk source ID")
        counts[source_id] = counts.get(source_id, 0) + 1
        chunks[chunk_id] = chunk
    if not chunks:
        raise ReviewInputError("governed corpus has no chunks")
    return chunks, identity, counts


def _validate_corpus_manifest(
    manifest: dict[str, Any],
    *,
    corpus_path: Path,
    chunks: dict[str, dict[str, Any]],
    source_counts: dict[str, int],
) -> None:
    expected = {
        "combined_chunk_count",
        "combined_chunk_file",
        "corpus_version",
        "generated_at",
        "included_source_count",
        "registry_version",
        "repair_provenance_policy",
        "sources",
    }
    if "provenance_migrated_at" in manifest:
        expected.add("provenance_migrated_at")
    _exact_keys(manifest, expected, "governed corpus manifest")
    _nonempty(manifest.get("corpus_version"), "corpus version")
    _timestamp(manifest.get("generated_at"), "corpus generated_at")
    if "provenance_migrated_at" in manifest:
        _timestamp(manifest.get("provenance_migrated_at"), "corpus provenance_migrated_at")
    if manifest.get("repair_provenance_policy") != "human_verified_only.v1":
        raise ReviewInputError("corpus manifest lacks the governed repair policy")
    if type(manifest.get("combined_chunk_count")) is not int or manifest[
        "combined_chunk_count"
    ] != len(chunks):
        raise ReviewInputError("corpus manifest chunk count is inconsistent")
    declared_file = _nonempty(manifest.get("combined_chunk_file"), "combined chunk file")
    if Path(declared_file).name != corpus_path.name:
        raise ReviewInputError("corpus manifest names a different chunk file")
    sources = manifest.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ReviewInputError("corpus manifest has no source registry")
    governed: dict[str, dict[str, Any]] = {}
    for index, source_value in enumerate(sources):
        if not isinstance(source_value, dict):
            raise ReviewInputError(f"corpus manifest source {index} must be an object")
        source_id = _nonempty(source_value.get("source_id"), "manifest source ID")
        action = source_value.get("corpus_action")
        if action != "include":
            continue
        required = {
            "canonical_url",
            "chunk_count",
            "corpus_action",
            "document_sha256",
            "excluded_record_count",
            "local_file",
            "record_count",
            "review_status",
            "source_id",
            "source_type",
        }
        _exact_keys(source_value, required, f"included corpus source {index}")
        if source_value.get("review_status") != "approved_static":
            raise ReviewInputError("included corpus source is not approved static evidence")
        _digest(source_value.get("document_sha256"), "manifest source document digest")
        if type(source_value.get("chunk_count")) is not int:
            raise ReviewInputError("manifest source chunk_count must be an integer")
        governed[source_id] = source_value
    if type(manifest.get("included_source_count")) is not int or manifest[
        "included_source_count"
    ] != len(governed):
        raise ReviewInputError("corpus manifest included-source count is inconsistent")
    if set(source_counts) != set(governed):
        raise ReviewInputError("governed corpus source roster differs from its manifest")
    for source_id, count in source_counts.items():
        source = governed[source_id]
        if source["chunk_count"] != count:
            raise ReviewInputError("governed corpus per-source count is inconsistent")
        document_hashes = {
            chunk["document_sha256"]
            for chunk in chunks.values()
            if chunk["source_id"] == source_id
        }
        if document_hashes != {source["document_sha256"]}:
            raise ReviewInputError("governed corpus source digest differs from its manifest")


def import_retrieval_suite(
    dataset_path: Path,
    corpus_path: Path,
    corpus_manifest_path: Path,
) -> ImportedReviewSuite:
    """Import frozen relevance labels and governed local chunks, never rankings."""

    dataset_value, dataset_identity = _read_yaml(dataset_path, "retrieval_dataset")
    if any(
        key in dataset_value for key in ("report_version", "metrics", "rankings", "results")
    ):
        raise ReviewInputError(
            "retrieval review input must be a dataset, never a ranking report"
        )
    try:
        dataset = BenchmarkDataset.model_validate(dataset_value)
    except ValueError as exc:
        raise ReviewInputError("retrieval dataset schema is invalid") from exc
    _timestamp(dataset.frozen_at, "retrieval dataset frozen_at")
    chunks, corpus_identity, source_counts = _read_chunks(corpus_path)
    manifest, manifest_identity = _read_json(corpus_manifest_path, "corpus_manifest")
    _validate_corpus_manifest(
        manifest,
        corpus_path=corpus_path,
        chunks=chunks,
        source_counts=source_counts,
    )

    imported_cases: list[ImportedReviewCase] = []
    for case in dataset.cases:
        if case.split != "holdout" or not case.acceptable_evidence:
            continue
        local_context: list[BlindLocalSourceContext] = []
        supports: list[BlindSupport] = []
        committed_sources: set[str] = set()
        support_index = 0
        seen_chunks: set[str] = set()
        for evidence in case.acceptable_evidence:
            if not evidence.chunk_ids:
                raise ReviewInputError(
                    f"retrieval case {case.id} must bind acceptable evidence to chunk IDs"
                )
            for chunk_id in evidence.chunk_ids:
                if chunk_id in seen_chunks:
                    continue
                chunk = chunks.get(chunk_id)
                if chunk is None or chunk["source_id"] != evidence.source_id:
                    raise ReviewInputError(
                        f"retrieval case {case.id} references unknown governed evidence"
                    )
                seen_chunks.add(chunk_id)
                committed_sources.add(
                    hashlib.sha256(evidence.source_id.encode("utf-8")).hexdigest()
                )
                local_context.append(
                    BlindLocalSourceContext(
                        context_id=chunk_id,
                        title=_nonempty(chunk["title"], "chunk title"),
                        publisher=_nonempty(chunk["publisher"], "chunk publisher"),
                        locator=(
                            _nonempty(chunk["locator"], "chunk locator")
                            if chunk.get("locator") is not None
                            else None
                        ),
                        text=_content(chunk["text"], "chunk text"),
                    )
                )
                support_index += 1
                supports.append(
                    BlindSupport(
                        support_id=f"label-{support_index}",
                        context_id=chunk_id,
                        quote=_content(chunk["text"], "chunk text"),
                    )
                )
        payload = BlindCasePayload(
            question=case.question,
            history=(),
            rubric=BlindRubric(
                required_concepts=tuple(case.required_concepts),
                forbidden_claims=tuple(case.forbidden_claims),
                required_limitations=tuple(case.required_limitations),
            ),
            answer=None,
            claims=(),
            supports=tuple(supports),
            local_source_context=tuple(local_context),
        )
        imported_cases.append(
            ImportedReviewCase(
                case_id=case.id,
                payload=payload,
                payload_sha256=canonical_sha256(payload.model_dump(mode="json")),
                source_id_sha256s=tuple(sorted(committed_sources)),
            )
        )
    if not imported_cases:
        raise ReviewInputError("retrieval dataset has no reviewable holdout cases")
    return _build_suite(
        suite_kind="retrieval",
        qualifying=True,
        nonqualifying_reasons=[],
        nonqualifying_dry_run=False,
        dataset_sha256=dataset_identity.sha256,
        input_files=(dataset_identity, corpus_identity, manifest_identity),
        cases=tuple(imported_cases),
    )


def import_semantic_holdout_suite(
    private_payload_path: Path,
    manifest_path: Path,
    candidate_report_path: Path,
    development_registry_path: Path,
) -> ImportedReviewSuite:
    """Import exact private inputs and a candidate report after commitment checks."""

    private, private_identity = _read_json(private_payload_path, "private_holdout_payload")
    manifest, manifest_identity = _read_json(manifest_path, "holdout_manifest")
    report, report_identity = _read_json(candidate_report_path, "holdout_candidate_report")
    development_registry, development_registry_identity = _read_json(
        development_registry_path, "semantic_development_registry"
    )
    _exact_keys(private, {"payload_version", "dataset_id", "cases"}, "private holdout payload")
    if private.get("payload_version") != "firelens_semantic_holdout_private_payload.v1":
        raise ReviewInputError("private holdout payload version is unsupported")
    _nonempty(private.get("dataset_id"), "private holdout dataset ID")
    private_cases = private.get("cases")
    if not isinstance(private_cases, list) or len(private_cases) < 25:
        raise ReviewInputError("private semantic holdout requires at least 25 cases")

    roster: list[dict[str, Any]] = []
    private_by_id: dict[str, dict[str, Any]] = {}
    aggregate_sources: set[str] = set()
    family_counts: dict[str, int] = {}
    prior_case_id: str | None = None
    for index, case_value in enumerate(private_cases):
        case = _exact_keys(
            case_value,
            {
                "case_id",
                "input_payload",
                "source_id_sha256s",
                "question_family_id",
                "risk_labels",
            },
            f"private holdout case {index}",
        )
        case_id = _nonempty(case.get("case_id"), f"private holdout case {index} ID")
        if prior_case_id is not None and case_id <= prior_case_id:
            raise ReviewInputError("private holdout cases must be sorted and unique")
        prior_case_id = case_id
        review_input = _validate_private_input(
            case.get("input_payload"), f"private case {case_id}"
        )
        sources = _string_tuple(
            case.get("source_id_sha256s"),
            f"private case {case_id} source commitments",
            sorted_unique=True,
        )
        if not sources or any(_DIGEST.fullmatch(item) is None for item in sources):
            raise ReviewInputError("private holdout source commitments are invalid")
        context_sources = sorted(
            {str(row["source_id_sha256"]) for row in review_input["source_context"]}
        )
        if list(sources) != context_sources:
            raise ReviewInputError("private holdout source-context commitments differ")
        family = _nonempty(case.get("question_family_id"), "private question family")
        risk_labels = _string_tuple(
            case.get("risk_labels"), "private risk labels", sorted_unique=True
        )
        if not risk_labels:
            raise ReviewInputError("private holdout requires at least one risk label per case")
        row = {
            "case_id": case_id,
            "input_sha256": canonical_sha256(review_input),
            "source_id_sha256s": list(sources),
            "question_family_id": family,
        }
        roster.append(row)
        private_by_id[case_id] = case
        aggregate_sources.update(sources)
        family_counts[family] = family_counts.get(family, 0) + 1
    if len(family_counts) < 5:
        raise ReviewInputError("private semantic holdout requires five question families")

    _exact_keys(manifest, HOLDOUT_MANIFEST_KEYS, "semantic holdout manifest")
    if manifest.get("manifest_version") != "firelens_semantic_holdout_manifest.v3":
        raise ReviewInputError("semantic holdout manifest version is unsupported")
    _timestamp(manifest.get("frozen_at"), "semantic holdout manifest frozen_at")
    if (
        manifest.get("frozen_before_candidate") is not True
        or manifest.get("double_review_required") is not True
    ):
        raise ReviewInputError("semantic holdout manifest lacks required review guards")
    source_roster = sorted(aggregate_sources)
    family_roster = sorted(family_counts)
    expected_manifest_values = {
        "dataset_sha256": canonical_sha256(private),
        "case_roster_sha256": canonical_sha256(roster),
        "case_count": len(roster),
        "case_roster": roster,
        "source_id_sha256s": source_roster,
        "source_roster_sha256": canonical_sha256(source_roster),
        "question_family_ids": family_roster,
        "question_family_roster_sha256": canonical_sha256(family_roster),
        "question_family_distribution": dict(sorted(family_counts.items())),
    }
    for key, expected in expected_manifest_values.items():
        if manifest.get(key) != expected:
            raise ReviewInputError(
                f"semantic holdout manifest {key} commitment is inconsistent"
            )
    _digest(manifest.get("development_registry_sha256"), "development registry commitment")
    _nonempty(manifest.get("development_registry_id"), "development registry ID")
    if not isinstance(manifest.get("disjointness_audit"), dict):
        raise ReviewInputError("semantic holdout manifest disjointness audit is missing")
    try:
        validated_registry = _semantic_development_registry_payload(development_registry)
        _semantic_holdout_manifest_payload(
            manifest,
            development_registry=validated_registry,
            development_registry_sha256=development_registry_identity.sha256,
        )
    except ValueError as exc:
        raise ReviewInputError(str(exc)) from exc

    _exact_keys(report, HOLDOUT_REPORT_KEYS, "semantic holdout candidate report")
    if report.get("report_version") != "firelens_semantic_holdout_report.v1":
        raise ReviewInputError("semantic holdout candidate report version is unsupported")
    generated_at = _timestamp(report.get("generated_at"), "candidate report generated_at")
    if generated_at <= _timestamp(manifest["frozen_at"], "manifest frozen_at"):
        raise ReviewInputError("candidate report must postdate the frozen manifest")
    candidate_id = _nonempty(report.get("candidate_id"), "candidate ID")
    commit = report.get("commit")
    if not isinstance(commit, str) or _COMMIT.fullmatch(commit) is None:
        raise ReviewInputError("candidate report commit is invalid")
    for key in (
        "candidate_identity_sha256",
        "corpus_sha256",
        "vector_matrix_sha256",
        "repairs_sha256",
        "configuration_sha256",
        "dataset_sha256",
        "dataset_manifest_sha256",
    ):
        _digest(report.get(key), f"candidate report {key}")
    _digest(
        report.get("document_context_sha256"),
        "candidate document-context digest",
        optional=True,
    )
    candidate_identity = {
        "candidate_id": candidate_id,
        "commit": commit,
        "corpus_sha256": report["corpus_sha256"],
        "vector_matrix_sha256": report["vector_matrix_sha256"],
        "document_context_sha256": report["document_context_sha256"],
        "repairs_sha256": report["repairs_sha256"],
        "configuration_sha256": report["configuration_sha256"],
    }
    if report["candidate_identity_sha256"] != canonical_sha256(candidate_identity):
        raise ReviewInputError("candidate report identity commitment is inconsistent")
    if report["dataset_sha256"] != manifest["dataset_sha256"]:
        raise ReviewInputError("candidate report targets a different holdout dataset")
    if report["dataset_manifest_sha256"] != manifest_identity.sha256:
        raise ReviewInputError("candidate report targets a different holdout manifest file")
    report_cases = report.get("cases")
    if (
        type(report.get("case_count")) is not int
        or report["case_count"] != len(roster)
        or not isinstance(report_cases, list)
        or len(report_cases) != len(roster)
    ):
        raise ReviewInputError("candidate report case roster is incomplete")

    imported_cases: list[ImportedReviewCase] = []
    for roster_row, report_case_value in zip(roster, report_cases, strict=True):
        report_case = _exact_keys(
            report_case_value,
            {"case_id", "input_sha256", "response", "response_sha256", "claims"},
            "semantic holdout candidate case",
        )
        case_id = roster_row["case_id"]
        if (
            report_case.get("case_id") != case_id
            or report_case.get("input_sha256") != roster_row["input_sha256"]
        ):
            raise ReviewInputError(
                "candidate report case differs from its private input commitment"
            )
        response = _content(report_case.get("response"), f"candidate case {case_id} response")
        if (
            report_case.get("response_sha256")
            != hashlib.sha256(response.encode("utf-8")).hexdigest()
        ):
            raise ReviewInputError("candidate response digest is inconsistent")
        claim_values = report_case.get("claims")
        if not isinstance(claim_values, list) or not claim_values:
            raise ReviewInputError("candidate case has no reviewable claims")
        claims: list[BlindClaim] = []
        seen_claims: set[str] = set()
        for claim_index, claim_value in enumerate(claim_values):
            claim = _exact_keys(
                claim_value,
                {"claim_id", "text", "text_sha256"},
                f"candidate case {case_id} claim {claim_index}",
            )
            claim_id = _nonempty(claim.get("claim_id"), "candidate claim ID")
            if claim_id in seen_claims:
                raise ReviewInputError("candidate case repeats claim IDs")
            seen_claims.add(claim_id)
            claim_text = _content(claim.get("text"), "candidate claim text")
            if (
                claim.get("text_sha256")
                != hashlib.sha256(claim_text.encode("utf-8")).hexdigest()
            ):
                raise ReviewInputError("candidate claim digest is inconsistent")
            claims.append(BlindClaim(claim_id=claim_id, text=claim_text))
        private_case = private_by_id[case_id]
        review_input = private_case["input_payload"]
        local_context = tuple(
            BlindLocalSourceContext(
                context_id=row["context_id"],
                locator=row["locator"],
                text=row["text"],
            )
            for row in review_input["source_context"]
        )
        rubric = review_input["rubric"]
        payload = BlindCasePayload(
            question=review_input["question"],
            history=tuple(
                BlindHistoryTurn.model_validate(row) for row in review_input["history"]
            ),
            rubric=BlindRubric(
                required_concepts=tuple(rubric["required_concepts"]),
                forbidden_claims=tuple(rubric["forbidden_claims"]),
                required_limitations=tuple(rubric["required_limitations"]),
            ),
            answer=response,
            claims=tuple(claims),
            supports=(),
            local_source_context=local_context,
        )
        imported_cases.append(
            ImportedReviewCase(
                case_id=case_id,
                payload=payload,
                payload_sha256=canonical_sha256(payload.model_dump(mode="json")),
                input_sha256=roster_row["input_sha256"],
                source_id_sha256s=tuple(roster_row["source_id_sha256s"]),
            )
        )
    return _build_suite(
        suite_kind="semantic_holdout",
        qualifying=True,
        nonqualifying_reasons=[],
        nonqualifying_dry_run=False,
        dataset_sha256=manifest["dataset_sha256"],
        input_files=(
            private_identity,
            manifest_identity,
            report_identity,
            development_registry_identity,
        ),
        cases=tuple(imported_cases),
    )
