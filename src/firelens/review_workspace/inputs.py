"""Strict import boundary for blinded human-review inputs.

The importers in this module deliberately build a new, small display contract
instead of passing benchmark reports through to a review surface.  Source files
remain hash/stat bound for later rechecks, while model, provider, candidate,
runtime, automated-verdict, metric, cost, latency, route, mode, and ranking
fields never enter :class:`BlindCasePayload`.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from firelens.benchmark import BenchmarkDataset

_MAX_INPUT_BYTES = 64 * 1024 * 1024
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")


class ReviewInputError(ValueError):
    """An input is unsafe, unsupported, incomplete, or internally inconsistent."""


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class BlindHistoryTurn(_FrozenModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=20_000)


class BlindRubric(_FrozenModel):
    """Semantic criteria only; route, mode, and expected status are excluded."""

    required_concepts: tuple[str, ...] = Field(max_length=100)
    forbidden_claims: tuple[str, ...] = Field(max_length=100)
    required_limitations: tuple[str, ...] = Field(max_length=100)


class BlindClaim(_FrozenModel):
    claim_id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=20_000)


class BlindSupport(_FrozenModel):
    support_id: str = Field(min_length=1, max_length=256)
    claim_id: str | None = Field(default=None, min_length=1, max_length=128)
    context_id: str = Field(min_length=1, max_length=256)
    quote: str = Field(min_length=1, max_length=20_000)


class BlindLocalSourceContext(_FrozenModel):
    context_id: str = Field(min_length=1, max_length=256)
    title: str | None = Field(default=None, min_length=1, max_length=1_000)
    publisher: str | None = Field(default=None, min_length=1, max_length=1_000)
    locator: str | None = Field(default=None, min_length=1, max_length=1_000)
    text: str = Field(min_length=1, max_length=200_000)


class BlindCasePayload(_FrozenModel):
    """The exact candidate material that a reviewer may be shown.

    Keeping the case ID outside this object lets the session protocol record an
    exposure without broadening the display allowlist.
    """

    question: str = Field(min_length=1, max_length=20_000)
    history: tuple[BlindHistoryTurn, ...] = Field(max_length=100)
    rubric: BlindRubric
    answer: str | None = Field(default=None, max_length=200_000)
    claims: tuple[BlindClaim, ...] = Field(max_length=1_000)
    supports: tuple[BlindSupport, ...] = Field(max_length=5_000)
    local_source_context: tuple[BlindLocalSourceContext, ...] = Field(max_length=5_000)

    @model_validator(mode="after")
    def references_are_closed(self) -> BlindCasePayload:
        claim_ids = [claim.claim_id for claim in self.claims]
        context_ids = [context.context_id for context in self.local_source_context]
        support_ids = [support.support_id for support in self.supports]
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("blind payload repeats claim IDs")
        if len(context_ids) != len(set(context_ids)):
            raise ValueError("blind payload repeats local context IDs")
        if len(support_ids) != len(set(support_ids)):
            raise ValueError("blind payload repeats support IDs")
        claim_roster = set(claim_ids)
        context_roster = set(context_ids)
        for support in self.supports:
            if support.claim_id is not None and support.claim_id not in claim_roster:
                raise ValueError("blind support references an unknown claim")
            if support.context_id not in context_roster:
                raise ValueError("blind support references unknown local context")
        return self


class InputFileIdentity(_FrozenModel):
    label: str = Field(min_length=1, max_length=80)
    absolute_path: str = Field(min_length=1, max_length=8_192)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size: int = Field(ge=1, le=_MAX_INPUT_BYTES, strict=True)
    device: int = Field(ge=0, strict=True)
    inode: int = Field(ge=1, strict=True)
    mtime_ns: int = Field(ge=0, strict=True)


class ImportedReviewCase(_FrozenModel):
    case_id: str = Field(min_length=1, max_length=128)
    payload: BlindCasePayload
    payload_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    input_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    source_id_sha256s: tuple[str, ...] = Field(max_length=10_000)

    @model_validator(mode="after")
    def payload_hash_is_exact(self) -> ImportedReviewCase:
        if self.payload_sha256 != canonical_sha256(self.payload.model_dump(mode="json")):
            raise ValueError("imported case payload hash is inconsistent")
        if tuple(sorted(set(self.source_id_sha256s))) != self.source_id_sha256s:
            raise ValueError("source commitments must be sorted and unique")
        if any(_DIGEST.fullmatch(value) is None for value in self.source_id_sha256s):
            raise ValueError("source commitments must be SHA-256 digests")
        return self


class ImportedReviewSuite(_FrozenModel):
    import_version: Literal["firelens_review_input_import.v1"]
    suite_kind: Literal["conversation", "retrieval", "semantic_holdout"]
    qualification_status: Literal["eligible", "nonqualifying_dry_run"]
    nonqualifying_reasons: tuple[str, ...] = Field(max_length=100)
    dataset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    input_files: tuple[InputFileIdentity, ...] = Field(min_length=1, max_length=10)
    cases: tuple[ImportedReviewCase, ...] = Field(min_length=1, max_length=10_000)
    suite_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def suite_identity_is_exact(self) -> ImportedReviewSuite:
        labels = [identity.label for identity in self.input_files]
        case_ids = [case.case_id for case in self.cases]
        if len(labels) != len(set(labels)):
            raise ValueError("input file labels must be unique")
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("imported review case IDs must be unique")
        if self.qualification_status == "eligible" and self.nonqualifying_reasons:
            raise ValueError("eligible imports cannot retain nonqualifying reasons")
        if (
            self.qualification_status == "nonqualifying_dry_run"
            and not self.nonqualifying_reasons
        ):
            raise ValueError("dry-run imports require at least one nonqualifying reason")
        if self.suite_sha256 != _suite_sha256(
            suite_kind=self.suite_kind,
            qualification_status=self.qualification_status,
            nonqualifying_reasons=self.nonqualifying_reasons,
            dataset_sha256=self.dataset_sha256,
            input_files=self.input_files,
            cases=self.cases,
        ):
            raise ValueError("imported review suite hash is inconsistent")
        return self

    def recheck_input_files(self) -> None:
        """Fail if any imported file identity differs from the captured bytes/stat."""

        for expected in self.input_files:
            actual_raw, actual = _read_bound_file(Path(expected.absolute_path), expected.label)
            del actual_raw
            if actual != expected:
                raise ReviewInputError(f"review input identity changed: {expected.label}")

    def case(self, case_id: str) -> ImportedReviewCase:
        for case in self.cases:
            if case.case_id == case_id:
                return case
        raise KeyError(case_id)


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def input_file_roster_sha256(suite: ImportedReviewSuite) -> str:
    return canonical_sha256(
        [
            {"label": item.label, "sha256": item.sha256, "size": item.size}
            for item in suite.input_files
        ]
    )


def _canonical_json_bytes(value: Any) -> bytes:
    try:
        rendered = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise ReviewInputError("review input is not canonical JSON") from exc
    return rendered.encode("utf-8")


def _validate_json_value(value: Any) -> None:
    if value is None or type(value) is bool:
        return
    if isinstance(value, str):
        if unicodedata.normalize("NFC", value) != value or "\x00" in value:
            raise ReviewInputError("review input contains a noncanonical string")
        return
    if isinstance(value, int):
        if abs(value) > 9_007_199_254_740_991:
            raise ReviewInputError("review input contains an unsafe integer")
        return
    if isinstance(value, float):
        if not math.isfinite(value) or (value == 0 and math.copysign(1, value) < 0):
            raise ReviewInputError("review input contains a noncanonical number")
        return
    if isinstance(value, list):
        for item in value:
            _validate_json_value(item)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str) or not key:
                raise ReviewInputError("review input contains an invalid object key")
            _validate_json_value(key)
            _validate_json_value(item)
        return
    raise ReviewInputError("review input contains an unsupported JSON value")


def _duplicate_rejecting_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ReviewInputError("review input contains a duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(_: str) -> None:
    raise ReviewInputError("review input contains a non-finite number")


def _read_bound_file(path: Path, label: str) -> tuple[bytes, InputFileIdentity]:
    absolute = Path(os.path.abspath(os.fspath(path.expanduser())))
    if ".." in path.parts:
        raise ReviewInputError(f"review input path contains parent traversal: {label}")
    flags = os.O_RDONLY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(absolute, flags)
    except OSError as exc:
        raise ReviewInputError(f"cannot open review input: {label}") from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ReviewInputError(f"review input is not a regular file: {label}")
        if before.st_nlink != 1:
            raise ReviewInputError(f"review input has an unexpected hard-link count: {label}")
        if before.st_size < 1 or before.st_size > _MAX_INPUT_BYTES:
            raise ReviewInputError(f"review input size is out of bounds: {label}")
        chunks: list[bytes] = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 1024 * 1024))
            if not chunk:
                raise ReviewInputError(f"review input changed while reading: {label}")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise ReviewInputError(f"review input grew while reading: {label}")
        after = os.fstat(descriptor)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        ) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise ReviewInputError(f"review input changed while reading: {label}")
    finally:
        os.close(descriptor)
    raw = b"".join(chunks)
    return raw, InputFileIdentity(
        label=label,
        absolute_path=os.fspath(absolute),
        sha256=hashlib.sha256(raw).hexdigest(),
        size=len(raw),
        device=after.st_dev,
        inode=after.st_ino,
        mtime_ns=after.st_mtime_ns,
    )


def _read_json(path: Path, label: str) -> tuple[dict[str, Any], InputFileIdentity]:
    raw, identity = _read_bound_file(path, label)
    try:
        payload = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_duplicate_rejecting_object,
            parse_constant=_reject_constant,
        )
    except ReviewInputError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ReviewInputError(f"invalid UTF-8 JSON review input: {label}") from exc
    if not isinstance(payload, dict):
        raise ReviewInputError(f"review JSON root must be an object: {label}")
    _validate_json_value(payload)
    return payload, identity


class _UniqueSafeLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(
    loader: _UniqueSafeLoader, node: yaml.nodes.MappingNode, deep: bool = False
) -> dict[Any, Any]:
    result: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise ReviewInputError("review YAML contains a duplicate key")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_UniqueSafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def _read_yaml(path: Path, label: str) -> tuple[dict[str, Any], InputFileIdentity]:
    raw, identity = _read_bound_file(path, label)
    try:
        payload = yaml.load(raw.decode("utf-8"), Loader=_UniqueSafeLoader)
    except ReviewInputError:
        raise
    except (UnicodeDecodeError, yaml.YAMLError, ValueError) as exc:
        raise ReviewInputError(f"invalid UTF-8 YAML review input: {label}") from exc
    if not isinstance(payload, dict):
        raise ReviewInputError(f"review YAML root must be an object: {label}")
    _validate_json_value(payload)
    return payload, identity


def _exact_keys(value: Any, expected: set[str], context: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise ReviewInputError(f"{context} has an unsupported schema")
    return value


def _nonempty(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ReviewInputError(f"{context} must be a non-empty canonical string")
    if unicodedata.normalize("NFC", value) != value:
        raise ReviewInputError(f"{context} must be NFC normalized")
    return value


def _content(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise ReviewInputError(f"{context} must contain text")
    if unicodedata.normalize("NFC", value) != value:
        raise ReviewInputError(f"{context} must be NFC normalized")
    return value


def _digest(value: Any, context: str, *, optional: bool = False) -> str | None:
    if optional and value is None:
        return None
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise ReviewInputError(f"{context} must be a SHA-256 digest")
    return value


def _timestamp(value: Any, context: str) -> datetime:
    raw = _nonempty(value, context)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReviewInputError(f"{context} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ReviewInputError(f"{context} must include a UTC offset")
    return parsed


def _string_tuple(value: Any, context: str, *, sorted_unique: bool = False) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ReviewInputError(f"{context} must be an array")
    result = tuple(_content(item, context) for item in value)
    if sorted_unique and result != tuple(sorted(set(result))):
        raise ReviewInputError(f"{context} must be sorted and unique")
    return result


def _suite_sha256(
    *,
    suite_kind: str,
    qualification_status: str,
    nonqualifying_reasons: tuple[str, ...],
    dataset_sha256: str,
    input_files: tuple[InputFileIdentity, ...],
    cases: tuple[ImportedReviewCase, ...],
) -> str:
    return canonical_sha256(
        {
            "suite_kind": suite_kind,
            "qualification_status": qualification_status,
            "nonqualifying_reasons": list(nonqualifying_reasons),
            "dataset_sha256": dataset_sha256,
            "input_files": [
                {"label": item.label, "sha256": item.sha256, "size": item.size}
                for item in input_files
            ],
            "cases": [
                {
                    "case_id": case.case_id,
                    "payload_sha256": case.payload_sha256,
                    "input_sha256": case.input_sha256,
                    "source_id_sha256s": list(case.source_id_sha256s),
                }
                for case in cases
            ],
        }
    )


def _build_suite(
    *,
    suite_kind: Literal["conversation", "retrieval", "semantic_holdout"],
    qualifying: bool,
    nonqualifying_reasons: list[str],
    nonqualifying_dry_run: bool,
    dataset_sha256: str,
    input_files: tuple[InputFileIdentity, ...],
    cases: tuple[ImportedReviewCase, ...],
) -> ImportedReviewSuite:
    if qualifying and not nonqualifying_dry_run:
        status: Literal["eligible", "nonqualifying_dry_run"] = "eligible"
        reasons: tuple[str, ...] = ()
    else:
        if not nonqualifying_dry_run:
            detail = ", ".join(nonqualifying_reasons) or "explicit dry-run flag missing"
            raise ReviewInputError(
                "nonqualifying review input requires nonqualifying_dry_run=True: " + detail
            )
        status = "nonqualifying_dry_run"
        reasons = tuple(
            sorted(set(nonqualifying_reasons or ["explicit_nonqualifying_dry_run"]))
        )
    suite_hash = _suite_sha256(
        suite_kind=suite_kind,
        qualification_status=status,
        nonqualifying_reasons=reasons,
        dataset_sha256=dataset_sha256,
        input_files=input_files,
        cases=cases,
    )
    return ImportedReviewSuite(
        import_version="firelens_review_input_import.v1",
        suite_kind=suite_kind,
        qualification_status=status,
        nonqualifying_reasons=reasons,
        dataset_sha256=dataset_sha256,
        input_files=input_files,
        cases=cases,
        suite_sha256=suite_hash,
    )


_CONVERSATION_REPORT_KEYS = {
    "report_version",
    "generated_at",
    "execution_mode",
    "dataset_version",
    "dataset_sha256",
    "commit",
    "corpus_sha256",
    "corpus_manifest_sha256",
    "vector_matrix_sha256",
    "vector_manifest_sha256",
    "document_context_sha256",
    "repairs_sha256",
    "configuration_sha256",
    "runtime_configuration",
    "corpus_version",
    "models",
    "configuration",
    "case_count",
    "selected_case_count",
    "complete",
    "cost_budget_usd",
    "cost_budget_exceeded",
    "metric_definitions",
    "metrics",
    "cases",
}

_CONVERSATION_CASE_KEYS = {
    "id",
    "split",
    "category",
    "risk_level",
    "question",
    "history",
    "expected_route",
    "actual_route",
    "route_correct",
    "expected_planning_relation",
    "actual_planning_relation",
    "planning_relation_correct",
    "expected_status",
    "actual_status",
    "status_correct",
    "expected_response_mode",
    "actual_response_mode",
    "response_mode_correct",
    "expected_evidence_status",
    "actual_evidence_statuses",
    "evidence_status_correct",
    "expected_paid_provider_stages",
    "actual_paid_provider_stages",
    "paid_call_boundary_correct",
    "provider_usage",
    "provider_attempts",
    "provider_models",
    "latency_ms",
    "stage_metrics",
    "followup_resolved",
    "required_concepts",
    "forbidden_claims",
    "required_limitations",
    "required_limitations_correct",
    "missing_required_limitations",
    "literal_forbidden_phrase_hits",
    "background_citation_leak_count",
    "automated_traceability_failure_count",
    "claim_support_floor_failure_count",
    "semantic_adjudication",
    "reason_code",
    "error_kind",
    "answer",
    "claims",
    "evidence",
    "limitations",
    "suggested_questions",
    "validation",
}

_EVIDENCE_KEYS = {
    "evidence_id",
    "primary_chunk_ids",
    "chunk_ids",
    "primary_text",
    "context_text",
    "source_id",
    "title",
    "publisher",
    "canonical_url",
    "page_number",
    "section_title",
    "locator",
    "temporal_class",
    "authority_class",
    "document_sha256",
    "review_provenance",
}


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


_CHUNK_KEYS = {
    "schema_version",
    "chunk_id",
    "parent_record_id",
    "source_id",
    "title",
    "publisher",
    "canonical_url",
    "temporal_class",
    "authority_class",
    "document_sha256",
    "page_number",
    "chunk_index",
    "section_title",
    "text",
    "char_count",
    "retrieved_at",
    "source_type",
    "section_id",
    "locator",
    "review_provenance",
}


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
        chunk = _exact_keys(value, _CHUNK_KEYS, f"governed corpus line {line_number}")
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


def _validate_private_input(value: Any, context: str) -> dict[str, Any]:
    review_input = _exact_keys(
        value,
        {"input_version", "question", "history", "rubric", "source_context"},
        context,
    )
    if review_input.get("input_version") != "firelens_semantic_holdout_review_input.v1":
        raise ReviewInputError("semantic holdout private-review-input version is unsupported")
    _content(review_input.get("question"), f"{context} question")
    history = review_input.get("history")
    if not isinstance(history, list):
        raise ReviewInputError(f"{context} history must be an array")
    for index, message in enumerate(history):
        row = _exact_keys(message, {"role", "content"}, f"{context} history {index}")
        if row.get("role") not in {"user", "assistant"}:
            raise ReviewInputError(f"{context} history role is unsupported")
        _content(row.get("content"), f"{context} history content")
    rubric = _exact_keys(
        review_input.get("rubric"),
        {
            "expected_route",
            "expected_status",
            "required_concepts",
            "forbidden_claims",
            "required_limitations",
        },
        f"{context} rubric",
    )
    _nonempty(rubric.get("expected_route"), f"{context} expected route")
    _nonempty(rubric.get("expected_status"), f"{context} expected status")
    rubric_lists = [
        _string_tuple(rubric.get(key), f"{context} {key}", sorted_unique=True)
        for key in ("required_concepts", "forbidden_claims", "required_limitations")
    ]
    if not any(rubric_lists):
        raise ReviewInputError(f"{context} rubric must contain semantic criteria")
    source_context = review_input.get("source_context")
    if not isinstance(source_context, list) or not source_context:
        raise ReviewInputError(f"{context} source context is missing")
    context_ids: list[str] = []
    for index, source in enumerate(source_context):
        row = _exact_keys(
            source,
            {"context_id", "source_id_sha256", "locator", "text"},
            f"{context} source context {index}",
        )
        context_ids.append(_nonempty(row.get("context_id"), f"{context} context ID"))
        _digest(row.get("source_id_sha256"), f"{context} source commitment")
        _content(row.get("locator"), f"{context} locator")
        _content(row.get("text"), f"{context} source text")
    if context_ids != sorted(set(context_ids)):
        raise ReviewInputError(f"{context} source context must be sorted and unique")
    return review_input


_HOLDOUT_MANIFEST_KEYS = {
    "manifest_version",
    "dataset_sha256",
    "case_roster_sha256",
    "case_count",
    "case_roster",
    "source_id_sha256s",
    "source_roster_sha256",
    "question_family_ids",
    "question_family_roster_sha256",
    "question_family_distribution",
    "development_registry_id",
    "development_registry_sha256",
    "disjointness_audit",
    "frozen_before_candidate",
    "double_review_required",
    "frozen_at",
}

_HOLDOUT_REPORT_KEYS = {
    "report_version",
    "candidate_id",
    "candidate_identity_sha256",
    "generated_at",
    "commit",
    "corpus_sha256",
    "vector_matrix_sha256",
    "document_context_sha256",
    "repairs_sha256",
    "configuration_sha256",
    "dataset_sha256",
    "dataset_manifest_sha256",
    "case_count",
    "cases",
}


def import_semantic_holdout_suite(
    private_payload_path: Path,
    manifest_path: Path,
    candidate_report_path: Path,
) -> ImportedReviewSuite:
    """Import exact private inputs and a candidate report after commitment checks."""

    private, private_identity = _read_json(private_payload_path, "private_holdout_payload")
    manifest, manifest_identity = _read_json(manifest_path, "holdout_manifest")
    report, report_identity = _read_json(candidate_report_path, "holdout_candidate_report")
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

    _exact_keys(manifest, _HOLDOUT_MANIFEST_KEYS, "semantic holdout manifest")
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

    _exact_keys(report, _HOLDOUT_REPORT_KEYS, "semantic holdout candidate report")
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
        input_files=(private_identity, manifest_identity, report_identity),
        cases=tuple(imported_cases),
    )
