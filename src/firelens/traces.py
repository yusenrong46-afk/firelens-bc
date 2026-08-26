"""Small local JSON traces with secrets and raw content excluded by default."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import threading
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_SAFE_ERROR_TYPES = frozenset(
    {
        "authentication",
        "credits",
        "invalid_request",
        "invalid_response",
        "model_unavailable",
        "no_retrieval_request",
        "rate_limit",
        "safety",
        "timeout",
        "unavailable",
        "unknown",
    }
)
_ENUM_FIELDS = {
    "operation": frozenset({"ask", "search"}),
    "route": frozenset({"capability", "related", "tangent", "live", "prohibited"}),
    "relation": frozenset({"grounded_candidate", "adjacent", "tangent"}),
    "support": frozenset(
        {
            "answerable",
            "partial",
            "insufficient_evidence",
            "requires_live_data",
            "prohibited",
            "conflict",
        }
    ),
    "status": frozenset({"answer", "abstention", "error"}),
    "response_mode": frozenset(
        {
            "grounded",
            "background",
            "capability",
            "scope_redirect",
            "abstention",
            "partial",
            "live",
            "mixed",
            "conflict",
            "requires_input",
        }
    ),
    "reason_code": frozenset(
        {
            "capability_overview",
            "scope_redirect",
            "personalized_safety_decision",
            "personalized_medical_advice",
            "policy_manipulation",
            "live_data_required",
            "planning_unavailable",
            "retrieval_unavailable",
            "retrieval_incomplete",
            "no_approved_evidence",
            "wrong_temporal_class",
            "required_authority_missing",
            "approved_static_evidence",
            "generation_unavailable",
            "draft_validation_failed",
            "model_abstained",
            "conflicting_evidence",
            "high_risk_claim_not_structured",
        }
    ),
    "error_kind": _SAFE_ERROR_TYPES,
}
_COUNT_FIELDS = frozenset(
    {
        "history_turn_count",
        "generation_attempts",
        "repair_count",
        "error_count",
        "cited_evidence_count",
    }
)
_BOOL_FIELDS = frozenset({"generation_model_present"})
_STAGE_COUNT_KEYS = frozenset({"bm25", "vector", "fused", "reranked", "evidence"})
_TIMING_KEYS = frozenset({"planning", "bm25", "vector", "fusion", "rerank"})
_PROVIDER_STAGE_KEYS = frozenset({"planning", "embedding", "rerank"})
_USAGE_KEYS = frozenset(
    {
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "input_tokens",
        "output_tokens",
        "reasoning_tokens",
        "cached_tokens",
        "cost",
    }
)
_VERSION_KEYS = frozenset(
    {
        "corpus",
        "retrieval_text_strategy",
        "embedding_model",
        "rerank_model",
        "generation_model",
    }
)


def _safe_categorical(value: Any, allowed: frozenset[str]) -> str | None:
    if not isinstance(value, str) or value not in allowed:
        return None
    return value


def _safe_number(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _safe_numeric_mapping(
    value: Any, *, allowed_keys: frozenset[str]
) -> dict[str, int | float]:
    if not isinstance(value, Mapping):
        return {}
    return {
        key: number
        for key, raw in value.items()
        if key in allowed_keys and (number := _safe_number(raw)) is not None
    }


def _safe_usage_mapping(value: Any) -> dict[str, dict[str, int | float]]:
    if not isinstance(value, Mapping):
        return {}
    return {
        key: usage
        for key, raw in value.items()
        if key in _PROVIDER_STAGE_KEYS
        and (usage := _safe_numeric_mapping(raw, allowed_keys=_USAGE_KEYS))
    }


def _safe_presence_mapping(value: Any, *, allowed_keys: frozenset[str]) -> dict[str, bool]:
    if not isinstance(value, Mapping):
        return {}
    return {
        key: True
        for key, raw in value.items()
        if key in allowed_keys and (raw is True or isinstance(raw, str))
    }


def _safe_count_mapping(value: Any, *, allowed_keys: frozenset[str]) -> dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    return {
        key: max(raw, 0)
        for key, raw in value.items()
        if key in allowed_keys and isinstance(raw, int) and not isinstance(raw, bool)
    }


def _safe_ranking_counts(value: Any) -> dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    counts: dict[str, int] = {}
    for stage in _STAGE_COUNT_KEYS:
        raw = value.get(stage)
        if isinstance(raw, Sequence) and not isinstance(raw, str):
            counts[stage] = len(raw)
            continue
        if stage not in {"bm25", "vector"}:
            continue
        counts[stage] = sum(
            len(items)
            for key, items in value.items()
            if isinstance(key, str)
            and key.startswith(f"{stage}:")
            and key.removeprefix(f"{stage}:").isdigit()
            and isinstance(items, Sequence)
            and not isinstance(items, str)
        )
    return counts


def _safe_validation(value: Any) -> dict[str, bool | int]:
    if not isinstance(value, Mapping):
        return {}
    validation: dict[str, bool | int] = {}
    if isinstance(value.get("accepted"), bool):
        validation["accepted"] = value["accepted"]
    errors = value.get("errors")
    if isinstance(errors, Sequence) and not isinstance(errors, str):
        validation["error_count"] = len(errors)
    elif isinstance(value.get("error_count"), int):
        validation["error_count"] = max(value["error_count"], 0)
    return validation


def project_ask_trace_details(details: Mapping[str, object]) -> dict[str, object]:
    """Project generation observations without retaining draft-derived text."""

    projected = {
        key: details[key]
        for key in (
            "generation_ms",
            "generation_usage",
            "generation_attempts",
            "repair_count",
        )
        if key in details
    }
    if isinstance(details.get("model"), str):
        projected["generation_model_present"] = True
    cited_ids = details.get("cited_evidence_ids")
    if isinstance(cited_ids, Sequence) and not isinstance(cited_ids, str):
        projected["cited_evidence_count"] = len(cited_ids)
    if validation := _safe_validation(details.get("validation")):
        projected["validation"] = validation
    return projected


def _sanitize_event(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Retain only categorical diagnostics and bounded numeric observations."""

    event: dict[str, Any] = {}
    for key, allowed in _ENUM_FIELDS.items():
        if (enum_value := _safe_categorical(payload.get(key), allowed)) is not None:
            event[key] = enum_value
    for key in _COUNT_FIELDS:
        raw_count = payload.get(key)
        if isinstance(raw_count, int) and not isinstance(raw_count, bool):
            event[key] = max(raw_count, 0)
    for key in _BOOL_FIELDS:
        if isinstance(bool_value := payload.get(key), bool):
            event[key] = bool_value

    for key in ("generation_ms",):
        if (number_value := _safe_number(payload.get(key))) is not None:
            event[key] = max(number_value, 0)

    numeric_mappings = {
        "stage_counts": _STAGE_COUNT_KEYS,
        "timings_ms": _TIMING_KEYS,
        "provider_attempts": _PROVIDER_STAGE_KEYS,
    }
    for key, allowed_keys in numeric_mappings.items():
        if numeric_value := _safe_numeric_mapping(payload.get(key), allowed_keys=allowed_keys):
            event[key] = numeric_value
    if usage_value := _safe_usage_mapping(payload.get("provider_usage")):
        event["provider_usage"] = usage_value
    version_presence = payload.get("version_present", payload.get("versions"))
    if version_value := _safe_presence_mapping(version_presence, allowed_keys=_VERSION_KEYS):
        event["version_present"] = version_value
    provider_presence = payload.get("provider_model_present", payload.get("provider_models"))
    if provider_value := _safe_presence_mapping(
        provider_presence, allowed_keys=_PROVIDER_STAGE_KEYS
    ):
        event["provider_model_present"] = provider_value
    ranking_counts = _safe_count_mapping(
        payload.get("stage_ranking_counts"), allowed_keys=_STAGE_COUNT_KEYS
    ) or _safe_ranking_counts(payload.get("stage_rankings"))
    if ranking_counts:
        event["stage_ranking_counts"] = ranking_counts

    if isinstance(payload.get("model"), str):
        event["generation_model_present"] = True
    if generation_value := _safe_numeric_mapping(
        payload.get("generation_usage"), allowed_keys=_USAGE_KEYS
    ):
        event["generation_usage"] = generation_value

    identifiers = payload.get("cited_evidence_ids")
    if isinstance(identifiers, Sequence) and not isinstance(identifiers, str):
        event["cited_evidence_count"] = len(identifiers)

    errors = payload.get("errors")
    if isinstance(errors, Sequence) and not isinstance(errors, str):
        event["error_count"] = len(errors)
        safe_types = sorted(
            {item for item in errors if isinstance(item, str) and item in _SAFE_ERROR_TYPES}
        )
        if safe_types:
            event["error_types"] = safe_types
    elif error_types := payload.get("error_types"):
        if isinstance(error_types, Sequence) and not isinstance(error_types, str):
            safe_types = sorted(
                {
                    item
                    for item in error_types
                    if isinstance(item, str) and item in _SAFE_ERROR_TYPES
                }
            )
            if safe_types:
                event["error_types"] = safe_types

    if validation := _safe_validation(payload.get("validation")):
        event["validation"] = validation
    return event


