from __future__ import annotations

from datetime import UTC, datetime
from random import Random

from pydantic import HttpUrl

from firelens.answering.input_clarity import (
    is_low_substance_question,
    missing_source_antecedent,
)
from firelens.answering.live_sample import display_order, official_display_label
from firelens.contracts import (
    Freshness,
    GeometryRelation,
    LiveResult,
    LiveResultKind,
    QueryRequest,
)
from firelens.guidance_capabilities import resolve_capability
from firelens.live_contracts import bind_distance_derivation


def _record(**updates: object) -> LiveResult:
    base = dict(
        result_id="incident:1",
        kind=LiveResultKind.INCIDENT,
        authority="BC Wildfire Service",
        source_url=HttpUrl("https://example.invalid/layer"),
        source_updated_at=datetime(2026, 9, 1, tzinfo=UTC),
        retrieved_at=datetime(2026, 9, 1, 1, tzinfo=UTC),
        freshness=Freshness.FRESH,
        status="Being Held",
        name=None,
        incident_number="N00001",
        size_hectares=0.01,
        geometry={"type": "Point", "coordinates": [-119.0, 49.0]},
        geometry_relation=GeometryRelation.UNKNOWN,
        fire_of_note=False,
    )
    base.update(updates)
    return LiveResult(**base)


def test_priority_sample_puts_fire_of_note_and_out_of_control_first() -> None:
    held = _record(result_id="incident:held", incident_number="N71932", size_hectares=0.009)
    ooc = _record(
        result_id="incident:ooc",
        status="Out of Control",
        name="Ridge Fire",
        incident_number="N10000",
        size_hectares=12.0,
    )
    note = _record(
        result_id="incident:note",
        status="Being Held",
        name="Pear Lake",
        incident_number="C40983",
        size_hectares=100.0,
        fire_of_note=True,
    )
    shuffled = [held, ooc, note]
    Random(7).shuffle(shuffled)
    ranked = display_order(shuffled)
    assert [item.result_id for item in ranked] == [
        "incident:note",
        "incident:ooc",
        "incident:held",
    ]
    assert official_display_label(held) == "Unnamed incident N71932"


def test_lookup_measured_from_a_place_lists_nearest_first_across_kinds() -> None:
    """The order a person reads is the order "the second one" counts through."""

    def located(result_id: str, km: float | None, **updates: object) -> LiveResult:
        record = _record(
            result_id=result_id, incident_number=result_id.split(":")[1], **updates
        )
        if km is None:
            return record
        derivation = bind_distance_derivation(
            result_id=result_id,
            distance_km=km,
            distance_basis="incident_point",
            calculated_at=record.retrieved_at,
            input_freshness=record.freshness,
        )
        return record.model_copy(
            update={
                "distance_km": km,
                "distance_basis": "incident_point",
                "distance_derivation": derivation,
            }
        )

    far_note = located("incident:K1", 45.0, fire_of_note=True, size_hectares=25_000.0)
    near_small = located("incident:K2", 12.0, size_hectares=0.5)
    unlocated = located("incident:K3", None, size_hectares=900.0)
    perimeter = _record(
        result_id="perimeter:K1",
        kind=LiveResultKind.PERIMETER,
        incident_number="K1",
        geometry={
            "type": "Polygon",
            "coordinates": [[[-119, 49], [-118, 49], [-118, 50], [-119, 49]]],
        },
    )
    shuffled = [unlocated, perimeter, far_note, near_small]
    Random(3).shuffle(shuffled)
    assert [item.result_id for item in display_order(shuffled)] == [
        "incident:K2",
        "incident:K1",
        "incident:K3",
        "perimeter:K1",
    ]


def test_ranking_is_deterministic_under_shuffle() -> None:
    records = [
        _record(
            result_id=f"incident:{index}", incident_number=f"N{index:05d}", size_hectares=index
        )
        for index in range(12)
    ]
    records[3] = records[3].model_copy(update={"fire_of_note": True, "name": "Note Fire"})
    records[8] = records[8].model_copy(update={"status": "Out of Control", "name": "OOC Fire"})
    first = [item.result_id for item in display_order(records)]
    for seed in range(5):
        copy = list(records)
        Random(seed).shuffle(copy)
        assert [item.result_id for item in display_order(copy)] == first


def test_evacuation_mistake_paraphrases_resolve_same_capability() -> None:
    questions = [
        "What mistakes should I avoid while evacuating?",
        "What are mistakes that I should avoid while evacuating?",
        "Which evacuation mistakes should I avoid?",
        "What should I not do during an evacuation?",
        "What common errors should evacuees avoid?",
        "What mistakes should I avoid during an evacuation?",
        "What are the mistakes I should avoid while evacuating?",
        "Which mistakes should I avoid when evacuating?",
        "What evacuation mistakes should I avoid?",
        "According to official guidance, what mistakes should I avoid during an evacuation?",
    ]
    resolved = [resolve_capability(question) for question in questions]
    assert all(item is not None for item in resolved)
    assert {item.id for item in resolved if item is not None} == {
        "evacuation_mistakes_to_avoid"
    }


def test_unclear_input_and_missing_source_antecedent() -> None:
    assert is_low_substance_question("asdf qwerty zxcv quantum foam")
    assert not is_low_substance_question("What is the refractive index of quantum foam?")
    assert not is_low_substance_question("What fires are near Kelowna?")
    request = QueryRequest(
        question="What does the official BC Wildfire Service say about this source?"
    )
    assert missing_source_antecedent(request)
