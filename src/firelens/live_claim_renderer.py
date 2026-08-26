"""Single deterministic renderer for typed official live claims."""

from __future__ import annotations

from firelens.live_contracts import LiveResult


def render_typed_live_claim(result: LiveResult) -> str:
    name = result.name or result.incident_number or result.result_id
    freshness = (
        result.freshness.value if hasattr(result.freshness, "value") else result.freshness
    )
    parts = [
        f"{name} status is {result.status} according to {result.authority}.",
        f"Official source updated {result.source_updated_at.date().isoformat()}.",
        f"FireLens retrieved this record {result.retrieved_at.isoformat()}.",
        f"Freshness is {freshness}.",
    ]
    if result.distance_km is not None and result.distance_basis is not None:
        basis = result.distance_basis.replace("_", " ")
        parts.append(f"Distance {result.distance_km:g} km geodesic to the official {basis}.")
    parts.append("This is not a safety determination.")
    return " ".join(parts)
