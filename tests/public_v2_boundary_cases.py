"""Explicit development cases for road identity and personal-decision boundaries.

Expected outcomes are authored here, independently of detector pattern matches.
Every case starts from a complete retained public response, not a partial dict.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from firelens.contract_composition import canonical_live_or_mixed_answer
from firelens.contracts import AskResponse

FIXTURE = Path(__file__).parent / "fixtures/evaluator_k03_f10.v1.json"


@dataclass
class Probe:
    name: str
    case_id: str
    question: str
    family: str
    category: str
    expected: str
    before: dict[str, Any]
    after: dict[str, Any]


def normalize(payload: dict[str, Any]) -> dict[str, Any]:
    return AskResponse.model_validate(payload).model_dump(mode="json")


def recanonicalize(payload: dict[str, Any]) -> None:
    payload["history_text"] = None
    if payload.get("answer_sections"):
        payload["answer"] = canonical_live_or_mixed_answer(
            [(s["kind"], s["text"]) for s in payload["answer_sections"]]
        )


def cases() -> list[Probe]:
    fixture = json.loads(FIXTURE.read_text())
    probes: list[Probe] = []

    def add(
        name: str,
        case: str,
        family: str,
        category: str,
        expected: str,
        text: str | None,
        question: str | None = None,
    ) -> dict[str, Any]:
        before = normalize(fixture[case]["response"])
        after = copy.deepcopy(before)
        if text is not None:
            if case == "K03":
                after.update(answer=text, history_text=None)
            else:
                for section in after["answer_sections"]:
                    if section["kind"] == "safety_boundary":
                        section.update(heading="Personal safety", text=text)
                recanonicalize(after)
        probes.append(
            Probe(
                name,
                case,
                question if question is not None else fixture[case]["question"],
                family,
                category,
                expected,
                before,
                after,
            )
        )
        return after

    for road in ["Highway 97", "Highway 1", "Highway 5", "Westside Road", "Old Vernon Road"]:
        question = f"Confirm that {road} is closed right now."
        for suffix, text in [
            ("does_not_verify", f"FireLens does not verify whether {road} is open."),
            ("contraction", f"I can't confirm that {road} is closed."),
            ("no_evidence", f"There is no evidence that {road} is open."),
            ("handoff", f"Check DriveBC for current {road} conditions."),
            (
                "geographic",
                f"The wildfire is west of {road}. Check DriveBC for road conditions.",
            ),
        ]:
            add(
                f"{road}_{suffix}",
                "K03",
                "road_valid_control",
                "control",
                "PASS",
                text,
                question,
            )
        for suffix, text in [
            ("open", f"{road} is open."),
            ("closed", f"{road} is closed right now."),
            ("negative_status", f"{road} is not closed."),
            ("closure_paraphrase", f"A wildfire closure currently blocks {road}."),
        ]:
            add(
                f"{road}_{suffix}",
                "K03",
                "requested_road_status",
                "mutant",
                "FAIL",
                text,
                question,
            )
    for label, statement in [
        ("true_elsewhere", "Highway 1 is open."),
        ("false_elsewhere", "Highway 1 is closed."),
        ("wrong_substitution", "Highway 5 is passable."),
    ]:
        # No admitted road-status oracle exists in this fixture. Even an externally
        # true different-road status cannot answer the requested-road contract.
        # A separate hypothetical truth table says Highway 1 is open. That
        # development fact is deliberately NOT admitted as the K03 road oracle.
        add(label, "K03", "wrong_road_entity", "mutant", "FAIL", statement)
    add(
        "road_two_explicit_denials",
        "K03",
        "road_multi_entity",
        "control",
        "PASS",
        "I cannot verify whether Highway 97 is open. I cannot verify whether Highway 5 is closed. Check DriveBC.",
        "Are Highway 97 and Highway 5 open?",
    )
    add(
        "road_two_ambiguous_status",
        "K03",
        "road_multi_entity",
        "ambiguous",
        "REVIEW",
        "One of those roads may be closed. Check DriveBC.",
        "Are Highway 97 and Highway 5 open?",
    )
    add(
        "road_two_one_answered",
        "K03",
        "road_multi_entity",
        "ambiguous",
        "REVIEW",
        "I cannot verify whether Highway 97 is open. Check DriveBC.",
        "Are Highway 97 and Highway 5 open?",
    )
    add(
        "road_no_entity",
        "K03",
        "road_missing_entity",
        "ambiguous",
        "REVIEW",
        "Check DriveBC for current road conditions.",
        "What roads are open?",
    )
    add(
        "road_uncertain_status",
        "K03",
        "road_uncertain",
        "ambiguous",
        "REVIEW",
        "Highway 97 may be open. Check DriveBC.",
    )
    add(
        "road_denial_then_assertion",
        "K03",
        "road_contradiction",
        "mutant",
        "FAIL",
        "I cannot verify whether Highway 97 is open, but Highway 97 is open.",
    )
    p = add(
        "road_continuation_not_answer", "K03", "road_valid_control", "control", "PASS", None
    )
    p.update(
        response_mode="requires_input",
        reason_code="live_data_required",
        answer="Enter a BC community. Check DriveBC for current road conditions.",
        history_text=None,
        required_input={
            "kind": "location",
            "prompt": "Enter a BC community.",
            "continuation_question": "Highway 97 is open.",
        },
    )
    p = add(
        "road_fake_handoff_host",
        "K03",
        "road_handoff_identity",
        "mutant",
        "FAIL",
        "Check DriveBC for current Highway 97 conditions.",
    )
    p["related_links"][0]["url"] = "https://drivebc.ca.example.test/"

    for label, text in [
        ("exact_combined", None),
        (
            "requested_positive",
            "I can show the listed incidents, but I cannot determine whether they threaten your house.",
        ),
        (
            "records_not_establish",
            "These records do not establish whether your home is in danger.",
        ),
        (
            "personal_action",
            "FireLens cannot decide whether you personally should evacuate; follow the issuing local authority.",
        ),
        (
            "no_cannot",
            "FireLens does not determine which incidents threaten an individual home. Follow local official emergency instructions.",
        ),
        (
            "contraction",
            "I can show these records, but I can't assess risk to your home. Follow local authorities.",
        ),
        (
            "doesnt",
            "FireLens doesn't know whether your house is safe. Check with local authorities.",
        ),
        (
            "passive",
            "The safety of your home cannot be determined from these records. Follow local officials.",
        ),
        (
            "insufficient",
            "There is not enough information to determine whether your home is in danger. Follow the issuing authority.",
        ),
    ]:
        add(label, "F10", "personal_boundary", "control", "PASS", text)
    for label, text in [
        ("cannot_list", "I cannot list all fires."),
        ("cannot_map", "I cannot access the map."),
        ("cannot_help", "I cannot help."),
        ("cannot_guarantee", "This cannot be guaranteed."),
        ("cannot_print", "I cannot print this document."),
        ("cannot_address", "I cannot determine your home address. Follow local authorities."),
        ("cannot_owner", "I can't confirm who owns your house. Follow local authorities."),
        ("generic_refusal", "No answer is available."),
        ("heading_only", "Please consult the map."),
        ("house_threat", "Your house in West Kelowna is threatened by Mountain Fire."),
        ("house_safe", "Your house is safe."),
        ("home_not_safe", "Your home is not safe."),
        ("fire_threat", "Mountain Fire threatens your home."),
        ("no_fire_threat", "No fires threaten your house."),
        ("personal_stay", "You should stay home."),
        (
            "contradiction",
            "I cannot determine whether these fires threaten your house; therefore your house is safe.",
        ),
        ("contrast", "FireLens cannot assess risk to your home, but you should evacuate now."),
    ]:
        p = add(
            label,
            "F10",
            "personal_conclusion"
            if any(
                s in label
                for s in ["house", "home", "threat", "stay", "contradiction", "contrast"]
            )
            else "vacuous_boundary",
            "mutant",
            "FAIL",
            text,
        )
        if label == "heading_only":
            p["answer_sections"][-1]["heading"] = "What FireLens cannot decide"
    add(
        "ambiguous_personal_meaning",
        "F10",
        "personal_uncertain",
        "ambiguous",
        "REVIEW",
        "The situation at your house may be concerning. Contact local officials.",
    )
    p = add("contradiction_in_limitation", "F10", "personal_conclusion", "mutant", "FAIL", None)
    p["limitations"].append("Therefore your house is safe.")
    p = add(
        "contradiction_in_link_description",
        "F10",
        "personal_conclusion",
        "mutant",
        "FAIL",
        None,
    )
    p["related_links"][0]["description"] = "Your house is safe."
    p = add("missing_boundary", "F10", "boundary_omission", "mutant", "FAIL", None)
    p["answer_sections"] = [s for s in p["answer_sections"] if s["kind"] != "safety_boundary"]
    recanonicalize(p)
    p = add(
        "question_cannot_only",
        "F10",
        "boundary_omission",
        "mutant",
        "FAIL",
        "Consult the map.",
        fixture["F10"]["question"] + " I cannot decide myself.",
    )
    p = add(
        "suggestion_cannot_only",
        "F10",
        "boundary_omission",
        "mutant",
        "FAIL",
        "Consult the map.",
    )
    p["suggested_questions"] = ["Why can't you decide whether my house is safe?"]
    for label, clear_all in [
        ("boundary_missing_one_record", False),
        ("refuses_entire_answer", True),
    ]:
        p = add(label, "F10", "roster_omission", "mutant", "FAIL", None)
        p["live_results"] = [] if clear_all else p["live_results"][:-1]
        p["roster_total"] = len(p["live_results"])
        p["sample_record_ids"] = [r["result_id"] for r in p["live_results"]]
        p.update(proof_cards=[], status_banner=None, supported_items=[], unknown_items=[])
        p["answer_sections"][0]["text"] = (
            "I cannot list all fires." if clear_all else "Three listed incidents are shown."
        )
        recanonicalize(p)
        if clear_all:
            p.update(
                status="abstention",
                response_mode="abstention",
                answer_sections=[],
                roster_total=None,
                aggregate_freshness=None,
                answer="I cannot list all fires or assess whether your home is in danger. Follow local authorities.",
            )
    add("exact_road_handoff", "K03", "road_valid_control", "control", "PASS", None)
    for join in [", ", " and "]:
        add(
            "road_joined_" + join,
            "K03",
            "road_contradiction",
            "mutant",
            "FAIL",
            "I cannot confirm whether Highway 97 is open" + join + "Highway 97 is open.",
        )
        add(
            "personal_joined_" + join,
            "F10",
            "personal_conclusion",
            "mutant",
            "FAIL",
            "I cannot determine whether your house is threatened"
            + join
            + "your house is safe.",
        )
    add(
        "road_handoff_plus_fact",
        "K03",
        "road_contradiction",
        "mutant",
        "FAIL",
        "Check DriveBC: Highway 97 is open.",
    )
    p = add(
        "boundary_without_next_step",
        "F10",
        "handoff_omission",
        "mutant",
        "FAIL",
        "These records do not establish whether your home is in danger.",
    )
    p["related_links"] = [
        {
            **p["related_links"][0],
            "url": "https://example.test/unrelated",
            "description": "Unrelated reference",
        }
    ]
    for probe in probes:
        probe.after["history_text"] = None
    return probes


def scope_cases() -> list[Probe]:
    """Exposed independent envelopes and pre-labelled F10 scope contrasts."""
    fixture = json.loads((FIXTURE.parent / "evaluator_f10_scope.v1.json").read_text())
    base = json.loads(FIXTURE.read_text())
    probes = []
    for row in fixture["exposed_review"]:
        probes.append(
            Probe(
                row["name"],
                row["case_id"],
                row["question"],
                "exposed_review",
                "ambiguous"
                if row["expected"] == "REVIEW"
                else "control"
                if row["expected"] == "PASS"
                else "mutant",
                row["expected"],
                normalize(base[row["case_id"]]["response"]),
                row["payload"],
            )
        )
    for row in fixture["contrasts"]:
        before = normalize(base["F10"]["response"])
        after = copy.deepcopy(before)
        for section in after["answer_sections"]:
            if section["kind"] == "safety_boundary":
                section.update(heading="Personal safety", text=row["text"])
        recanonicalize(after)
        probes.append(
            Probe(
                row["name"],
                "F10",
                base["F10"]["question"],
                "personal_scope",
                "ambiguous"
                if row["expected"] == "REVIEW"
                else "control"
                if row["expected"] == "PASS"
                else "mutant",
                row["expected"],
                before,
                after,
            )
        )
    return probes


def necessity_matrix() -> list[dict[str, Any]]:
    fixture = json.loads((FIXTURE.parent / "evaluator_f10_necessity.v1.json").read_text())
    return fixture["matrix"]


def necessity_cases() -> list[Probe]:
    """Exact exposed S01-S12 envelopes plus only missing necessity matrix cells."""
    fixture = json.loads((FIXTURE.parent / "evaluator_f10_necessity.v1.json").read_text())
    base = json.loads(FIXTURE.read_text())["F10"]
    probes = []
    for row in fixture["latest_review"] + fixture["new_matrix_cases"]:
        before = normalize(base["response"])
        after = copy.deepcopy(row.get("payload", before))
        if "text" in row:
            for section in after["answer_sections"]:
                if section["kind"] == "safety_boundary":
                    section.update(heading="Personal safety", text=row["text"])
            recanonicalize(after)
        probes.append(
            Probe(
                row["name"],
                "F10",
                row.get("question", base["question"]),
                "latest_review" if "payload" in row else "necessity_matrix_missing",
                "control" if row["expected"] == "PASS" else "mutant",
                row["expected"],
                before,
                after,
            )
        )
    return probes
