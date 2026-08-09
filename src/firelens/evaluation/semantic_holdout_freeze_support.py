"""Canonical parsing and validation for sealed semantic-holdout inputs."""

from __future__ import annotations

import json
import math
import os
import re
import stat
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, NoReturn

from firelens.evaluation.common import sha256_json

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PROTOCOL = ROOT / "data/evaluation/semantic_holdout_freeze_protocol.v1.json"
MAX_INPUT_BYTES = 16 * 1024 * 1024
LOWER_ID = re.compile(r"^[a-z][a-z0-9._-]{1,127}$")
CASE_ID = re.compile(r"^[A-Z][A-Z0-9._-]{2,63}$")
DIGEST = re.compile(r"^[0-9a-f]{64}$")


class FreezeRefusal(ValueError):
    """A refusal whose stable code is safe to show without private values."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _refuse(code: str) -> NoReturn:
    raise FreezeRefusal(code)


def _exact_keys(value: Any, expected: set[str], code: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        _refuse(code)
    return value


def _nonempty_string(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        _refuse(code)
    if unicodedata.normalize("NFC", value) != value:
        _refuse(code)
    return value


def _content_string(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _refuse(code)
    if unicodedata.normalize("NFC", value) != value or "\x00" in value:
        _refuse(code)
    return value


def _lower_identifier(value: Any, code: str) -> str:
    parsed = _nonempty_string(value, code)
    if LOWER_ID.fullmatch(parsed) is None:
        _refuse(code)
    return parsed


def _case_identifier(value: Any, code: str) -> str:
    parsed = _nonempty_string(value, code)
    if CASE_ID.fullmatch(parsed) is None:
        _refuse(code)
    return parsed


def _digest(value: Any, code: str) -> str:
    if not isinstance(value, str) or DIGEST.fullmatch(value) is None:
        _refuse(code)
    return value


def _timestamp(value: Any, code: str) -> datetime:
    parsed_value = _nonempty_string(value, code)
    try:
        parsed = datetime.fromisoformat(parsed_value.replace("Z", "+00:00"))
    except ValueError:
        _refuse(code)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        _refuse(code)
    return parsed


def _sorted_unique_strings(
    value: Any,
    *,
    code: str,
    minimum: int,
    parser: Any = _nonempty_string,
) -> list[str]:
    if not isinstance(value, list) or len(value) < minimum:
        _refuse(code)
    parsed = [parser(item, code) for item in value]
    if parsed != sorted(parsed) or len(parsed) != len(set(parsed)):
        _refuse(code)
    return parsed


def _validate_json_value(value: Any) -> None:
    if value is None or type(value) is bool:
        return
    if isinstance(value, str):
        if unicodedata.normalize("NFC", value) != value or "\x00" in value:
            _refuse("noncanonical_json_value")
        return
    if isinstance(value, int):
        if abs(value) > 9_007_199_254_740_991:
            _refuse("noncanonical_json_number")
        return
    if isinstance(value, float):
        if not math.isfinite(value) or (value == 0.0 and math.copysign(1.0, value) < 0):
            _refuse("noncanonical_json_number")
        return
    if isinstance(value, list):
        for item in value:
            _validate_json_value(item)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            _nonempty_string(key, "noncanonical_json_key")
            _validate_json_value(item)
        return
    _refuse("unsupported_json_value")


def _duplicate_rejecting_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _refuse("duplicate_json_key")
        result[key] = value
    return result


def _reject_constant(_: str) -> None:
    _refuse("noncanonical_json_number")


def _lexical_path(path: Path) -> Path:
    if ".." in path.parts:
        _refuse("parent_path_reference")
    return Path(os.path.abspath(os.fspath(path.expanduser())))


def _assert_no_symlink_components(path: Path, *, leaf_may_be_missing: bool) -> None:
    absolute = _lexical_path(path)
    current = Path(absolute.anchor)
    for index, part in enumerate(absolute.parts[1:], start=1):
        current /= part
        is_leaf = index == len(absolute.parts) - 1
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            if leaf_may_be_missing and is_leaf:
                return
            _refuse("path_component_missing")
        if stat.S_ISLNK(mode):
            _refuse("symlink_path_refused")


def _read_json(path: Path, *, private: bool = False) -> tuple[dict[str, Any], bytes]:
    absolute = _lexical_path(path)
    _assert_no_symlink_components(absolute, leaf_may_be_missing=False)
    if private and absolute.resolve(strict=True).is_relative_to(ROOT):
        _refuse("private_payload_inside_repository")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(absolute, flags)
    except OSError:
        _refuse("input_open_failed")
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            _refuse("input_not_regular_file")
        if metadata.st_size > MAX_INPUT_BYTES:
            _refuse("input_too_large")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            raw = stream.read(MAX_INPUT_BYTES + 1)
    finally:
        os.close(descriptor)
    if len(raw) > MAX_INPUT_BYTES:
        _refuse("input_too_large")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        _refuse("input_not_utf8")
    try:
        payload = json.loads(
            text,
            object_pairs_hook=_duplicate_rejecting_object,
            parse_constant=_reject_constant,
        )
    except FreezeRefusal:
        raise
    except (TypeError, ValueError, json.JSONDecodeError):
        _refuse("invalid_json")
    if not isinstance(payload, dict):
        _refuse("json_root_not_object")
    _validate_json_value(payload)
    return payload, raw


def _canonical_digest(payload: Any) -> str:
    return sha256_json(payload)


def _render_public_json(payload: dict[str, Any]) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        + "\n"
    ).encode("utf-8")


def _write_new_public_json(path: Path, payload: dict[str, Any]) -> None:
    absolute = _lexical_path(path)
    _assert_no_symlink_components(absolute, leaf_may_be_missing=True)
    if absolute.exists() or absolute.is_symlink():
        _refuse("output_exists")
    parent = absolute.parent
    if not parent.is_dir():
        _refuse("output_parent_not_directory")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(absolute, flags, 0o644)
    except FileExistsError:
        _refuse("output_exists")
    except OSError:
        _refuse("output_open_failed")
    created = True
    try:
        rendered = _render_public_json(payload)
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write(rendered)
            stream.flush()
            os.fsync(stream.fileno())
        created = False
    finally:
        os.close(descriptor)
        if created:
            try:
                absolute.unlink()
            except FileNotFoundError:
                pass


def load_protocol(path: Path = DEFAULT_PROTOCOL) -> dict[str, Any]:
    protocol, _ = _read_json(path)
    _exact_keys(
        protocol,
        {
            "canonical_json",
            "frozen_at",
            "minimums",
            "privacy",
            "protocol_version",
            "status",
            "supported_contracts",
        },
        "protocol_schema_invalid",
    )
    if protocol.get("protocol_version") != "firelens_semantic_holdout_freeze_protocol.v1":
        _refuse("protocol_version_invalid")
    if protocol.get("status") != "frozen":
        _refuse("protocol_not_frozen")
    _timestamp(protocol.get("frozen_at"), "protocol_timestamp_invalid")
    canonical_json = _exact_keys(
        protocol.get("canonical_json"),
        {
            "allow_non_finite_numbers",
            "duplicate_object_keys",
            "hash_encoding",
            "identifier_lists",
            "unicode_normalization",
        },
        "protocol_canonical_json_invalid",
    )
    if canonical_json != {
        "allow_non_finite_numbers": False,
        "duplicate_object_keys": "reject",
        "hash_encoding": "utf8_compact_sorted_keys_no_ascii_escaping",
        "identifier_lists": "sorted_unique",
        "unicode_normalization": "NFC",
    }:
        _refuse("protocol_canonical_json_invalid")
    minimums = _exact_keys(
        protocol.get("minimums"),
        {
            "case_count",
            "question_family_count",
            "risk_labels_per_case",
            "source_commitments_per_case",
        },
        "protocol_minimums_invalid",
    )
    if minimums != {
        "case_count": 25,
        "question_family_count": 5,
        "risk_labels_per_case": 1,
        "source_commitments_per_case": 1,
    }:
        _refuse("protocol_minimums_invalid")
    privacy = _exact_keys(
        protocol.get("privacy"),
        {
            "private_payload_must_be_outside_repository",
            "private_values_in_console_output",
            "write_normalized_private_payload",
        },
        "protocol_privacy_invalid",
    )
    if privacy != {
        "private_payload_must_be_outside_repository": True,
        "private_values_in_console_output": False,
        "write_normalized_private_payload": False,
    }:
        _refuse("protocol_privacy_invalid")
    contracts = _exact_keys(
        protocol.get("supported_contracts"),
        {
            "development_registry",
            "development_review_request",
            "disjointness_audit",
            "private_holdout_payload",
            "private_review_input",
            "public_holdout_manifest",
        },
        "protocol_contracts_invalid",
    )
    if contracts != {
        "development_registry": "firelens_semantic_development_exposure_registry.v1",
        "development_review_request": (
            "firelens_semantic_development_exposure_freeze_request.v1"
        ),
        "disjointness_audit": "firelens_semantic_disjointness_audit.v1",
        "private_holdout_payload": "firelens_semantic_holdout_private_payload.v1",
        "private_review_input": "firelens_semantic_holdout_review_input.v1",
        "public_holdout_manifest": "firelens_semantic_holdout_manifest.v3",
    }:
        _refuse("protocol_contracts_invalid")
    return protocol


def _require_pre_candidate_guard(
    *, attest_no_candidate: bool, candidate_created_at: str | None
) -> None:
    if candidate_created_at is not None:
        _timestamp(candidate_created_at, "candidate_timestamp_invalid")
        _refuse("candidate_already_started")
    if attest_no_candidate is not True:
        _refuse("pre_candidate_attestation_required")
