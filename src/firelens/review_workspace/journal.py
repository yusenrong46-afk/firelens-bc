"""Crash-aware append-only JSONL storage for human-review evidence.

Every append is serialized under an exclusive advisory lock.  Existing bytes are
fully replayed and hash-validated before a new record is considered, so corruption
cannot silently become the prefix of a new valid chain.  This module intentionally
does not interpret review decisions; it preserves them for later protocol-specific
qualification code.
"""

from __future__ import annotations

import errno
import fcntl
import hashlib
import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from firelens.review_workspace.models import (
    GENESIS_EVENT_HASH,
    Identifier,
    ReviewEventDraft,
    ReviewJournalEvent,
)

_DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
_READ_FLAGS = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW
_APPEND_FLAGS = (
    os.O_APPEND | os.O_CREAT | os.O_WRONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
)
_IMMUTABLE_FLAGS = os.O_EXCL | os.O_CREAT | os.O_WRONLY | os.O_CLOEXEC | os.O_NOFOLLOW


class JournalLimits(BaseModel):
    """Bound memory, disk, and individual append sizes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_record_bytes: int = Field(default=64 * 1024, ge=1_024, le=1024 * 1024)
    max_file_bytes: int = Field(default=16 * 1024 * 1024, ge=1_024, le=512 * 1024 * 1024)
    max_records: int = Field(default=100_000, ge=1, le=1_000_000)


@dataclass(frozen=True)
class _SecureParent:
    root_fd: int
    parent_fd: int
    filename: str

    def close(self) -> None:
        if self.parent_fd != self.root_fd:
            os.close(self.parent_fd)
        os.close(self.root_fd)


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
        raise ValueError("review data is not canonical JSON") from exc
    return rendered.encode("utf-8")


def _canonical_model_bytes(model: BaseModel, *, exclude: set[str] | None = None) -> bytes:
    return _canonical_json_bytes(model.model_dump(mode="json", exclude=exclude or set()))


def _event_hash(event: ReviewJournalEvent) -> str:
    return hashlib.sha256(_canonical_model_bytes(event, exclude={"event_hash"})).hexdigest()


def _validate_relative_path(relative_path: str | Path) -> tuple[str, ...]:
    raw = os.fspath(relative_path)
    if not raw or "\x00" in raw:
        raise ValueError("artifact path must not be empty")
    path = PurePath(raw)
    if (
        not path.parts
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ValueError("artifact path must be a contained relative path")
    return path.parts


def _ensure_root(directory: Path, *, create: bool = True) -> Path:
    directory = directory.expanduser()
    created = False
    try:
        initial_metadata = directory.lstat()
    except FileNotFoundError:
        if not create:
            raise
        try:
            directory.mkdir(mode=0o700, parents=True, exist_ok=False)
        except FileExistsError:
            # A concurrent first writer may have created the same workspace.
            pass
        else:
            created = True
        initial_metadata = directory.lstat()
    if stat.S_ISLNK(initial_metadata.st_mode):
        raise ValueError(f"review workspace directory must not be a symlink: {directory}")
    if created:
        directory.chmod(0o700)
    metadata = directory.lstat()
    if not stat.S_ISDIR(metadata.st_mode):
        raise ValueError(f"review workspace path is not a directory: {directory}")
    if stat.S_IMODE(metadata.st_mode) != 0o700:
        raise PermissionError(f"review workspace directory must have mode 0700: {directory}")
    return directory


def _open_secure_parent(
    directory: Path,
    relative_path: str | Path,
    *,
    create: bool = True,
) -> _SecureParent:
    """Resolve a target beneath ``directory`` without following child symlinks."""

    root = _ensure_root(directory, create=create)
    parts = _validate_relative_path(relative_path)
    root_fd = os.open(root, _DIRECTORY_FLAGS)
    root_metadata = os.fstat(root_fd)
    path_metadata = root.lstat()
    if (root_metadata.st_dev, root_metadata.st_ino) != (
        path_metadata.st_dev,
        path_metadata.st_ino,
    ):
        os.close(root_fd)
        raise ValueError("review workspace directory changed while it was opened")
    current_fd = root_fd
    try:
        for component in parts[:-1]:
            created = False
            try:
                next_fd = os.open(component, _DIRECTORY_FLAGS, dir_fd=current_fd)
            except FileNotFoundError:
                if not create:
                    raise
                try:
                    os.mkdir(component, mode=0o700, dir_fd=current_fd)
                except FileExistsError:
                    # Another locked journal instance can establish this path first.
                    pass
                else:
                    os.fsync(current_fd)
                    created = True
                next_fd = os.open(component, _DIRECTORY_FLAGS, dir_fd=current_fd)
            if created:
                os.fchmod(next_fd, 0o700)
            metadata = os.fstat(next_fd)
            if not stat.S_ISDIR(metadata.st_mode):
                os.close(next_fd)
                raise ValueError(f"review workspace component is not a directory: {component}")
            if stat.S_IMODE(metadata.st_mode) != 0o700:
                os.close(next_fd)
                raise PermissionError(
                    f"review workspace subdirectory must have mode 0700: {component}"
                )
            if current_fd != root_fd:
                os.close(current_fd)
            current_fd = next_fd
        return _SecureParent(root_fd=root_fd, parent_fd=current_fd, filename=parts[-1])
    except Exception:
        if current_fd != root_fd:
            os.close(current_fd)
        os.close(root_fd)
        raise


def _validate_regular_private_file(descriptor: int, *, label: str) -> os.stat_result:
    metadata = os.fstat(descriptor)
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError(f"{label} is not a regular file")
    if metadata.st_nlink != 1:
        raise ValueError(f"{label} has an unexpected hard-link count")
    if stat.S_IMODE(metadata.st_mode) != 0o600:
        raise PermissionError(f"{label} must have mode 0600")
    return metadata


def _open_journal_for_append(secure_parent: _SecureParent) -> tuple[int, bool]:
    """Open the journal without letting a special file block the process."""

    try:
        descriptor = os.open(
            secure_parent.filename,
            _APPEND_FLAGS | os.O_EXCL,
            0o600,
            dir_fd=secure_parent.parent_fd,
        )
    except FileExistsError:
        pass
    else:
        os.fchmod(descriptor, 0o600)
        _validate_regular_private_file(descriptor, label="review journal")
        os.fsync(descriptor)
        os.fsync(secure_parent.parent_fd)
        return descriptor, True

    path_metadata = os.stat(
        secure_parent.filename,
        dir_fd=secure_parent.parent_fd,
        follow_symlinks=False,
    )
    if stat.S_ISLNK(path_metadata.st_mode):
        raise ValueError("review journal must not be a symlink")
    if not stat.S_ISREG(path_metadata.st_mode):
        raise ValueError("review journal is not a regular file")
    if path_metadata.st_nlink != 1:
        raise ValueError("review journal has an unexpected hard-link count")
    if stat.S_IMODE(path_metadata.st_mode) != 0o600:
        raise PermissionError("review journal must have mode 0600")
    descriptor = os.open(
        secure_parent.filename,
        _APPEND_FLAGS,
        0o600,
        dir_fd=secure_parent.parent_fd,
    )
    descriptor_metadata = _validate_regular_private_file(descriptor, label="review journal")
    if (path_metadata.st_dev, path_metadata.st_ino) != (
        descriptor_metadata.st_dev,
        descriptor_metadata.st_ino,
    ):
        os.close(descriptor)
        raise ValueError("review journal path changed while it was opened")
    return descriptor, False


def _open_journal_for_read(secure_parent: _SecureParent) -> int:
    """Open an existing journal without creating or mutating workspace state."""

    path_metadata = os.stat(
        secure_parent.filename,
        dir_fd=secure_parent.parent_fd,
        follow_symlinks=False,
    )
    if stat.S_ISLNK(path_metadata.st_mode):
        raise ValueError("review journal must not be a symlink")
    if not stat.S_ISREG(path_metadata.st_mode):
        raise ValueError("review journal is not a regular file")
    descriptor = os.open(
        secure_parent.filename,
        _READ_FLAGS,
        dir_fd=secure_parent.parent_fd,
    )
    descriptor_metadata = _validate_regular_private_file(descriptor, label="review journal")
    if (path_metadata.st_dev, path_metadata.st_ino) != (
        descriptor_metadata.st_dev,
        descriptor_metadata.st_ino,
    ):
        os.close(descriptor)
        raise ValueError("review journal path changed while it was opened")
    return descriptor


def _assert_descriptor_is_current_path(
    secure_parent: _SecureParent,
    descriptor: int,
) -> os.stat_result:
    """Reject rename/unlink replacement while a locked descriptor is in use."""

    descriptor_metadata = _validate_regular_private_file(descriptor, label="review journal")
    try:
        path_metadata = os.stat(
            secure_parent.filename,
            dir_fd=secure_parent.parent_fd,
            follow_symlinks=False,
        )
    except FileNotFoundError as exc:
        raise ValueError("review journal path disappeared while it was open") from exc
    if not stat.S_ISREG(path_metadata.st_mode):
        raise ValueError("review journal path is no longer a regular file")
    if (path_metadata.st_dev, path_metadata.st_ino) != (
        descriptor_metadata.st_dev,
        descriptor_metadata.st_ino,
    ):
        raise ValueError("review journal path changed while it was open")
    return descriptor_metadata


def _read_all(descriptor: int, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        chunk = os.read(descriptor, min(remaining, 1024 * 1024))
        if not chunk:
            raise ValueError("review journal changed while it was being read")
        chunks.append(chunk)
        remaining -= len(chunk)
    if os.read(descriptor, 1):
        raise ValueError("review journal grew while it was being read")
    return b"".join(chunks)


def _same_request(existing: ReviewJournalEvent, draft: ReviewEventDraft) -> bool:
    """Compare semantic request bytes while allowing retry-time timestamp drift."""

    existing_request = existing.as_draft().model_dump(mode="json", exclude={"timestamp"})
    draft_request = draft.model_dump(mode="json", exclude={"timestamp"})
    return _canonical_json_bytes(existing_request) == _canonical_json_bytes(draft_request)


class AppendOnlyReviewJournal:
    """A per-session durable event chain stored as canonical UTF-8 JSONL."""

    def __init__(
        self,
        directory: Path,
        *,
        session_id: str,
        relative_path: str | Path = "events.jsonl",
        limits: JournalLimits | None = None,
    ) -> None:
        self.directory = directory
        self.session_id = TypeAdapter(Identifier).validate_python(session_id)
        self.relative_path = relative_path
        self.limits = limits or JournalLimits()

    def replay(self) -> tuple[ReviewJournalEvent, ...]:
        """Read and validate the complete journal chain under an exclusive lock."""

        _validate_relative_path(self.relative_path)
        try:
            secure_parent = _open_secure_parent(
                self.directory,
                self.relative_path,
                create=False,
            )
        except FileNotFoundError:
            return ()
        read_fd: int | None = None
        try:
            try:
                read_fd = _open_journal_for_read(secure_parent)
            except FileNotFoundError:
                return ()
            fcntl.flock(read_fd, fcntl.LOCK_SH)
            events = self._replay_descriptor(read_fd)
            _assert_descriptor_is_current_path(secure_parent, read_fd)
            return events
        finally:
            if read_fd is not None:
                try:
                    fcntl.flock(read_fd, fcntl.LOCK_UN)
                finally:
                    os.close(read_fd)
            secure_parent.close()

    def append(self, draft: ReviewEventDraft) -> ReviewJournalEvent:
        """Append one event or return its already-durable idempotent predecessor."""

        if draft.session_id != self.session_id:
            raise ValueError("event session_id does not match its journal")
        secure_parent = _open_secure_parent(self.directory, self.relative_path)
        append_fd: int | None = None
        try:
            append_fd, _created = _open_journal_for_append(secure_parent)
            fcntl.flock(append_fd, fcntl.LOCK_EX)
            _assert_descriptor_is_current_path(secure_parent, append_fd)
            events = self._replay_locked(secure_parent, append_fd)
            for existing in events:
                if existing.idempotency_key != draft.idempotency_key:
                    continue
                if _same_request(existing, draft):
                    return existing
                raise ValueError("idempotency key already exists for a different request")

            if events and draft.timestamp <= events[-1].timestamp:
                raise ValueError("event timestamps must be strictly increasing")
            if len(events) >= self.limits.max_records:
                raise ValueError("review journal record limit exceeded")

            previous_hash = events[-1].event_hash if events else GENESIS_EVENT_HASH
            unsigned = ReviewJournalEvent(
                event_version="firelens_review_journal_event.v1",
                sequence=len(events) + 1,
                event_type=draft.event_type,
                session_id=draft.session_id,
                actor_id=draft.actor_id,
                case_id=draft.case_id,
                idempotency_key=draft.idempotency_key,
                presentation_id=draft.presentation_id,
                payload=draft.payload,
                timestamp=draft.timestamp,
                previous_event_hash=previous_hash,
                event_hash=GENESIS_EVENT_HASH,
            )
            event = unsigned.model_copy(update={"event_hash": _event_hash(unsigned)})
            record = _canonical_model_bytes(event) + b"\n"
            if len(record) > self.limits.max_record_bytes:
                raise ValueError("review journal record limit exceeded")

            metadata = _assert_descriptor_is_current_path(secure_parent, append_fd)
            if metadata.st_size + len(record) > self.limits.max_file_bytes:
                raise ValueError("review journal file limit exceeded")
            written = os.write(append_fd, record)
            if written != len(record):
                os.ftruncate(append_fd, metadata.st_size)
                os.fsync(append_fd)
                raise OSError("short append while writing review journal")
            os.fsync(append_fd)
            _assert_descriptor_is_current_path(secure_parent, append_fd)
            os.fsync(secure_parent.parent_fd)
            return event
        finally:
            if append_fd is not None:
                try:
                    fcntl.flock(append_fd, fcntl.LOCK_UN)
                finally:
                    os.close(append_fd)
            secure_parent.close()

    def _replay_locked(
        self,
        secure_parent: _SecureParent,
        append_fd: int,
    ) -> tuple[ReviewJournalEvent, ...]:
        append_metadata = _validate_regular_private_file(append_fd, label="review journal")
        if append_metadata.st_size > self.limits.max_file_bytes:
            raise ValueError("review journal file limit exceeded")
        read_fd = os.open(
            secure_parent.filename,
            _READ_FLAGS,
            dir_fd=secure_parent.parent_fd,
        )
        try:
            read_metadata = _validate_regular_private_file(read_fd, label="review journal")
            if (read_metadata.st_dev, read_metadata.st_ino) != (
                append_metadata.st_dev,
                append_metadata.st_ino,
            ):
                raise ValueError("review journal path changed while it was opened")
            raw = _read_all(read_fd, read_metadata.st_size)
        finally:
            os.close(read_fd)
        return self._validate_chain(raw)

    def _replay_descriptor(self, read_fd: int) -> tuple[ReviewJournalEvent, ...]:
        metadata = _validate_regular_private_file(read_fd, label="review journal")
        if metadata.st_size > self.limits.max_file_bytes:
            raise ValueError("review journal file limit exceeded")
        os.lseek(read_fd, 0, os.SEEK_SET)
        return self._validate_chain(_read_all(read_fd, metadata.st_size))

    def _validate_chain(self, raw: bytes) -> tuple[ReviewJournalEvent, ...]:
        if not raw:
            return ()
        if not raw.endswith(b"\n"):
            raise ValueError("review journal ends with a truncated partial record")
        lines = raw[:-1].split(b"\n")
        if len(lines) > self.limits.max_records:
            raise ValueError("review journal record limit exceeded")

        events: list[ReviewJournalEvent] = []
        seen_idempotency: set[str] = set()
        previous_hash: str = GENESIS_EVENT_HASH
        previous_timestamp = None
        for index, line in enumerate(lines, start=1):
            if not line:
                raise ValueError("review journal contains an empty record")
            if len(line) + 1 > self.limits.max_record_bytes:
                raise ValueError("review journal record limit exceeded")
            try:
                document = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError(f"invalid review journal record at sequence {index}") from exc
            if _canonical_json_bytes(document) != line:
                raise ValueError(f"non-canonical review journal record at sequence {index}")
            event = ReviewJournalEvent.model_validate(document)
            if _canonical_model_bytes(event) != line:
                raise ValueError(f"non-canonical review journal model at sequence {index}")
            if event.sequence != index:
                raise ValueError(f"review journal sequence mismatch at record {index}")
            if event.session_id != self.session_id:
                raise ValueError(f"review journal session mismatch at record {index}")
            if event.previous_event_hash != previous_hash:
                raise ValueError(f"review journal chain mismatch at record {index}")
            if event.event_hash != _event_hash(event):
                raise ValueError(f"review journal event hash mismatch at record {index}")
            if event.idempotency_key in seen_idempotency:
                raise ValueError(f"duplicate idempotency key at record {index}")
            if previous_timestamp is not None and event.timestamp <= previous_timestamp:
                raise ValueError(f"non-monotonic timestamp at record {index}")
            seen_idempotency.add(event.idempotency_key)
            previous_hash = event.event_hash
            previous_timestamp = event.timestamp
            events.append(event)
        return tuple(events)


def create_immutable_json(
    directory: Path,
    relative_path: str | Path,
    value: BaseModel | dict[str, Any],
    *,
    max_bytes: int = 1024 * 1024,
) -> Path:
    """Create one canonical private JSON receipt and never overwrite it.

    Intended uses are session manifests, finalization receipts, and export receipts.
    The caller chooses the filename so those different artifact classes stay explicit.
    """

    if max_bytes < 1 or max_bytes > 16 * 1024 * 1024:
        raise ValueError("immutable artifact max_bytes is out of bounds")
    document = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    encoded = _canonical_json_bytes(document) + b"\n"
    if len(encoded) > max_bytes:
        raise ValueError("immutable artifact size limit exceeded")

    secure_parent = _open_secure_parent(directory, relative_path)
    descriptor: int | None = None
    created = False
    try:
        try:
            descriptor = os.open(
                secure_parent.filename,
                _IMMUTABLE_FLAGS,
                0o600,
                dir_fd=secure_parent.parent_fd,
            )
            created = True
        except OSError as exc:
            if exc.errno in {errno.EEXIST, errno.ELOOP}:
                raise FileExistsError(
                    f"refusing to overwrite immutable review artifact: {relative_path}"
                ) from exc
            raise
        os.fchmod(descriptor, 0o600)
        _validate_regular_private_file(descriptor, label="immutable review artifact")
        written = os.write(descriptor, encoded)
        if written != len(encoded):
            raise OSError("short write while creating immutable review artifact")
        os.fsync(descriptor)
        os.fsync(secure_parent.parent_fd)
    except Exception:
        if descriptor is not None:
            os.close(descriptor)
            descriptor = None
        if created:
            try:
                os.unlink(secure_parent.filename, dir_fd=secure_parent.parent_fd)
                os.fsync(secure_parent.parent_fd)
            except FileNotFoundError:
                pass
        raise
    finally:
        if descriptor is not None:
            os.close(descriptor)
        secure_parent.close()

    root = _ensure_root(directory)
    result = root.joinpath(*_validate_relative_path(relative_path))
    resolved_parent = result.parent.resolve(strict=True)
    if root != resolved_parent and root not in resolved_parent.parents:
        raise ValueError("immutable artifact escaped the review workspace")
    return result
