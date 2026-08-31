"""Capture, sanitize, persist, and validate private preview response evidence."""

from __future__ import annotations

import base64
import binascii
import errno
import hashlib
import json
import os
import stat
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from firelens.evaluation.common import require_digest as _require_digest
from firelens.evaluation.common import require_exact_keys as _require_exact_keys
from firelens.evaluation.common import sha256_json as _sha256_json

LIVE_METADATA_FIELDS = (
    "result_id",
    "kind",
    "authority",
    "source_url",
    "source_updated_at",
    "retrieved_at",
    "status",
)
RETAINED_MEDIA_TYPES = frozenset({"application/json", "text/html"})
FORBIDDEN_RETAINED_FIELDS = frozenset(
    {
        "answer",
        "authorization",
        "bbox",
        "body",
        "content",
        "context_text",
        "coordinates",
        "cookie",
        "geometry",
        "headers",
        "history_text",
        "latitude",
        "location",
        "longitude",
        "primary_text",
        "private_headers",
        "quote",
        "raw_response",
        "response_body",
        "response_content",
        "set-cookie",
        "source_passage",
    }
)
RAW_ARTIFACT_VERSION = "firelens.preview_raw_response_artifact.v1"
MAX_RAW_ARTIFACT_BYTES = 64 * 1024 * 1024


def _json_sha256(value: Any) -> str:
    canonical = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _retained_media_type(value: str | None) -> str:
    """Retain only the protocol media type, never arbitrary header parameters."""

    media_type = str(value or "").split(";", 1)[0].strip().casefold()
    return media_type if media_type in RETAINED_MEDIA_TYPES else "other"


def _public_live_metadata(row: Any) -> dict[str, Any]:
    """Retain only public record provenance, while preserving malformed rows."""

    if not isinstance(row, dict):
        return {"invalid_record": True, "value_type": type(row).__name__}
    retained = {field: row.get(field) for field in LIVE_METADATA_FIELDS}
    source_url = retained.get("source_url")
    if isinstance(source_url, str):
        retained["source_url"] = (
            urlparse(source_url)._replace(params="", query="", fragment="").geturl()
        )
    return retained


