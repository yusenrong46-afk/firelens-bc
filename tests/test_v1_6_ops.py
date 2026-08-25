from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from rag_helpers import make_chunk

from firelens.agent.failures import classify_failure, record_expected_failure
from firelens.agent.packet import AgentPacket
from firelens.errors import (
    OfficialSourceUnavailable,
    ToolInputError,
    UnexpectedProgrammingError,
)
from firelens.live import LiveDataUnavailable
from firelens.live_support import LiveDataErrorKind
from firelens.runtime_artifact_common import RuntimeArtifactError
from firelens.runtime_packaging import verify_packaging_parity
from firelens.source_radar import inspect_source_changes

ROOT = Path(__file__).resolve().parents[1]


def test_live_outage_is_not_an_unexpected_programming_error() -> None:
    classified = classify_failure(
        LiveDataUnavailable("layer down", kind=LiveDataErrorKind.UNREACHABLE)
    )
    assert isinstance(classified, OfficialSourceUnavailable)
    assert classified.public_kind == "official_source_unavailable"


def test_unexpected_failure_is_never_reported_as_source_outage() -> None:
    packet = AgentPacket()
    try:
        record_expected_failure(packet, RuntimeError("boom"))
    except UnexpectedProgrammingError as exc:
        assert exc.public_kind == "unexpected_programming_error"
        assert exc.public_kind != "official_source_unavailable"
    else:
        raise AssertionError("unexpected errors must not be swallowed")
    assert packet.policy.fallback_reason is None


def test_value_error_is_typed_tool_input() -> None:
    packet = AgentPacket()
    payload = record_expected_failure(packet, ValueError("tool is not allowlisted: x"))
    assert payload == {"error": "tool_input_error"}
    assert packet.policy.fallback_reason == ToolInputError.public_kind


def test_source_change_radar_quarantines_without_publishing(tmp_path: Path) -> None:
    chunk = make_chunk("chunk-a", "Keep an emergency kit with water.")
    chunks_path = tmp_path / "chunks.jsonl"
    chunks_path.write_text(json.dumps(asdict(chunk), sort_keys=True) + "\n", encoding="utf-8")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "source_id": "source-a",
                        "corpus_action": "include",
                        "document_sha256": "a" * 64,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    acquired = tmp_path / "acquired.bin"
    acquired.write_bytes(b"changed-bytes")
    report = inspect_source_changes(
        tmp_path,
        {"source-a": acquired},
        manifest_path=manifest_path,
        chunks_path=chunks_path,
    )
    assert report["auto_publish"] is False
    assert report["quarantine_recommended"] is True
    assert report["changes"][0]["publication"] == "blocked"
    assert report["changes"][0]["affected_chunk_ids"] == ["chunk-a"]


def test_source_change_radar_marks_missing_included_acquisitions_incomplete(
    tmp_path: Path,
) -> None:
    chunk = make_chunk("chunk-a", "Reviewed source text.")
    chunks_path = tmp_path / "chunks.jsonl"
    chunks_path.write_text(json.dumps(asdict(chunk), sort_keys=True) + "\n", encoding="utf-8")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "source_id": "source-a",
                        "corpus_action": "include",
                        "document_sha256": "a" * 64,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    report = inspect_source_changes(
        tmp_path,
        {},
        manifest_path=manifest_path,
        chunks_path=chunks_path,
    )

    assert report["scan_complete"] is False
    assert report["missing_source_ids"] == ["source-a"]
    assert report["quarantine_recommended"] is True


def test_source_change_radar_rejects_duplicate_manifest_keys(tmp_path: Path) -> None:
    chunks_path = tmp_path / "chunks.jsonl"
    chunks_path.write_text("", encoding="utf-8")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        '{"sources":[{"source_id":"source-a","corpus_action":"include",'
        '"document_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}],'
        '"sources":[]}',
        encoding="utf-8",
    )

    try:
        inspect_source_changes(
            tmp_path,
            {},
            manifest_path=manifest_path,
            chunks_path=chunks_path,
        )
    except RuntimeArtifactError as exc:
        assert "duplicate JSON key: sources" in str(exc)
    else:
        raise AssertionError("duplicate manifest keys must fail closed")


def test_vercel_and_docker_share_one_logical_allowlist() -> None:
    report = verify_packaging_parity(ROOT)
    assert report["missing_from_dockerfile"] == []
    assert report["missing_from_vercel"] == []
    assert report["document_context_in_docker"] is True
    assert report["document_context_in_vercel"] is True
    assert report["status"] == "passed"
