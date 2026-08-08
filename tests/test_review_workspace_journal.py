from __future__ import annotations

import json
import os
import stat
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier

import pytest
from pydantic import ValidationError

from firelens.review_workspace import (
    GENESIS_EVENT_HASH,
    AppendOnlyReviewJournal,
    JournalLimits,
    ReviewActor,
    ReviewEventDraft,
    ReviewSession,
    create_immutable_json,
)

SESSION_ID = "semantic-session-001"
START = datetime(2026, 8, 6, 18, 0, tzinfo=UTC)


def _draft(
    sequence: int = 1,
    *,
    idempotency_key: str | None = None,
    payload: dict[str, object] | None = None,
    timestamp: datetime | None = None,
) -> ReviewEventDraft:
    return ReviewEventDraft(
        event_type="case.decision.recorded",
        session_id=SESSION_ID,
        actor_id="reviewer-01",
        case_id=f"case-{sequence:03d}",
        idempotency_key=idempotency_key or f"request-{sequence:03d}",
        presentation_id=f"presentation-{sequence:03d}",
        payload=payload or {"decision": "supported", "notes": "evidence agrees"},
        timestamp=timestamp or START + timedelta(seconds=sequence),
    )


def _journal(tmp_path: Path, **kwargs: object) -> AppendOnlyReviewJournal:
    return AppendOnlyReviewJournal(
        tmp_path / "review-workspace",
        session_id=SESSION_ID,
        **kwargs,
    )


