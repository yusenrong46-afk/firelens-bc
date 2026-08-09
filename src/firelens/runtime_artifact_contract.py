"""Focused validation helpers for the runtime artifact contract."""

from __future__ import annotations

from typing import Any

from firelens.runtime_artifact_common import RuntimeArtifactError
from firelens.runtime_artifact_common import exact_keys as _exact_keys
from firelens.runtime_artifact_common import logical_path as _logical_path


def validate_prohibited_contract(value: Any) -> None:
    if not isinstance(value, dict):
        raise RuntimeArtifactError("prohibited rules must be an object")
    _exact_keys(
        value,
        {"prefixes", "segments", "basenames", "basename_tokens", "suffixes"},
        context="prohibited rules",
    )
    for field, values in value.items():
        if (
            not isinstance(values, list)
            or any(not isinstance(item, str) or not item for item in values)
            or len(values) != len(set(values))
        ):
            raise RuntimeArtifactError(f"prohibited.{field} must contain unique strings")
    for prefix in value["prefixes"]:
        _logical_path(prefix, context="prohibited prefix")
    mandatory = {
        "prefixes": {
            ".git",
            ".venv",
            "data/evaluation",
            "data/raw",
            "data/sources",
            "docs",
            "output",
            "tests",
        },
        "segments": {
            "adjudication",
            "browser",
            "evaluation",
            "intermediates",
            "node_modules",
            "review",
            "ux",
        },
        "basenames": {".env", "embedding_cache.jsonl"},
        "basename_tokens": {
            "adjudicat",
            "embedding_cache",
            "holdout",
            "owner_review",
            "sealed",
            "ux_review",
        },
        "suffixes": {".lock", ".map", ".pyc"},
    }
    for field, required in mandatory.items():
        if not required.issubset(set(value[field])):
            raise RuntimeArtifactError(f"prohibited.{field} omits mandatory artifact classes")
