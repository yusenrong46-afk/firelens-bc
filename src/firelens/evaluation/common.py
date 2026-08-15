"""Shared deterministic helpers for evaluation evidence validators."""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, overload

import yaml

ROOT = Path(__file__).resolve().parents[3]


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_json(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


def assert_recomputed_summary_matches(
    submitted: dict[str, Any], recomputed: dict[str, Any], *, context: str
) -> None:
    submitted_evidence = {
        key: value for key, value in submitted.items() if key != "generated_at"
    }
    recomputed_evidence = {
        key: value for key, value in recomputed.items() if key != "generated_at"
    }
    if submitted_evidence != recomputed_evidence:
        raise ValueError(f"{context} summary differs from raw validated evidence")


def read_report(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.is_file():
        return None
    raw = path.read_text(encoding="utf-8")
    payload = yaml.safe_load(raw) if path.suffix in {".yaml", ".yml"} else json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return payload


def p95(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, min(len(ordered) - 1, math.ceil(len(ordered) * 0.95) - 1))]


def strict_bool(payload: dict[str, Any], key: str, context: str) -> bool:
    value = payload.get(key)
    if type(value) is not bool:
        raise ValueError(f"{context} {key} must be a strict boolean")
    return value


def strict_int(
    payload: dict[str, Any],
    key: str,
    context: str,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{context} {key} must be an integer")
    if minimum is not None and value < minimum:
        raise ValueError(f"{context} {key} must be at least {minimum}")
    if maximum is not None and value > maximum:
        raise ValueError(f"{context} {key} must be at most {maximum}")
    return value


def strict_number(
    payload: dict[str, Any],
    key: str,
    context: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{context} {key} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{context} {key} must be finite")
    if minimum is not None and number < minimum:
        raise ValueError(f"{context} {key} must be at least {minimum}")
    if maximum is not None and number > maximum:
        raise ValueError(f"{context} {key} must be at most {maximum}")
    return number


def run_logged(command: list[str], log_path: Path) -> dict[str, Any]:
    started = time.perf_counter()
    completed = subprocess.run(
        command,
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(completed.stdout + completed.stderr, encoding="utf-8")
    return {
        "command": command,
        "exit_code": completed.returncode,
        "passed": completed.returncode == 0,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "log_path": str(log_path.relative_to(ROOT)),
        "log_sha256": file_sha256(log_path),
    }


def require_exact_keys(payload: dict[str, Any], expected: set[str], *, context: str) -> None:
    actual = set(payload)
    if actual == expected:
        return
    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    raise ValueError(
        f"{context} does not match the canonical schema; "
        f"missing={missing}, unexpected={unexpected}"
    )


ROLLBACK_ENVIRONMENT_SNAPSHOT_KEYS = {
    "release_version",
    "build_commit",
    "candidate_id",
    "embedding_model",
    "rerank_model",
    "generation_model",
    "data_collection",
    "allow_fallbacks",
    "require_parameters",
    "embedding_zdr",
    "reranking_zdr",
    "generation_zdr",
}


def require_environment_snapshot(value: Any, *, commit: str, context: str) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"{context} environment snapshot must be an object")
    require_exact_keys(value, ROLLBACK_ENVIRONMENT_SNAPSHOT_KEYS, context=context)
    if value.get("build_commit") != commit:
        raise ValueError(f"{context} environment snapshot build commit does not match")
    if value.get("data_collection") != "deny":
        raise ValueError(f"{context} environment snapshot data_collection is invalid")
    if value.get("allow_fallbacks") != "false":
        raise ValueError(f"{context} environment snapshot allow_fallbacks is invalid")
    if value.get("require_parameters") != "true":
        raise ValueError(f"{context} environment snapshot require_parameters is invalid")
    for field in ("embedding_zdr", "reranking_zdr", "generation_zdr"):
        if value.get(field) not in {"required", "optional"}:
            raise ValueError(f"{context} environment snapshot {field} is invalid")
    if any(not str(value.get(key) or "").strip() for key in ROLLBACK_ENVIRONMENT_SNAPSHOT_KEYS):
        raise ValueError(f"{context} environment snapshot is incomplete")


def blank_environment_snapshot() -> dict[str, None]:
    return {key: None for key in sorted(ROLLBACK_ENVIRONMENT_SNAPSHOT_KEYS)}


def blank_rollback_evidence() -> dict[str, Any]:
    return {
        "candidate_deployment_id": None,
        "candidate_commit": None,
        "restored_deployment_id": None,
        "restored_commit": None,
        "verified_at": None,
        "candidate_artifact_sha256": None,
        "restored_artifact_sha256": None,
        "candidate_environment_snapshot": blank_environment_snapshot(),
        "restored_environment_snapshot": blank_environment_snapshot(),
        "checks": {
            "readiness_restored": None,
            "homepage_anonymous": None,
            "release_identity_restored": None,
            "environment_snapshot_restored": None,
            "grounded_smoke_passed": None,
            "live_smoke_passed": None,
        },
    }


@overload
def require_digest(value: Any, *, context: str, optional: Literal[False] = False) -> str: ...


@overload
def require_digest(value: Any, *, context: str, optional: Literal[True]) -> str | None: ...


def require_digest(value: Any, *, context: str, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{context} must be a lowercase SHA-256 digest")
    return value


def require_nonempty_string(value: Any, *, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context} must be a non-empty string")
    if value != value.strip():
        raise ValueError(f"{context} must not contain leading or trailing whitespace")
    return value


def require_full_git_sha(value: Any, *, context: str) -> str:
    commit = require_nonempty_string(value, context=context)
    if len(commit) != 40 or any(character not in "0123456789abcdef" for character in commit):
        raise ValueError(f"{context} must be a full lowercase Git SHA")
    return commit


def require_timestamp(value: Any, *, context: str) -> datetime:
    raw = require_nonempty_string(value, context=context)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{context} must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{context} must include a timezone")
    return parsed
