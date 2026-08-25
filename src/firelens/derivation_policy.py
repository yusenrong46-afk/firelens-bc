"""Defense-in-depth checks for nested distance-derivation publication metadata."""

from __future__ import annotations

import math
import re
from typing import Any

from firelens.live_contracts import (
    DerivationValidationStatus,
    DistanceDerivation,
    canonical_validation_status,
    derivation_calculated_at_is_future,
    derivation_cites_record_and_place,
    derivation_publication_state,
    stored_input_freshness,
)
from firelens.safety_profile import PublicationState

_KM_GEODESIC = re.compile(r"(\d+(?:\.\d+)?)\s*km\s+geodesic", re.IGNORECASE)
_BASIS_LABELS = {
    "incident_point": "incident point",
    "perimeter_boundary": "perimeter boundary",
}


def as_distance_derivation(value: Any) -> DistanceDerivation:
    if isinstance(value, DistanceDerivation):
        return value
    if isinstance(value, dict):
        return DistanceDerivation.model_construct(**value)
    raise TypeError("distance derivation metadata is missing")


def distance_wording_errors(claim_text: str, derivation: DistanceDerivation) -> list[str]:
    """Require emitted km geodesic wording to match the bound measurement."""

    text = claim_text.casefold()
    if "km geodesic" not in text:
        return []
    quantities = [float(match) for match in _KM_GEODESIC.findall(claim_text)]
    if not quantities:
        return ["distance-bearing wording does not include a kilometre quantity"]
    errors: list[str] = []
    if not any(
        math.isclose(value, derivation.distance_km, rel_tol=0, abs_tol=0.05)
        for value in quantities
    ):
        errors.append("distance-bearing wording does not match the bound derivation")
    basis_label = _BASIS_LABELS[derivation.distance_basis]
    mentions_basis = "incident point" in text or "perimeter boundary" in text
    if mentions_basis and basis_label not in text:
        errors.append("distance-bearing wording does not match the derivation basis")
    return errors


def derivation_policy_errors(
    *,
    claim_id: str,
    claim_text: str,
    freshness: Any,
    derivation: Any,
) -> list[str]:
    """Nested derivation checks that still run on model_construct/model_copy cards."""

    bound = as_distance_derivation(derivation)
    errors: list[str] = []
    status = canonical_validation_status(bound.validation_status)
    publication = bound.publication_state
    if publication == PublicationState.VERIFIED and status != DerivationValidationStatus.VALID:
        errors.append(f"claim {claim_id} invalid derivation cannot be verified")
    if publication == PublicationState.VERIFIED and not derivation_cites_record_and_place(
        bound.input_source_ids
    ):
        errors.append(
            f"claim {claim_id} verified derivation requires record and location inputs"
        )
    if derivation_calculated_at_is_future(bound.calculated_at) and (
        status == DerivationValidationStatus.VALID or publication == PublicationState.VERIFIED
    ):
        errors.append(f"claim {claim_id} derivation calculated_at is materially in the future")
    expected = derivation_publication_state(
        validation_status=status,
        input_freshness=freshness,
        input_source_ids=bound.input_source_ids,
    )
    if publication != expected:
        errors.append(f"claim {claim_id} derivation publication does not match input freshness")
    stored = stored_input_freshness(bound.input_freshness)
    if stored != stored_input_freshness(freshness):
        errors.append(f"claim {claim_id} derivation input freshness does not match the card")
    for message in distance_wording_errors(claim_text, bound):
        errors.append(f"claim {claim_id} {message}")
    return errors
