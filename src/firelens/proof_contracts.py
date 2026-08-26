"""Proof-card wire contracts and their deterministic safety-profile constructor."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, HttpUrl, model_validator

from firelens._publication_authority import (
    _UNSUPPORTED_PUBLICATION,
    _proof_card_publication_error,
)
from firelens.contract_base import FrozenStrictModel
from firelens.derivation_policy import derivation_policy_errors
from firelens.live_contracts import (
    DISTANCE_ALGORITHM,
    DISTANCE_UNIT,
    GEODESIC_CRS,
    DistanceDerivation,
)
from firelens.publication_contracts import PublicationAuthority
from firelens.safety_profile import (
    PublicationState,
    TruthClass,
    bind_proof_profile,
    verified_critical_metadata_present,
)

SupportState = Literal[
    "supported",
    "structured_reviewed",
    "official_live_typed",
    "official_quote_only",
    "source_linked_explanation",
    "unknown",
    "background",
    "conflict",
    "live_record",
]


class AnswerStatusBanner(FrozenStrictModel):
    headline: str = Field(min_length=1, max_length=120)
    detail: str = Field(min_length=1, max_length=500)
    freshness_label: str = Field(min_length=1, max_length=80)
    availability_label: str = Field(min_length=1, max_length=160)
    retrieval_completed_at: datetime | None = None
    source_updated_at: datetime | None = None
    official_escalation_title: str | None = Field(default=None, max_length=120)
    official_escalation_url: HttpUrl | None = None


class ProofCard(FrozenStrictModel):
    claim_id: str = Field(min_length=1, max_length=200)
    claim_text: str = Field(min_length=1, max_length=600)
    support_state: SupportState
    support_label: str = Field(min_length=1, max_length=120)
    authority: str = Field(min_length=1, max_length=160)
    exact_passage: str | None = Field(default=None, max_length=500)
    source_title: str | None = Field(default=None, max_length=200)
    source_revision: str | None = Field(default=None, max_length=200)
    review_state: str = Field(min_length=1, max_length=120)
    critical_fields_checked: str = Field(min_length=1, max_length=160)
    freshness: str = Field(min_length=1, max_length=80)
    conflicts_or_unknowns: list[str] = Field(default_factory=list, max_length=8)
    official_url: HttpUrl | None = None
    truth_class: TruthClass
    publication_state: PublicationState
    derivation: DistanceDerivation | None = None
    publication: PublicationAuthority

    @model_validator(mode="after")
    def profile_metadata_matches_support_state(self) -> ProofCard:
        expected_truth, expected_state = bind_proof_profile(
            self.support_state, freshness=self.freshness
        )
        if self.truth_class != expected_truth or self.publication_state != expected_state:
            raise ValueError(
                "proof card profile metadata must match support state and freshness"
            )
        publication_error = _proof_card_publication_error(self)
        if publication_error:
            raise ValueError(publication_error)
        if (
            expected_state is PublicationState.VERIFIED
            and not verified_critical_metadata_present(self)
        ):
            raise ValueError("verified proof cards require complete critical metadata")
        if self.derivation is not None:
            if self.derivation.truth_class is not TruthClass.DETERMINISTIC_DERIVATION:
                raise ValueError(
                    "distance derivation cannot conceal a non-derivation truth class"
                )
            if (
                self.derivation.crs != GEODESIC_CRS
                or self.derivation.units != DISTANCE_UNIT
                or self.derivation.algorithm != DISTANCE_ALGORITHM
            ):
                raise ValueError("unsupported CRS or units cannot be emitted as supported")
            policy_errors = derivation_policy_errors(
                claim_id=self.claim_id,
                claim_text=self.claim_text,
                freshness=self.freshness,
                derivation=self.derivation,
            )
            if policy_errors:
                raise ValueError(policy_errors[0])
        elif "km geodesic" in self.claim_text.casefold():
            raise ValueError("distance-bearing claims require derivation binding")
        return self


def make_proof_card(
    *,
    claim_id: str,
    claim_text: str,
    support_state: SupportState,
    support_label: str,
    authority: str,
    review_state: str,
    critical_fields_checked: str,
    freshness: str,
    exact_passage: str | None = None,
    source_title: str | None = None,
    source_revision: str | None = None,
    conflicts_or_unknowns: list[str] | None = None,
    official_url: HttpUrl | None = None,
    rejected: bool = False,
    derivation: DistanceDerivation | None = None,
    publication: PublicationAuthority,
) -> ProofCard:
    """Construct a proof card with deterministic Safety Profile metadata."""

    if rejected:
        support_state = "unknown"
        publication = _UNSUPPORTED_PUBLICATION
    truth_class, publication_state = bind_proof_profile(
        support_state, rejected=rejected, freshness=freshness
    )
    return ProofCard(
        claim_id=claim_id,
        claim_text=claim_text,
        support_state=support_state,
        support_label=support_label,
        authority=authority,
        exact_passage=exact_passage,
        source_title=source_title,
        source_revision=source_revision,
        review_state=review_state,
        critical_fields_checked=critical_fields_checked,
        freshness=freshness,
        conflicts_or_unknowns=list(conflicts_or_unknowns or []),
        official_url=official_url,
        truth_class=truth_class,
        publication_state=publication_state,
        derivation=derivation,
        publication=publication,
    )