class TraceRecorder:
    def __init__(
        self,
        directory: Path,
        *,
        include_content: bool = False,
        max_files: int = 250,
        max_bytes: int = 50 * 1024 * 1024,
    ) -> None:
        self.directory = directory
        self.include_content = include_content
        self.max_files = max_files
        self.max_bytes = max_bytes
        self._lock = threading.Lock()

    async def record(
        self,
        trace_id: str,
        *,
        question: str,
        payload: dict[str, Any],
    ) -> bool:
        try:
            await asyncio.to_thread(
                self._record_sync,
                trace_id,
                question=question,
                payload=payload,
            )
        except OSError:
            return False
        return True

    def _record_sync(
        self,
        trace_id: str,
        *,
        question: str,
        payload: dict[str, Any],
    ) -> None:
        with self._lock:
            self._record_locked(trace_id, question=question, payload=payload)

    def _record_locked(
        self,
        trace_id: str,
        *,
        question: str,
        payload: dict[str, Any],
    ) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"{trace_id}.json"
        now = datetime.now(UTC).isoformat()
        trace: dict[str, Any] = {
            "trace_version": "firelens_trace.v2",
            "trace_id": trace_id,
            "created_at": now,
            "updated_at": now,
            "events": [],
        }
        if path.is_file():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
                if (
                    isinstance(existing, dict)
                    and existing.get("trace_id") == trace_id
                    and isinstance(existing.get("events"), list)
                ):
                    created_at = existing.get("created_at")
                    if isinstance(created_at, str):
                        trace["created_at"] = created_at
                    trace["events"] = [
                        _sanitize_event(event)
                        for event in existing["events"]
                        if isinstance(event, Mapping)
                    ]
                    trace["updated_at"] = now
            except (json.JSONDecodeError, OSError):
                pass
        if self.include_content:
            trace["question"] = question
        trace["events"].append(_sanitize_event(payload))
        serialized = json.dumps(trace, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=self.directory,
            prefix=f".{trace_id}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temp_path = Path(stream.name)
            stream.write(serialized)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.replace(temp_path, path)
        finally:
            temp_path.unlink(missing_ok=True)
        self._enforce_retention(exclude=path)

    def _enforce_retention(self, *, exclude: Path) -> None:
        traces = sorted(
            (
                item
                for item in self.directory.glob("*.json")
                if item.is_file() and item != exclude
            ),
            key=lambda item: item.stat().st_mtime,
        )
        total_bytes = exclude.stat().st_size + sum(item.stat().st_size for item in traces)
        while traces and (len(traces) + 1 > self.max_files or total_bytes > self.max_bytes):
            oldest = traces.pop(0)
            total_bytes -= oldest.stat().st_size
            oldest.unlink(missing_ok=True)