def _assert_exact_retained_keys(
    payload: Any, expected: set[str], *, context: str
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError(f"{context} must be an object")
    actual = set(payload)
    if actual != expected:
        raise ValueError(
            f"{context} violates the retained-evidence schema; "
            f"missing={sorted(expected - actual)}, unexpected={sorted(actual - expected)}"
        )
    return payload


def _assert_no_sensitive_retained_fields(
    value: Any, *, context: str = "preview report"
) -> None:
    """Reject plaintext/body/location channels from any retained structure."""

    if isinstance(value, dict):
        normalized_forbidden = {field.replace("-", "_") for field in FORBIDDEN_RETAINED_FIELDS}
        for key, nested in value.items():
            normalized = str(key).strip().casefold().replace("-", "_")
            if normalized in normalized_forbidden:
                raise ValueError(f"{context} contains forbidden retained field {key!r}")
            _assert_no_sensitive_retained_fields(nested, context=f"{context}.{key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _assert_no_sensitive_retained_fields(nested, context=f"{context}[{index}]")


def _assert_safe_retained_preview_report(report: dict[str, Any]) -> None:
    """Enforce the content-free preview artifact boundary before serialization."""

    _assert_exact_retained_keys(
        report,
        {
            "report_version",
            "evidence_schema_version",
            "generated_at",
            "base_url",
            "expected",
            "observed",
            "requests",
            "ask_p95_ms",
            "p95_target_ms",
            "checks",
            "qualified",
            "elapsed_seconds",
            "not_executed",
            "raw_response_artifact_sha256",
        },
        context="preview report",
    )
    requests = report.get("requests")
    if not isinstance(requests, list) or len(requests) != 8:
        raise ValueError("preview report must retain exactly eight request rows")
    expected_cases = [
        "homepage",
        "liveness",
        "readiness",
        "static",
        "unsupported",
        "live",
        "mixed",
        "map",
    ]
    request_keys = {
        "case_id",
        "method",
        "path",
        "request",
        "request_body_sha256",
        "status_code",
        "latency_ms",
        "response_content_type",
        "response_content_length_bytes",
        "response_body_sha256",
        "response",
    }
    for index, row in enumerate(requests):
        _validate_retained_preview_request(row, index, expected_cases[index], request_keys)
    _assert_no_sensitive_retained_fields(report)


def _validate_retained_preview_request(
    row: Any, index: int, case_id: str, request_keys: set[str]
) -> None:
    retained = _assert_exact_retained_keys(
        row, request_keys, context=f"preview request {index}"
    )
    if retained.get("case_id") != case_id:
        raise ValueError("preview retained case order differs from the canonical protocol")
    request = retained.get("request")
    if not isinstance(request, dict) or not set(request).issubset({"question", "layers"}):
        raise ValueError(f"preview {case_id} request retains unsupported input fields")
    response = retained.get("response")
    simple_keys = {
        "homepage": set(),
        "liveness": {"status"},
        "readiness": {
            "status",
            "release_version",
            "build_commit",
            "deployment_id",
            "rate_limit_scope",
        },
    }
    if case_id in simple_keys:
        _assert_exact_retained_keys(
            response, simple_keys[case_id], context=f"preview {case_id} response"
        )
    elif case_id == "map":
        _validate_retained_live_records(response, context="preview map", map_response=True)
    else:
        _validate_retained_ask_response(response, case_id)


def _validate_retained_live_records(
    value: Any, *, context: str, map_response: bool = False
) -> None:
    payload = (
        _assert_exact_retained_keys(
            value, {"record_count", "records"}, context=f"{context} response"
        )
        if map_response
        else value
    )
    records = payload["records"] if map_response else payload
    for index, record in enumerate(records):
        _assert_exact_retained_keys(
            record, set(LIVE_METADATA_FIELDS), context=f"{context} record {index}"
        )


def _validate_retained_ask_response(response: Any, case_id: str) -> None:
    keys = {"status", "response_mode", "claim_count", "evidence_count", "live_result_count"}
    if case_id in {"static", "mixed"}:
        keys.add("exact_support")
    if case_id in {"live", "mixed"}:
        keys.add("live_records")
    payload = _assert_exact_retained_keys(response, keys, context=f"preview {case_id} response")
    _validate_retained_live_records(
        payload.get("live_records", []), context=f"preview {case_id} live"
    )
    if payload.get("exact_support") is not None:
        _validate_retained_exact_support(payload["exact_support"], case_id)


def _validate_retained_exact_support(support: Any, case_id: str) -> None:
    proof = _assert_exact_retained_keys(
        support, {"claims", "evidence"}, context=f"preview {case_id} exact-support proof"
    )
    for claim_index, claim in enumerate(proof["claims"]):
        retained = _assert_exact_retained_keys(
            claim, {"claim_id", "supports"}, context=f"preview {case_id} claim {claim_index}"
        )
        for support_index, row in enumerate(retained["supports"]):
            keys = {
                "evidence_id",
                "quote_sha256",
                "quote_length",
                "match_start",
                "match_end",
                "matched_slice_sha256",
            }
            _assert_exact_retained_keys(
                row,
                keys,
                context=f"preview {case_id} claim {claim_index} support {support_index}",
            )
    for index, row in enumerate(proof["evidence"]):
        _assert_exact_retained_keys(
            row,
            {"evidence_id", "primary_text_sha256", "primary_text_length"},
            context=f"preview {case_id} evidence {index}",
        )


def _exact_support_evidence(payload: dict[str, Any]) -> dict[str, Any]:
    """Create a content-free proof roster for exact-quote support checks."""

    evidence_rows: list[dict[str, Any]] = []
    primary_by_id: dict[str, str] = {}
    for row in payload.get("evidence", []):
        if not isinstance(row, dict) or not row.get("evidence_id"):
            evidence_rows.append({"invalid_evidence": True, "value_type": type(row).__name__})
            continue
        evidence_id = str(row["evidence_id"])
        primary_text = row.get("primary_text")
        if not isinstance(primary_text, str):
            evidence_rows.append(
                {
                    "evidence_id": evidence_id,
                    "primary_text_sha256": None,
                    "primary_text_length": None,
                }
            )
            continue
        primary_by_id[evidence_id] = primary_text
        evidence_rows.append(
            {
                "evidence_id": evidence_id,
                "primary_text_sha256": hashlib.sha256(primary_text.encode("utf-8")).hexdigest(),
                "primary_text_length": len(primary_text),
            }
        )

    claim_rows: list[dict[str, Any]] = []
    for claim in payload.get("claims", []):
        if not isinstance(claim, dict):
            claim_rows.append({"invalid_claim": True, "value_type": type(claim).__name__})
            continue
        support_rows: list[dict[str, Any]] = []
        supports = claim.get("supports", [])
        if not isinstance(supports, list):
            supports = []
        for support in supports:
            if not isinstance(support, dict):
                support_rows.append(
                    {"invalid_support": True, "value_type": type(support).__name__}
                )
                continue
            evidence_id = str(support.get("evidence_id") or "")
            quote = support.get("quote")
            primary_text = primary_by_id.get(evidence_id)
            match_start = (
                primary_text.find(quote)
                if isinstance(primary_text, str) and isinstance(quote, str) and quote
                else -1
            )
            matched_slice = (
                primary_text[match_start : match_start + len(quote)]
                if match_start >= 0 and isinstance(primary_text, str) and isinstance(quote, str)
                else None
            )
            support_rows.append(
                {
                    "evidence_id": evidence_id,
                    "quote_sha256": (
                        hashlib.sha256(quote.encode("utf-8")).hexdigest()
                        if isinstance(quote, str)
                        else None
                    ),
                    "quote_length": len(quote) if isinstance(quote, str) else None,
                    "match_start": match_start,
                    "match_end": (
                        match_start + len(quote)
                        if match_start >= 0 and isinstance(quote, str)
                        else -1
                    ),
                    "matched_slice_sha256": (
                        hashlib.sha256(matched_slice.encode("utf-8")).hexdigest()
                        if matched_slice is not None
                        else None
                    ),
                }
            )
        claim_rows.append(
            {
                "claim_id": str(claim.get("claim_id") or ""),
                "supports": support_rows,
            }
        )
    return {"claims": claim_rows, "evidence": evidence_rows}


def _response_evidence(case_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Select the minimum response fields needed to recompute canonical checks."""

    if case_id == "homepage":
        return {}
    if case_id in {"liveness", "readiness"}:
        fields = (
            ("status",)
            if case_id == "liveness"
            else (
                "status",
                "release_version",
                "build_commit",
                "deployment_id",
                "rate_limit_scope",
            )
        )
        return {field: payload.get(field) for field in fields}

    evidence: dict[str, Any] = {
        "status": payload.get("status"),
        "response_mode": payload.get("response_mode"),
        "claim_count": len(payload.get("claims", []))
        if isinstance(payload.get("claims", []), list)
        else None,
        "evidence_count": len(payload.get("evidence", []))
        if isinstance(payload.get("evidence", []), list)
        else None,
        "live_result_count": len(payload.get("live_results", []))
        if isinstance(payload.get("live_results", []), list)
        else None,
    }
    if case_id in {"static", "mixed"}:
        evidence["exact_support"] = _exact_support_evidence(payload)
    if case_id in {"live", "mixed"}:
        evidence["live_records"] = [
            _public_live_metadata(row) for row in payload.get("live_results", [])
        ]
    if case_id == "map":
        evidence = {
            "record_count": len(payload.get("results", []))
            if isinstance(payload.get("results", []), list)
            else None,
            "records": [_public_live_metadata(row) for row in payload.get("results", [])],
        }
    return evidence


def _raw_response_row(case_id: str, body: bytes) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "response_body_base64": base64.b64encode(body).decode("ascii"),
        "retained_response_sha256": None,
    }


def _serialize_raw_response_artifact(
    requests: list[dict[str, Any]], raw_requests: list[dict[str, Any]]
) -> str:
    for request, raw_request in zip(requests, raw_requests, strict=True):
        raw_request["retained_response_sha256"] = _json_sha256(request["response"])
    raw_text = (
        json.dumps(
            {"artifact_version": RAW_ARTIFACT_VERSION, "requests": raw_requests},
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    if len(raw_text.encode("utf-8")) > MAX_RAW_ARTIFACT_BYTES:
        raise ValueError("preview raw response artifact exceeds the private evidence limit")
    return raw_text


def _assert_raw_response_artifact_available(path: Path) -> None:
    if path.exists() or path.is_symlink():
        raise FileExistsError(f"refusing to overwrite preview raw response artifact: {path}")


def _write_raw_response_artifact(path: Path, raw_text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            descriptor = -1
            stream.write(raw_text)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        if descriptor >= 0:
            os.close(descriptor)
        path.unlink(missing_ok=True)
        raise


def _read_bounded_fd(descriptor: int, *, maximum_bytes: int) -> bytes:
    chunks: list[bytes] = []
    remaining = maximum_bytes + 1
    while remaining > 0:
        chunk = os.read(descriptor, min(1024 * 1024, remaining))
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    payload = b"".join(chunks)
    if len(payload) > maximum_bytes:
        raise ValueError("preview raw response artifact exceeds the private evidence limit")
    return payload


def _strict_json_object(raw_bytes: bytes) -> dict[str, Any]:
    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON constant {value}")

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        for key, value in pairs:
            if key in payload:
                raise ValueError(f"duplicate JSON key {key!r}")
            payload[key] = value
        return payload

    try:
        decoded = raw_bytes.decode("utf-8")
        payload = json.loads(
            decoded,
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError("preview raw response artifact must contain strict JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("preview raw response artifact must be an object")
    return payload


def _read_private_raw_artifact(path: Path) -> tuple[bytes, dict[str, Any]]:
    try:
        path_before = os.lstat(path)
    except FileNotFoundError as exc:
        raise ValueError("preview raw response artifact is required") from exc
    if stat.S_ISLNK(path_before.st_mode):
        raise ValueError("preview raw response artifact must not be a symbolic link")
    if not stat.S_ISREG(path_before.st_mode):
        raise ValueError("preview raw response artifact must be one private 0600 regular file")

    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError as exc:
        raise ValueError(
            "preview raw response artifact changed before it could be read"
        ) from exc
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise ValueError(
                "preview raw response artifact must not be a symbolic link"
            ) from exc
        raise ValueError("preview raw response artifact could not be opened safely") from exc

    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or stat.S_IMODE(opened.st_mode) != 0o600
            or opened.st_nlink != 1
        ):
            raise ValueError(
                "preview raw response artifact must be one private 0600 regular file"
            )
        if (path_before.st_dev, path_before.st_ino) != (opened.st_dev, opened.st_ino):
            raise ValueError("preview raw response artifact changed before it could be read")
        if opened.st_size < 0 or opened.st_size > MAX_RAW_ARTIFACT_BYTES:
            raise ValueError("preview raw response artifact exceeds the private evidence limit")

        raw_bytes = _read_bounded_fd(descriptor, maximum_bytes=MAX_RAW_ARTIFACT_BYTES)
        opened_after = os.fstat(descriptor)
        try:
            path_after = os.lstat(path)
        except FileNotFoundError as exc:
            raise ValueError("preview raw response artifact changed while being read") from exc
        stable_file_fields = (
            "st_dev",
            "st_ino",
            "st_mode",
            "st_nlink",
            "st_size",
            "st_mtime_ns",
            "st_ctime_ns",
        )
        if any(
            getattr(opened, field) != getattr(opened_after, field)
            for field in stable_file_fields
        ) or (path_after.st_dev, path_after.st_ino) != (opened.st_dev, opened.st_ino):
            raise ValueError("preview raw response artifact changed while being read")
        if len(raw_bytes) != opened.st_size:
            raise ValueError("preview raw response artifact changed while being read")
    finally:
        os.close(descriptor)
    return raw_bytes, _strict_json_object(raw_bytes)


def _validate_preview_raw_response_artifact(
    report: dict[str, Any],
    requests: list[dict[str, Any]],
    raw_response_artifact: Path | None,
) -> None:
    if raw_response_artifact is None:
        raise ValueError("preview raw response artifact is required")
    raw_bytes, payload = _read_private_raw_artifact(raw_response_artifact)
    declared_digest = _require_digest(
        report.get("raw_response_artifact_sha256"),
        context="preview raw response artifact digest",
    )
    if hashlib.sha256(raw_bytes).hexdigest() != declared_digest:
        raise ValueError("preview raw response artifact digest does not match the report")
    _require_exact_keys(
        payload,
        {"artifact_version", "requests"},
        context="preview raw response artifact",
    )
    if payload.get("artifact_version") != RAW_ARTIFACT_VERSION:
        raise ValueError("preview raw response artifact uses an unsupported version")
    raw_requests = payload.get("requests")
    if not isinstance(raw_requests, list) or len(raw_requests) != len(requests):
        raise ValueError("preview raw response artifact must contain the canonical roster")
    for index, (request, raw_request) in enumerate(zip(requests, raw_requests, strict=True)):
        _validate_raw_response_row(request, raw_request, index=index)


def _validate_raw_response_row(
    request: dict[str, Any], raw_request: Any, *, index: int
) -> None:
    context = f"preview raw response {index}"
    if not isinstance(raw_request, dict):
        raise ValueError(f"{context} must be an object")
    _require_exact_keys(
        raw_request,
        {"case_id", "response_body_base64", "retained_response_sha256"},
        context=context,
    )
    if raw_request.get("case_id") != request.get("case_id"):
        raise ValueError("preview raw response artifact differs from the canonical roster")
    encoded = raw_request.get("response_body_base64")
    if not isinstance(encoded, str):
        raise ValueError(f"{context} body must be base64 text")
    try:
        raw_body = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError(f"{context} body is not strict base64") from exc
    if len(raw_body) != request["response_content_length_bytes"]:
        raise ValueError(f"{context} length differs from the retained request evidence")
    if hashlib.sha256(raw_body).hexdigest() != request["response_body_sha256"]:
        raise ValueError(f"{context} response-body digest differs from raw evidence")
    case_id = str(request["case_id"])
    if case_id == "homepage":
        recomputed_response: dict[str, Any] = {}
    else:
        try:
            decoded_response = json.loads(raw_body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"{context} is not a valid JSON response") from exc
        if not isinstance(decoded_response, dict):
            raise ValueError(f"{context} JSON response must be an object")
        recomputed_response = _response_evidence(case_id, decoded_response)
    if recomputed_response != request["response"]:
        raise ValueError(f"{context} retained response differs from raw evidence")
    retained_digest = _require_digest(
        raw_request.get("retained_response_sha256"),
        context=f"{context} retained-response digest",
    )
    if retained_digest != _sha256_json(recomputed_response):
        raise ValueError(f"{context} retained response differs from the report")
