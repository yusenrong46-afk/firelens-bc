"""Fail-closed conversion of verified blind-review evidence into release sidecars.

The private workspace remains the source of truth.  Conversion is allowed only after
an independent human attests that the storage and external-anchor controls were
reviewed.  The public qualification manifest is content-free: it preserves identities,
hashes, journal heads, agreement counts, and the adjudicated disposition without
copying questions, answers, passages, or notes.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from firelens.benchmark import file_sha256
from firelens.owner_review import (
    CaseReview,
    ClaimReview,
    OwnerSemanticReview,
    validate_owner_review,
)
from firelens.retrieval_review import (
    RetrievalCaseReview,
    RetrievalOwnerReview,
    validate_retrieval_owner_review,
)
from firelens.review_workspace.analysis import verify_review_analysis
from firelens.review_workspace.exports import verify_finalized_evidence_export
from firelens.review_workspace.preparation import resume_prepared_review
from firelens.review_workspace.session import FinalizedReviewEvidence

_PLACEHOLDER_NAMES = frozenset(
    {
        "adjudicator",
        "chatgpt",
        "human reviewer",
        "independent reviewer",
        "owner",
        "reviewer",
        "storage reviewer",
        "tbd",
        "unknown",
    }
)


class _ReviewRecipe(Protocol):
    @property
    def suite_kind(self) -> str: ...

    @property
    def conversation_report(self) -> object: ...

    @property
    def retrieval_dataset(self) -> object: ...


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class StorageReviewChecks(_FrozenModel):
    private_permissions_confirmed: Literal[True]
    no_symlink_or_hardlink_findings: Literal[True]
    journal_receipts_replayed: Literal[True]
    finalized_export_and_analysis_recomputed: Literal[True]
    external_final_head_anchor_retained: Literal[True]
    no_open_storage_findings: Literal[True]


class IndependentStorageAttestation(_FrozenModel):
    attestation_version: Literal["firelens_independent_storage_attestation.v1"]
    session_id: str = Field(min_length=1, max_length=128)
    suite_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    finalized_evidence_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    review_analysis_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    finalization_event_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    reviewer_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:@-]{2,127}$")
    reviewer_name: str = Field(min_length=2, max_length=200)
    reviewed_at: datetime
    external_anchor_reference: str = Field(min_length=3, max_length=500)
    checks: StorageReviewChecks
    decision: Literal["approve"]
    notes: str = Field(default="", max_length=4_000)

    @field_validator("reviewer_name")
    @classmethod
    def reviewer_is_named_human(cls, value: str) -> str:
        normalized = value.strip()
        lowered = normalized.casefold()
        if (
            lowered in _PLACEHOLDER_NAMES
            or "gpt" in lowered
            or "model" in lowered
            or not re.search(r"[A-Za-z]", normalized)
        ):
            raise ValueError("storage attestation requires a named human reviewer")
        return normalized

    @field_validator("reviewed_at")
    @classmethod
    def reviewed_at_is_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("storage review timestamp must include a UTC offset")
        return value.astimezone(UTC)


class QualifiedActor(_FrozenModel):
    actor_id: str
    display_name: str
    role: Literal["reviewer", "adjudicator"]
    journal_head_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    journal_count: int = Field(ge=1, strict=True)


class ReviewQualificationManifest(_FrozenModel):
    qualification_version: Literal["firelens_blind_review_qualification.v1"]
    qualified: Literal[True]
    suite_kind: Literal["conversation", "retrieval"]
    session_id: str
    suite_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    dataset_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_artifact_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    protocol_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    finalized_evidence_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    finalized_evidence_byte_count: int = Field(ge=1, strict=True)
    review_analysis_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    storage_attestation_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    review_sidecar_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    review_summary_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    finalization_event_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    finalized_at: datetime
    qualified_at: datetime
    actors: tuple[QualifiedActor, ...] = Field(min_length=3, max_length=3)
    independent_storage_reviewer_id: str
    independent_storage_reviewer_name: str
    external_anchor_reference: str
    storage_checks: StorageReviewChecks
    initial_disagreement_case_count: int = Field(ge=0, strict=True)
    adjudicated_finding_case_count: Literal[0]
    adjudicator_needs_discussion_case_count: Literal[0]
    adjudicated_unsupported_claim_count: Literal[0]
    adjudicated_unclear_claim_count: Literal[0]
    all_adjudicated_cases_clear: Literal[True]
    case_count: int = Field(ge=1, strict=True)

    @model_validator(mode="after")
    def actor_roster_is_complete(self) -> ReviewQualificationManifest:
        roles = [actor.role for actor in self.actors]
        if roles.count("reviewer") != 2 or roles.count("adjudicator") != 1:
            raise ValueError(
                "qualification manifest requires two reviewers and one adjudicator"
            )
        names = [actor.display_name.casefold() for actor in self.actors]
        names.append(self.independent_storage_reviewer_name.casefold())
        if len(names) != len(set(names)):
            raise ValueError("storage reviewer must be independent from all session actors")
        actor_ids = [actor.actor_id.casefold() for actor in self.actors]
        if self.independent_storage_reviewer_id.casefold() in actor_ids:
            raise ValueError("storage reviewer must be independent from all session actors")
        return self


def _load_private_attestation(
    path: Path,
) -> tuple[IndependentStorageAttestation, str]:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ValueError("storage attestation must be one private 0600 regular file") from exc
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_size > 128 * 1024
        ):
            raise ValueError("storage attestation must be one private 0600 regular file")
        content = bytearray()
        while chunk := os.read(descriptor, min(65_536, 128 * 1024 + 1 - len(content))):
            content.extend(chunk)
            if len(content) > 128 * 1024:
                raise ValueError("storage attestation must be one private 0600 regular file")
        current = path.lstat()
        if (current.st_dev, current.st_ino) != (metadata.st_dev, metadata.st_ino):
            raise ValueError("storage attestation changed while it was being read")
    except OSError as exc:
        raise ValueError("storage attestation is not readable YAML/JSON") from exc
    finally:
        os.close(descriptor)
    raw = bytes(content)
    try:
        payload = yaml.safe_load(raw.decode("utf-8"))
    except (UnicodeDecodeError, yaml.YAMLError) as exc:
        raise ValueError("storage attestation is not readable YAML/JSON") from exc
    return IndependentStorageAttestation.model_validate(payload), hashlib.sha256(
        raw
    ).hexdigest()


def storage_attestation_template(workspace: Path) -> dict[str, object]:
    """Return an unapproved template bound to the verified private workspace."""

    coordinator, launch, _tokens = resume_prepared_review(workspace)
    evidence, export_receipt = verify_finalized_evidence_export(workspace)
    _analysis, analysis_receipt = verify_review_analysis(workspace)
    adjudicator = next(actor for actor in evidence.actors if actor.actor.role == "adjudicator")
    return {
        "attestation_version": "firelens_independent_storage_attestation.v1",
        "session_id": launch.session.session_id,
        "suite_sha256": coordinator.suite.suite_sha256,
        "finalized_evidence_sha256": export_receipt.evidence_sha256,
        "review_analysis_sha256": analysis_receipt.analysis_sha256,
        "finalization_event_hash": adjudicator.journal_head_hash,
        "reviewer_id": None,
        "reviewer_name": None,
        "reviewed_at": None,
        "external_anchor_reference": None,
        "checks": {
            "private_permissions_confirmed": False,
            "no_symlink_or_hardlink_findings": False,
            "journal_receipts_replayed": False,
            "finalized_export_and_analysis_recomputed": False,
            "external_final_head_anchor_retained": False,
            "no_open_storage_findings": False,
        },
        "decision": "pending",
        "notes": "",
    }


def _write_private(path: Path, text: str) -> None:
    if path.exists() or path.is_symlink():
        raise FileExistsError(f"refusing to overwrite review qualification artifact: {path}")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(text, encoding="utf-8")
    path.chmod(0o600)


def write_storage_attestation_template(workspace: Path, output: Path) -> None:
    _write_private(
        output,
        yaml.safe_dump(storage_attestation_template(workspace), sort_keys=False),
    )


def _semantic_sidecar(
    evidence: FinalizedReviewEvidence, report_path: Path
) -> OwnerSemanticReview:
    adjudicator = next(actor for actor in evidence.actors if actor.actor.role == "adjudicator")
    return OwnerSemanticReview(
        review_version="firelens_owner_semantic_review.v1",
        report_sha256=file_sha256(report_path),
        reviewer=adjudicator.actor.display_name,
        reviewed_at=evidence.finalization.finalized_at,
        cases=[
            CaseReview(
                case_id=row.case_id,
                required_concepts_present=bool(row.decision.required_concepts_present),
                forbidden_claims_absent=bool(row.decision.forbidden_claims_absent),
                required_limitations_present=bool(row.decision.required_limitations_present),
                decision=row.decision.disposition,
                claims=[
                    ClaimReview(
                        claim_id=claim.claim_id,
                        decision=claim.decision,
                        notes="",
                    )
                    for claim in row.decision.claims
                ],
                notes="",
            )
            for row in adjudicator.decisions
        ],
    )


def _retrieval_sidecar(
    evidence: FinalizedReviewEvidence, dataset_path: Path
) -> RetrievalOwnerReview:
    adjudicator = next(actor for actor in evidence.actors if actor.actor.role == "adjudicator")
    return RetrievalOwnerReview(
        review_version="firelens_retrieval_owner_review.v1",
        dataset_sha256=file_sha256(dataset_path),
        reviewer=adjudicator.actor.display_name,
        reviewed_at=evidence.finalization.finalized_at,
        cases=[
            RetrievalCaseReview(
                case_id=row.case_id,
                question_is_independent=bool(row.decision.question_is_independent),
                answerability_correct=bool(row.decision.answerability_correct),
                acceptable_evidence_correct=bool(row.decision.acceptable_evidence_correct),
                decision=row.decision.disposition,
                notes="",
            )
            for row in adjudicator.decisions
        ],
    )


def build_review_qualification(
    workspace: Path,
    attestation_path: Path,
    output_directory: Path,
) -> ReviewQualificationManifest:
    """Create a closed qualification package after independent storage approval."""

    if output_directory.exists() or output_directory.is_symlink():
        raise FileExistsError("refusing to overwrite review qualification directory")
    coordinator, launch, _tokens = resume_prepared_review(workspace)
    evidence, export_receipt = verify_finalized_evidence_export(workspace)
    analysis, analysis_receipt = verify_review_analysis(workspace)
    attestation, attestation_sha256 = _load_private_attestation(attestation_path)
    if launch.input_recipe.suite_kind not in {"conversation", "retrieval"}:
        raise ValueError("qualification adapter currently supports conversation and retrieval")
    adjudicator = next(actor for actor in evidence.actors if actor.actor.role == "adjudicator")
    expected = {
        "session_id": evidence.session.session_id,
        "suite_sha256": evidence.suite_sha256,
        "finalized_evidence_sha256": export_receipt.evidence_sha256,
        "review_analysis_sha256": analysis_receipt.analysis_sha256,
        "finalization_event_hash": adjudicator.journal_head_hash,
    }
    for key, value in expected.items():
        if getattr(attestation, key) != value:
            raise ValueError(f"storage attestation disagrees with {key}")
    actor_names = {actor.actor.display_name.casefold() for actor in evidence.actors}
    actor_ids = {actor.actor.actor_id.casefold() for actor in evidence.actors}
    if (
        attestation.reviewer_name.casefold() in actor_names
        or attestation.reviewer_id.casefold() in actor_ids
    ):
        raise ValueError("storage reviewer must be independent from session actors")
    if attestation.reviewed_at < analysis.generated_at:
        raise ValueError("storage attestation predates the verified review analysis")
    if not analysis.all_adjudicated_cases_clear:
        raise ValueError("adjudicated human findings block review qualification")
    if any(
        (
            analysis.adjudicated_finding_case_count,
            analysis.adjudicator_needs_discussion_case_count,
            analysis.adjudicated_unsupported_claim_count,
            analysis.adjudicated_unclear_claim_count,
        )
    ):
        raise ValueError("adjudicated review counts contradict a clear qualification")

    parent = output_directory.parent.resolve(strict=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output_directory.name}.staging-", dir=parent))
    staging.chmod(0o700)
    sidecar_path = staging / "review-sidecar.yaml"
    summary_path = staging / "review-summary.json"
    manifest_path = staging / "review-qualification.json"
    try:
        source_path, summary = _build_qualification_sidecar(
            launch.input_recipe, evidence, sidecar_path
        )
        if summary.get("qualified") is not True:
            raise ValueError("adjudicated sidecar does not satisfy the release review contract")
        _write_private(
            summary_path,
            json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        )
        actors = _qualified_actors(evidence)
        manifest = ReviewQualificationManifest(
            qualification_version="firelens_blind_review_qualification.v1",
            qualified=True,
            suite_kind=launch.input_recipe.suite_kind,
            session_id=evidence.session.session_id,
            suite_sha256=evidence.suite_sha256,
            dataset_sha256=evidence.dataset_sha256,
            source_artifact_sha256=file_sha256(source_path),
            protocol_sha256=evidence.session.protocol_sha256,
            finalized_evidence_sha256=export_receipt.evidence_sha256,
            finalized_evidence_byte_count=export_receipt.evidence_byte_count,
            review_analysis_sha256=analysis_receipt.analysis_sha256,
            storage_attestation_sha256=attestation_sha256,
            review_sidecar_sha256=file_sha256(sidecar_path),
            review_summary_sha256=file_sha256(summary_path),
            finalization_event_hash=adjudicator.journal_head_hash,
            finalized_at=evidence.finalization.finalized_at,
            qualified_at=attestation.reviewed_at,
            actors=actors,
            independent_storage_reviewer_id=attestation.reviewer_id,
            independent_storage_reviewer_name=attestation.reviewer_name,
            external_anchor_reference=attestation.external_anchor_reference,
            storage_checks=attestation.checks,
            initial_disagreement_case_count=analysis.initial_disagreement_case_count,
            adjudicated_finding_case_count=0,
            adjudicator_needs_discussion_case_count=0,
            adjudicated_unsupported_claim_count=0,
            adjudicated_unclear_claim_count=0,
            all_adjudicated_cases_clear=True,
            case_count=analysis.case_count,
        )
        _write_private(
            manifest_path,
            json.dumps(
                manifest.model_dump(mode="json"),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
        )
        verified = verify_review_qualification_package(
            manifest_path,
            source_path=source_path,
            sidecar_path=sidecar_path,
            summary_path=summary_path,
            attestation_path=attestation_path,
        )
        os.rename(staging, output_directory)
        return verified
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise


def _build_qualification_sidecar(
    recipe: _ReviewRecipe, evidence: FinalizedReviewEvidence, sidecar_path: Path
) -> tuple[Path, dict[str, object]]:
    count = len(evidence.session.case_ids)
    if recipe.suite_kind == "conversation":
        source_path = Path(str(recipe.conversation_report))
        sidecar = _semantic_sidecar(evidence, source_path)
        _write_private(
            sidecar_path, yaml.safe_dump(sidecar.model_dump(mode="json"), sort_keys=False)
        )
        return source_path, validate_owner_review(
            source_path, sidecar_path, expected_case_count=count
        )
    source_path = Path(str(recipe.retrieval_dataset))
    retrieval_sidecar = _retrieval_sidecar(evidence, source_path)
    _write_private(
        sidecar_path,
        yaml.safe_dump(retrieval_sidecar.model_dump(mode="json"), sort_keys=False),
    )
    return source_path, validate_retrieval_owner_review(
        source_path, sidecar_path, expected_case_count=count
    )


def _qualified_actors(evidence: FinalizedReviewEvidence) -> tuple[QualifiedActor, ...]:
    actors: list[QualifiedActor] = []
    for actor in evidence.actors:
        if actor.actor.role not in {"reviewer", "adjudicator"}:
            raise ValueError("qualification evidence contains a non-review actor")
        actors.append(
            QualifiedActor(
                actor_id=actor.actor.actor_id,
                display_name=actor.actor.display_name,
                role=actor.actor.role,
                journal_head_hash=actor.journal_head_hash,
                journal_count=actor.journal_count,
            )
        )
    return tuple(actors)


def verify_review_qualification_package(
    manifest_path: Path,
    *,
    source_path: Path,
    sidecar_path: Path,
    summary_path: Path,
    attestation_path: Path | None = None,
    expected_suite_kind: Literal["conversation", "retrieval"] | None = None,
    expected_case_count: int | None = None,
) -> ReviewQualificationManifest:
    """Recompute the verdict and verify the content-free release package."""

    try:
        manifest = ReviewQualificationManifest.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise ValueError("review qualification manifest is invalid") from exc
    if expected_suite_kind is not None and manifest.suite_kind != expected_suite_kind:
        raise ValueError("review qualification suite kind mismatch")
    if expected_case_count is not None and manifest.case_count != expected_case_count:
        raise ValueError("review qualification case count mismatch")
    expected_hashes = {
        "source_artifact_sha256": file_sha256(source_path),
        "review_sidecar_sha256": file_sha256(sidecar_path),
        "review_summary_sha256": file_sha256(summary_path),
    }
    for key, value in expected_hashes.items():
        if getattr(manifest, key) != value:
            raise ValueError(f"review qualification manifest disagrees with {key}")
    try:
        submitted_summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("review qualification summary is invalid JSON") from exc
    if not isinstance(submitted_summary, dict):
        raise ValueError("review qualification summary must be a JSON object")
    recomputed_summary = _recomputed_review_summary(manifest, source_path, sidecar_path)
    submitted_evidence = {
        key: value for key, value in submitted_summary.items() if key != "generated_at"
    }
    recomputed_evidence = {
        key: value for key, value in recomputed_summary.items() if key != "generated_at"
    }
    if submitted_evidence != recomputed_evidence:
        raise ValueError("review qualification summary differs from validated evidence")
    if recomputed_summary.get("qualified") is not True:
        raise ValueError("review qualification evidence does not satisfy the release contract")
    if attestation_path is None:
        raise ValueError("private storage attestation is required to verify qualification")
    _validate_manifest_attestation(manifest, attestation_path)
    return manifest


def _recomputed_review_summary(
    manifest: ReviewQualificationManifest, source_path: Path, sidecar_path: Path
) -> dict[str, object]:
    if manifest.suite_kind == "conversation":
        return validate_owner_review(
            source_path, sidecar_path, expected_case_count=manifest.case_count
        )
    return validate_retrieval_owner_review(
        source_path, sidecar_path, expected_case_count=manifest.case_count
    )


def _validate_manifest_attestation(
    manifest: ReviewQualificationManifest, attestation_path: Path
) -> None:
    attestation, digest = _load_private_attestation(attestation_path)
    expectations: dict[str, object] = {
        "storage_attestation_sha256": digest,
        "session_id": attestation.session_id,
        "suite_sha256": attestation.suite_sha256,
        "finalized_evidence_sha256": attestation.finalized_evidence_sha256,
        "review_analysis_sha256": attestation.review_analysis_sha256,
        "finalization_event_hash": attestation.finalization_event_hash,
        "independent_storage_reviewer_id": attestation.reviewer_id,
        "independent_storage_reviewer_name": attestation.reviewer_name,
        "external_anchor_reference": attestation.external_anchor_reference,
        "qualified_at": attestation.reviewed_at,
        "storage_checks": attestation.checks,
    }
    for key, expected in expectations.items():
        if getattr(manifest, key) != expected:
            raise ValueError(f"review qualification manifest disagrees with {key}")
