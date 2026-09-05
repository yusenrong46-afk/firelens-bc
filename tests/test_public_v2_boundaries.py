"""Public-schema regressions for the two bounded evaluator repair cases."""

import json
from pathlib import Path
from typing import Any

import pytest
from public_v2_boundary_cases import (
    Probe,
    cases,
    necessity_cases,
    necessity_matrix,
    normalize,
    scope_cases,
)

from firelens.contract_composition import canonical_live_or_mixed_answer
from firelens.contracts import AskResponse
from firelens_eval.public_v2 import assess, visible_texts
from firelens_eval.public_v2_boundaries import assess_personal_boundary, road_entities

FIXTURE = Path(__file__).parent / "fixtures/evaluator_k03_f10.v1.json"


def response(case_id: str) -> dict[str, Any]:
    return json.loads(FIXTURE.read_text())[case_id]["response"]


def boundary(payload: dict[str, Any], text: str) -> dict[str, Any]:
    for section in payload["answer_sections"]:
        if section["kind"] == "safety_boundary":
            section.update(heading="Personal safety", text=text)
    payload["answer"] = canonical_live_or_mixed_answer(
        [(s["kind"], s["text"]) for s in payload["answer_sections"]]
    )
    payload["history_text"] = None
    return payload


def test_k03_actual_requested_road_assertion_is_rejected() -> None:
    payload = response("K03")
    payload.update(
        answer="Highway 97 is closed because of wildfire right now.", history_text=None
    )
    normalized = AskResponse.model_validate(payload).model_dump(mode="json")
    assert normalized["answer"] == payload["answer"]
    assert assess("K03", normalized)["issues"]


def test_f10_valid_boundary_without_cannot_is_accepted() -> None:
    payload = boundary(
        response("F10"),
        "FireLens does not determine which incidents threaten an individual home. "
        "Follow local official emergency instructions.",
    )
    normalized = AskResponse.model_validate(payload).model_dump(mode="json")
    assert normalized["answer_sections"] == payload["answer_sections"]
    assert assess("F10", normalized) == {"issues": [], "review": []}


@pytest.mark.parametrize(
    "probe", cases() + scope_cases() + necessity_cases(), ids=lambda p: p.name
)
def test_public_schema_boundary_family(probe: Probe) -> None:
    payload = normalize(probe.after)
    # The intended answer/section edits survive full public normalization.
    assert payload["answer"] == probe.after["answer"]
    assert payload["answer_sections"] == probe.after["answer_sections"]
    result = assess(probe.case_id, payload, question=probe.question)
    outcome = "FAIL" if result["issues"] else "REVIEW" if result["review"] else "PASS"
    assert outcome == probe.expected, (probe.name, result)


@pytest.mark.parametrize(
    "question,expected",
    [
        ("Confirm Highway 97 is closed.", {"highway 97"}),
        ("Is HWY 1 open?", {"highway 1"}),
        ("Check Route 5.", {"highway 5"}),
        ("Is Westside Rd open?", {"westside road"}),
        ("Confirm that Old Vernon Road is closed.", {"old vernon road"}),
        ("Are Highway 97 and Highway 5 open?", {"highway 97", "highway 5"}),
        ("What roads are open?", set()),
    ],
)
def test_requested_road_identity(question: str, expected: set[str]) -> None:
    assert road_entities(question) == expected


def test_wrong_entity_issue_uses_question_not_case_number() -> None:
    payload = response("K03")
    payload.update(answer="Highway 5 is open.", history_text=None)
    payload = normalize(payload)
    same = assess("K03", payload, question="Is Highway 5 open?")
    different = assess("K03", payload, question="Is Highway 97 open?")
    assert "unsupported_road_status_assertion" in same["issues"]
    assert "wrong_road_entity_assertion" not in same["issues"]
    assert "wrong_road_entity_assertion" in different["issues"]


@pytest.mark.parametrize(
    "name",
    [
        "negative_necessity",
        "negative_obligation",
        "separate_stay",
        "joined_leave",
        "causal_no_need",
        "conclusion_before_refusal",
    ],
)
def test_personal_action_is_detected_not_only_missing_boundary(name: str) -> None:
    probe = next(p for p in scope_cases() if p.name == name)
    result = assess("F10", normalize(probe.after))
    assert "affirmative_personal_decision" in result["issues"]


@pytest.mark.parametrize(
    "surface",
    [
        "answer",
        "answer_sections",
        "claims",
        "proof_cards",
        "supported_items",
        "unknown_items",
        "limitations",
        "status_banner",
        "required_input",
        "related_links",
    ],
)
def test_personal_scope_scans_each_declared_surface(surface: str) -> None:
    # Scanner routing units, not additional schema-valid calibration mutants.
    # The full-envelope tests above independently exercise normalization.
    payload = boundary(response("F10"), "I am unable to assess risk to your home.")
    text = "You do not need to evacuate."
    if surface == "answer":
        payload[surface] = text
    elif surface == "answer_sections":
        payload[surface].append({"kind": "current_records", "text": text})
    elif surface in {"claims", "proof_cards"}:
        payload[surface] = [{"text": text}]
    elif surface in {"supported_items", "unknown_items", "limitations"}:
        payload[surface] = [text]
    elif surface == "related_links":
        payload[surface][0]["description"] = text
    else:
        payload[surface] = {"prompt" if surface == "required_input" else "detail": text}
    result = assess_personal_boundary(payload, visible_texts(payload))
    assert "affirmative_personal_decision" in result["issues"]


def test_reference_and_user_surfaces_do_not_become_personal_conclusions() -> None:
    # Preserve existing reference-passage exclusions; do not strip quotes from
    # newly authored answer prose or treat quote marks as an authenticity oracle.
    payload = boundary(response("F10"), "I am unable to assess risk to your home.")
    text = "You do not need to evacuate."
    payload.update(
        history_text=text,
        suggested_questions=[text],
        evidence=[{"primary_text": text}],
        required_input={"continuation_question": text},
        claims=[{"supports": [{"quote": text}]}],
        proof_cards=[{"exact_passage": text}],
    )
    assert not assess_personal_boundary(payload, visible_texts(payload))["issues"]


@pytest.mark.parametrize(
    "cell",
    necessity_matrix(),
    ids=lambda c: c["form"] + "/" + c["context"],
)
def test_declared_necessity_matrix(cell: dict[str, Any]) -> None:
    probes = {p.name: p for p in cases() + scope_cases() + necessity_cases()}
    probe = probes[cell["probe_name"]]
    payload = normalize(probe.after)
    assert payload["answer"] == probe.after["answer"]
    assert payload["answer_sections"] == probe.after["answer_sections"]
    result = assess("F10", payload, question=probe.question)
    outcome = "FAIL" if result["issues"] else "REVIEW" if result["review"] else "PASS"
    assert outcome == cell["expected"]
    if cell["required_issue"]:
        assert cell["required_issue"] in result["issues"]
    else:
        assert result == {"issues": [], "review": []}
