from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from upgrade_benchmark_support_preview import (
    _preview_report,
    _write_preview_raw_artifact,
)

from firelens.evaluation import preview_raw_evidence
from firelens.evaluation.release_surfaces import _preview


def test_preview_qualification_requires_raw_response_evidence(tmp_path: Path) -> None:
    report = _preview_report()

    with pytest.raises(ValueError, match="raw response artifact is required"):
        _preview(report, raw_response_artifact=tmp_path / "missing.json")


def test_preview_rejects_well_formed_body_digest_substitution(tmp_path: Path) -> None:
    report = _preview_report()
    artifact = _write_preview_raw_artifact(report, tmp_path / "preview-raw.json")
    report["requests"][0]["response_body_sha256"] = "0" * 64

    with pytest.raises(ValueError, match="response-body digest"):
        _preview(report, raw_response_artifact=artifact)


def test_preview_rejects_raw_file_digest_substitution(tmp_path: Path) -> None:
    report = _preview_report()
    artifact = _write_preview_raw_artifact(report, tmp_path / "preview-raw.json")
    report["raw_response_artifact_sha256"] = "0" * 64

    with pytest.raises(ValueError, match="raw response artifact digest"):
        _preview(report, raw_response_artifact=artifact)


def test_preview_rejects_retained_response_digest_substitution(tmp_path: Path) -> None:
    report = _preview_report()
    artifact = _write_preview_raw_artifact(report, tmp_path / "preview-raw.json")
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    payload["requests"][0]["retained_response_sha256"] = "0" * 64
    artifact.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    artifact.chmod(0o600)
    report["raw_response_artifact_sha256"] = hashlib.sha256(artifact.read_bytes()).hexdigest()

    with pytest.raises(ValueError, match="retained response differs from the report"):
        _preview(report, raw_response_artifact=artifact)


def test_preview_recomputes_retained_response_from_raw_body(tmp_path: Path) -> None:
    report = _preview_report()
    artifact = _write_preview_raw_artifact(report, tmp_path / "preview-raw.json")
    static = next(row for row in report["requests"] if row["case_id"] == "static")
    static["response"]["exact_support"]["evidence"][0]["primary_text_sha256"] = "f" * 64

    with pytest.raises(ValueError, match="retained response differs from raw evidence"):
        _preview(report, raw_response_artifact=artifact)


def test_preview_rejects_path_swap_during_bound_file_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = _preview_report()
    artifact = _write_preview_raw_artifact(report, tmp_path / "preview-raw.json")
    replacement = tmp_path / "replacement.json"
    replacement.write_text("{}\n", encoding="utf-8")
    replacement.chmod(0o600)
    read_bound_file = preview_raw_evidence._read_bounded_fd

    def read_then_swap(descriptor: int, *, maximum_bytes: int) -> bytes:
        raw_bytes = read_bound_file(descriptor, maximum_bytes=maximum_bytes)
        replacement.replace(artifact)
        return raw_bytes

    monkeypatch.setattr(preview_raw_evidence, "_read_bounded_fd", read_then_swap)

    with pytest.raises(ValueError, match="changed while being read"):
        _preview(report, raw_response_artifact=artifact)


def test_preview_requires_private_single_link_raw_artifact(tmp_path: Path) -> None:
    report = _preview_report()
    artifact = _write_preview_raw_artifact(report, tmp_path / "preview-raw.json")
    artifact.chmod(0o640)

    with pytest.raises(ValueError, match="private 0600 regular file"):
        _preview(report, raw_response_artifact=artifact)

    artifact.chmod(0o600)
    (tmp_path / "second-link.json").hardlink_to(artifact)
    with pytest.raises(ValueError, match="private 0600 regular file"):
        _preview(report, raw_response_artifact=artifact)


def test_private_raw_writer_never_overwrites_existing_artifact(tmp_path: Path) -> None:
    artifact = tmp_path / "preview-raw.json"
    artifact.write_text("original\n", encoding="utf-8")
    artifact.chmod(0o600)

    with pytest.raises(FileExistsError):
        preview_raw_evidence._write_raw_response_artifact(artifact, "replacement\n")

    assert artifact.read_text(encoding="utf-8") == "original\n"


def test_raw_artifact_generator_enforces_validator_size_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(preview_raw_evidence, "MAX_RAW_ARTIFACT_BYTES", 1)
    requests = [{"response": {}}]
    raw_requests = [preview_raw_evidence._raw_response_row("homepage", b"body")]

    with pytest.raises(ValueError, match="private evidence limit"):
        preview_raw_evidence._serialize_raw_response_artifact(requests, raw_requests)
