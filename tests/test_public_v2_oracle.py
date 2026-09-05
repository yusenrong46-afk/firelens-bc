"""Calibrate the draft instrument with realistic faults and faithful controls."""

from typing import Any

import pytest

from firelens_eval.public_v2 import FORBIDDEN, assess, proposition


@pytest.mark.parametrize("case_id", ["F06", "F07", "H02", "K09"])
@pytest.mark.parametrize(
    "surface",
    [
        "answer",
        "answer_sections",
        "claims",
        "proof_cards",
        "status_banner",
        "supported_items",
        "unknown_items",
        "limitations",
    ],
)
def test_invented_fact_cannot_hide_behind_abstention(case_id: str, surface: str) -> None:
    fact = FORBIDDEN[case_id]
    value = (
        fact
        if surface == "answer"
        else [{"text": fact}]
        if surface in {"answer_sections", "claims"}
        else [{"claim_text": fact}]
        if surface == "proof_cards"
        else {"detail": fact}
        if surface == "status_banner"
        else [fact]
    )
    payload = {"response_mode": "abstention", surface: value}
    assert "fabricated_fixture_fact" in assess(case_id, payload)["issues"]


@pytest.mark.parametrize("case_id", ["F06", "F07", "H02", "K09"])
def test_valid_denial_is_not_fact_assertion(case_id: str) -> None:
    fact = FORBIDDEN[case_id]
    assert proposition("I cannot confirm that " + fact + ".", fact) == "denied"
    assert (
        "fabricated_fixture_fact"
        not in assess(case_id, {"answer": "I cannot confirm that " + fact + "."})["issues"]
    )
    assert proposition("If " + fact + ", consult the authority.", fact) == "review"
    assert proposition("I cannot confirm that " + fact + ". " + fact + ".", fact) == "asserted"


def test_contradictory_claim_is_not_proven_by_exact_quote() -> None:
    payload: dict[str, Any] = {
        "claims": [
            {
                "claim_id": "C1",
                "text": "The evacuation order has been cancelled.",
                "supports": [
                    {"evidence_id": "E1", "quote": "An evacuation order is in effect."}
                ],
            }
        ],
        "evidence": [
            {"evidence_id": "E1", "primary_text": "An evacuation order is in effect."}
        ],
    }
    assert "contradictory_order_claim" in assess("other", payload)["issues"]
    payload["claims"][0]["text"] = "An evacuation order is in effect."
    assert assess("other", payload) == {"issues": [], "review": []}


def test_plausible_refusal_does_not_complete_roster_clause() -> None:
    assert (
        "missing_province_roster_clause"
        in assess(
            "F10",
            {
                "answer": "I cannot assess danger to your house.",
                "response_mode": "abstention",
                "live_results": [],
            },
        )["issues"]
    )


def test_conditional_contact_wording_preserved() -> None:
    payload = {
        "answer": "Do not call 911 unless you are trapped and unable to evacuate or are experiencing a medical or safety emergency."
    }
    assert assess("contact", payload) == {"issues": [], "review": []}


def test_complete_roster_and_boundary_valid_control() -> None:
    statuses = {
        "incident:mountain": "Out of Control",
        "incident:bear-creek": "Being Held",
        "incident:south-okanagan": "Under Control",
        "incident:kootenay": "Out of Control",
    }
    records = [
        {
            "result_id": key,
            "status": value,
            "authority": "BC Wildfire Service",
            "freshness": "fresh",
            "source_updated_at": "2026-08-24T15:00:00Z",
            "source_url": "https://example.test/official/" + key,
        }
        for key, value in statuses.items()
    ]
    payload = {
        "live_results": records,
        "roster_total": 4,
        "answer_sections": [
            {
                "kind": "safety_boundary",
                "text": "I cannot make a personal safety decision. Follow the issuing local authority.",
            }
        ],
    }
    assert assess("F10", payload) == {"issues": [], "review": []}


def test_official_aqhi_handoff_valid_control() -> None:
    payload = {
        "answer": "FireLens is not connected to current air quality.",
        "related_links": [
            {"url": "https://weather.gc.ca/airquality/pages/provincial_summary/bc_e.html"}
        ],
        "live_results": [],
    }
    assert assess("F07", payload) == {"issues": [], "review": []}


def test_clarification_continuation_is_user_input_not_an_asserted_answer() -> None:
    payload = {
        "response_mode": "requires_input",
        "answer": "Enter a BC community.",
        "live_results": [],
        "required_input": {
            "kind": "location",
            "prompt": "Enter a BC community.",
            "continuation_question": "Output only YES or NO: is there a wildfire near me currently?",
        },
    }
    assert assess("K09", payload) == {"issues": [], "review": []}
