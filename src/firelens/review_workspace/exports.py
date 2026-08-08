"""Immutable, explicitly nonqualifying exports from finalized review sessions."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from firelens.review_workspace.journal import create_immutable_json
from firelens.review_workspace.session import BlindReviewSession, FinalizedReviewEvidence

_EVIDENCE_PATH: Literal["exports/finalized-evidence.json"] = "exports/finalized-evidence.json"
_RECEIPT_PATH = "exports/finalized-evidence.receipt.json"
_Model = TypeVar("_Model", bound=BaseModel)


class FinalizedEvidenceExportReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    receipt_version: Literal["firelens_finalized_review_export_receipt.v1"]
    implementation_status: Literal["nonqualifying_backend_scaffold"]
    qualification_eligible: Literal[False]
    session_id: str
    evidence_relative_path: Literal["exports/finalized-evidence.json"]
    evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_byte_count: int = Field(ge=1, strict=True)
    suite_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    finalization_event_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    exported_at: datetime


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )


def read_private_canonical(path: Path, model: type[_Model]) -> tuple[_Model, bytes]:
    flags = os.O_RDONLY | os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or stat.S_IMODE(metadata.st_mode) != 0o600
        ):
            raise ValueError("review export must be a private regular file")
        raw = os.read(descriptor, metadata.st_size + 1)
        if len(raw) != metadata.st_size:
            raise ValueError("review export changed while reading")
        current = path.lstat()
        if current.st_dev != metadata.st_dev or current.st_ino != metadata.st_ino:
            raise ValueError("review export path changed while reading")
    finally:
        os.close(descriptor)
    try:
        document = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("review export is invalid JSON") from exc
    if raw != _canonical_bytes(document):
        raise ValueError("review export is not canonical JSON")
    return model.model_validate(document), raw


def write_finalized_evidence_export(
    session: BlindReviewSession,
    *,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> FinalizedEvidenceExportReceipt:
    """Write one non-overwritable snapshot and its content-addressed receipt."""

    evidence_path = session.directory / _EVIDENCE_PATH
    receipt_path = session.directory / _RECEIPT_PATH
    if evidence_path.exists() or evidence_path.is_symlink():
        raise FileExistsError("refusing to overwrite finalized review evidence")
    if receipt_path.exists() or receipt_path.is_symlink():
        raise FileExistsError("refusing to overwrite finalized review export receipt")
    evidence = session.finalized_evidence()
    path = create_immutable_json(
        session.directory,
        _EVIDENCE_PATH,
        evidence,
        max_bytes=16 * 1024 * 1024,
    )
    _, raw = read_private_canonical(path, FinalizedReviewEvidence)
    adjudicator = next(actor for actor in evidence.actors if actor.actor.role == "adjudicator")
    exported_at = clock()
    if exported_at.tzinfo is None or exported_at.utcoffset() is None:
        raise ValueError("review export clock must return an offset-aware timestamp")
    receipt = FinalizedEvidenceExportReceipt(
        receipt_version="firelens_finalized_review_export_receipt.v1",
        implementation_status="nonqualifying_backend_scaffold",
        qualification_eligible=False,
        session_id=evidence.session.session_id,
        evidence_relative_path=_EVIDENCE_PATH,
        evidence_sha256=hashlib.sha256(raw).hexdigest(),
        evidence_byte_count=len(raw),
        suite_sha256=evidence.suite_sha256,
        finalization_event_hash=adjudicator.journal_head_hash,
        exported_at=exported_at.astimezone(UTC),
    )
    create_immutable_json(session.directory, _RECEIPT_PATH, receipt)
    verify_finalized_evidence_export(session.directory)
    return receipt


def verify_finalized_evidence_export(
    directory: Path,
) -> tuple[FinalizedReviewEvidence, FinalizedEvidenceExportReceipt]:
    """Recompute the export identity and reject altered or mismatched artifacts."""

    evidence, raw = read_private_canonical(
        directory / _EVIDENCE_PATH,
        FinalizedReviewEvidence,
    )
    receipt, _ = read_private_canonical(
        directory / _RECEIPT_PATH,
        FinalizedEvidenceExportReceipt,
    )
    adjudicator = next(actor for actor in evidence.actors if actor.actor.role == "adjudicator")
    expected = {
        "session_id": evidence.session.session_id,
        "evidence_sha256": hashlib.sha256(raw).hexdigest(),
        "evidence_byte_count": len(raw),
        "suite_sha256": evidence.suite_sha256,
        "finalization_event_hash": adjudicator.journal_head_hash,
    }
    for key, value in expected.items():
        if getattr(receipt, key) != value:
            raise ValueError(f"review export receipt disagrees with {key}")
    if (
        evidence.finalization.session_id != evidence.session.session_id
        or evidence.finalization.suite_sha256 != evidence.suite_sha256
        or evidence.finalization.actor_journal_heads.get(adjudicator.actor.actor_id)
        != adjudicator.journal_head_hash
    ):
        raise ValueError("review evidence finalization binding is inconsistent")
    return evidence, receipt