def test_append_replay_is_canonical_hash_chained_and_private(tmp_path: Path) -> None:
    journal = _journal(tmp_path)

    first = journal.append(_draft(1, payload={"z": "wildfire", "a": "évidence"}))
    second = journal.append(_draft(2))

    assert first.sequence == 1
    assert first.previous_event_hash == GENESIS_EVENT_HASH
    assert second.sequence == 2
    assert second.previous_event_hash == first.event_hash
    assert journal.replay() == (first, second)

    workspace = tmp_path / "review-workspace"
    journal_path = workspace / "events.jsonl"
    assert stat.S_IMODE(workspace.stat().st_mode) == 0o700
    assert stat.S_IMODE(journal_path.stat().st_mode) == 0o600
    raw_lines = journal_path.read_bytes().splitlines()
    assert len(raw_lines) == 2
    for raw_line in raw_lines:
        document = json.loads(raw_line)
        assert raw_line == json.dumps(
            document,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")


def test_replay_of_missing_journal_is_read_only(tmp_path: Path) -> None:
    journal = _journal(tmp_path)

    assert journal.replay() == ()
    assert not (tmp_path / "review-workspace").exists()


def test_idempotent_retry_returns_existing_event_without_appending(tmp_path: Path) -> None:
    journal = _journal(tmp_path)
    original = journal.append(_draft(1))
    retry = _draft(1, timestamp=START + timedelta(hours=1))

    returned = AppendOnlyReviewJournal(
        tmp_path / "review-workspace", session_id=SESSION_ID
    ).append(retry)

    assert returned == original
    assert journal.replay() == (original,)


def test_same_idempotency_key_with_different_payload_fails(tmp_path: Path) -> None:
    journal = _journal(tmp_path)
    journal.append(_draft(1))

    with pytest.raises(ValueError, match="idempotency key"):
        journal.append(
            _draft(
                2,
                idempotency_key="request-001",
                payload={"decision": "unsupported"},
            )
        )

    assert len(journal.replay()) == 1


def test_concurrent_retries_serialize_to_one_event(tmp_path: Path) -> None:
    journal = _journal(tmp_path)
    barrier = Barrier(12)

    def append_after_barrier(_: int) -> str:
        barrier.wait(timeout=5)
        return journal.append(_draft(1)).event_hash

    with ThreadPoolExecutor(max_workers=12) as executor:
        hashes = list(executor.map(append_after_barrier, range(12)))

    assert len(set(hashes)) == 1
    assert len(journal.replay()) == 1


def test_retry_after_lost_post_fsync_ack_finds_durable_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    journal = _journal(tmp_path)
    journal.replay()
    real_fsync = os.fsync

    def fail_after_fsync(descriptor: int) -> None:
        real_fsync(descriptor)
        raise OSError("simulated lost acknowledgement after durable file sync")

    monkeypatch.setattr("firelens.review_workspace.journal.os.fsync", fail_after_fsync)
    with pytest.raises(OSError, match="lost acknowledgement"):
        journal.append(_draft(1))
    monkeypatch.setattr("firelens.review_workspace.journal.os.fsync", real_fsync)

    recovered = journal.append(_draft(1, timestamp=START + timedelta(hours=1)))
    assert recovered.sequence == 1
    assert journal.replay() == (recovered,)


def test_replay_rejects_truncated_partial_line_before_next_append(tmp_path: Path) -> None:
    journal = _journal(tmp_path)
    journal.append(_draft(1))
    path = tmp_path / "review-workspace" / "events.jsonl"
    with path.open("ab") as stream:
        stream.write(b'{"partial":')

    with pytest.raises(ValueError, match="truncated partial record"):
        journal.append(_draft(2))


def test_replay_rejects_payload_tampering_before_next_append(tmp_path: Path) -> None:
    journal = _journal(tmp_path)
    journal.append(_draft(1))
    path = tmp_path / "review-workspace" / "events.jsonl"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["payload"]["decision"] = "unsupported"
    path.write_text(
        json.dumps(document, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="event hash mismatch"):
        journal.append(_draft(2))


def test_replay_rejects_tampered_chain_link(tmp_path: Path) -> None:
    journal = _journal(tmp_path)
    journal.append(_draft(1))
    journal.append(_draft(2))
    path = tmp_path / "review-workspace" / "events.jsonl"
    documents = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    documents[1]["previous_event_hash"] = GENESIS_EVENT_HASH
    path.write_text(
        "\n".join(
            json.dumps(row, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
            for row in documents
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="chain mismatch"):
        journal.replay()


def test_replay_rejects_noncanonical_existing_json(tmp_path: Path) -> None:
    journal = _journal(tmp_path)
    event = journal.append(_draft(1))
    path = tmp_path / "review-workspace" / "events.jsonl"
    path.write_text(
        json.dumps(event.model_dump(mode="json"), ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="non-canonical"):
        journal.replay()


def test_replay_rejects_non_monotonic_timestamp(tmp_path: Path) -> None:
    journal = _journal(tmp_path)
    journal.append(_draft(1))

    with pytest.raises(ValueError, match="strictly increasing"):
        journal.append(_draft(2, timestamp=START + timedelta(milliseconds=1)))


@pytest.mark.parametrize(
    "relative_path", [".", "../outside.jsonl", "nested/../../outside", "/tmp/x"]
)
def test_paths_must_remain_within_workspace(tmp_path: Path, relative_path: str) -> None:
    journal = _journal(tmp_path, relative_path=relative_path)

    with pytest.raises(ValueError, match="contained relative path"):
        journal.replay()


def test_journal_rejects_final_symlink(tmp_path: Path) -> None:
    workspace = tmp_path / "review-workspace"
    workspace.mkdir(mode=0o700)
    outside = tmp_path / "outside.jsonl"
    outside.write_text("do not touch", encoding="utf-8")
    (workspace / "events.jsonl").symlink_to(outside)

    with pytest.raises((ValueError, OSError)):
        _journal(tmp_path).replay()
    assert outside.read_text(encoding="utf-8") == "do not touch"


def test_journal_rejects_symlinked_subdirectory(tmp_path: Path) -> None:
    workspace = tmp_path / "review-workspace"
    workspace.mkdir(mode=0o700)
    outside = tmp_path / "outside"
    outside.mkdir()
    (workspace / "nested").symlink_to(outside, target_is_directory=True)

    with pytest.raises((ValueError, OSError)):
        _journal(tmp_path, relative_path="nested/events.jsonl").replay()
    assert not (outside / "events.jsonl").exists()


def test_journal_rejects_nonregular_target_without_blocking(tmp_path: Path) -> None:
    workspace = tmp_path / "review-workspace"
    workspace.mkdir(mode=0o700)
    os.mkfifo(workspace / "events.jsonl", mode=0o600)

    with pytest.raises(ValueError, match="not a regular file"):
        _journal(tmp_path).replay()


def test_journal_rejects_unexpected_hard_link(tmp_path: Path) -> None:
    journal = _journal(tmp_path)
    journal.append(_draft(1))
    path = tmp_path / "review-workspace" / "events.jsonl"
    os.link(path, tmp_path / "unexpected-link.jsonl")

    with pytest.raises(ValueError, match="hard-link count"):
        journal.replay()


def test_append_rejects_path_replacement_before_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    journal = _journal(tmp_path)
    journal.append(_draft(1))
    path = tmp_path / "review-workspace" / "events.jsonl"
    displaced = path.with_name("displaced.jsonl")
    real_write = os.write
    replaced = False

    def replace_after_write(descriptor: int, payload: bytes) -> int:
        nonlocal replaced
        written = real_write(descriptor, payload)
        if not replaced and b'"sequence":2' in payload:
            replaced = True
            path.rename(displaced)
            path.write_bytes(b"")
            path.chmod(0o600)
        return written

    monkeypatch.setattr("firelens.review_workspace.journal.os.write", replace_after_write)

    with pytest.raises(ValueError, match="path changed"):
        journal.append(_draft(2))

    assert replaced
    assert displaced.read_bytes().endswith(b"\n")


def test_journal_rejects_broad_file_permissions(tmp_path: Path) -> None:
    journal = _journal(tmp_path)
    journal.append(_draft(1))
    path = tmp_path / "review-workspace" / "events.jsonl"
    path.chmod(0o640)

    with pytest.raises(PermissionError, match="0600"):
        journal.replay()
    assert stat.S_IMODE(path.stat().st_mode) == 0o640


def test_journal_rejects_broad_directory_permissions(tmp_path: Path) -> None:
    journal = _journal(tmp_path)
    journal.append(_draft(1))
    workspace = tmp_path / "review-workspace"
    workspace.chmod(0o750)

    with pytest.raises(PermissionError, match="0700"):
        journal.replay()


def test_limits_reject_large_records_and_excess_records(tmp_path: Path) -> None:
    record_limited = _journal(
        tmp_path / "record",
        limits=JournalLimits(max_record_bytes=1024),
    )
    with pytest.raises(ValueError, match="record limit"):
        record_limited.append(_draft(1, payload={"notes": "x" * 2_000}))

    count_limited = _journal(
        tmp_path / "count",
        limits=JournalLimits(max_records=1),
    )
    count_limited.append(_draft(1))
    with pytest.raises(ValueError, match="record limit"):
        count_limited.append(_draft(2))

    file_limited = _journal(
        tmp_path / "file",
        limits=JournalLimits(max_file_bytes=1024),
    )
    file_limited.append(_draft(1, payload={"notes": "x" * 400}))
    with pytest.raises(ValueError, match="file limit"):
        file_limited.append(_draft(2))


def test_immutable_json_uses_exclusive_private_canonical_creation(tmp_path: Path) -> None:
    workspace = tmp_path / "review-workspace"
    session = ReviewSession(
        session_version="firelens_review_session.v1",
        session_id=SESSION_ID,
        review_kind="semantic",
        artifact_sha256="a" * 64,
        protocol_sha256="b" * 64,
        created_at=START,
        case_ids=("case-001",),
        actors=(
            ReviewActor(
                actor_id="reviewer-01",
                display_name="Human Reviewer",
                role="reviewer",
            ),
        ),
    )

    path = create_immutable_json(workspace, "session/session.json", session)

    assert stat.S_IMODE(workspace.stat().st_mode) == 0o700
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    raw = path.read_bytes()
    assert raw.endswith(b"\n")
    assert raw[:-1] == json.dumps(
        json.loads(raw),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        create_immutable_json(workspace, "session/session.json", session)


def test_immutable_creation_rejects_symlink_and_traversal(tmp_path: Path) -> None:
    workspace = tmp_path / "review-workspace"
    workspace.mkdir(mode=0o700)
    outside = tmp_path / "outside.json"
    outside.write_text("original", encoding="utf-8")
    (workspace / "receipt.json").symlink_to(outside)

    with pytest.raises(FileExistsError):
        create_immutable_json(workspace, "receipt.json", {"qualified": True})
    with pytest.raises(ValueError, match="contained relative path"):
        create_immutable_json(workspace, "../escape.json", {"qualified": True})
    assert outside.read_text(encoding="utf-8") == "original"


def test_strict_models_reject_unknown_fields_naive_time_and_duplicate_ids() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ReviewEventDraft.model_validate(
            {
                **_draft(1).model_dump(),
                "unexpected": True,
            }
        )
    with pytest.raises(ValidationError, match="UTC offset"):
        ReviewEventDraft(
            **{
                **_draft(1).model_dump(exclude={"timestamp"}),
                "timestamp": datetime(2026, 8, 6, 18, 0),
            }
        )
    actor = ReviewActor(
        actor_id="reviewer-01",
        display_name="Human Reviewer",
        role="reviewer",
    )
    with pytest.raises(ValidationError, match="duplicate case IDs"):
        ReviewSession(
            session_version="firelens_review_session.v1",
            session_id=SESSION_ID,
            review_kind="semantic",
            artifact_sha256="a" * 64,
            protocol_sha256="b" * 64,
            created_at=START,
            case_ids=("case-001", "case-001"),
            actors=(actor,),
        )
