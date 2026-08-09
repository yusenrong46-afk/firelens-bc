"""Immutable blind-display contracts and secure review-input parsing primitives."""

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

CHUNK_KEYS = {
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

HOLDOUT_MANIFEST_KEYS = {
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

HOLDOUT_REPORT_KEYS = {
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
