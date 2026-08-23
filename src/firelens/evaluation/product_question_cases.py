"""Versioned exploratory questions representing ordinary FireLens product use."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

LocationExpectation = Literal["inferred", "required", "none"]
ContextFixture = Literal["none", "first_incident"]


Capability = Literal[
    "resolved_location",
    "required_input",
    "live_results",
    "claims",
    "evidence",
    "related_links",
]


@dataclass(frozen=True)
class ProductQuestionCase:
    id: str
    bucket: str
    question: str
    expected_modes: tuple[str, ...]
    location_expectation: LocationExpectation = "none"
    context_fixture: ContextFixture = "none"
    history: tuple[dict[str, str], ...] = ()
    notes: str = ""
    required_capabilities: tuple[Capability, ...] = ()
    required_live_kinds: tuple[str, ...] = ()
    empty_live_results_allowed: bool = False

    def as_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["expected_modes"] = list(self.expected_modes)
        payload["history"] = list(self.history)
        # Keep the frozen v1 catalog byte-compatible unless a development case
        # explicitly opts into a structural capability assertion.
        if self.required_capabilities:
            payload["required_capabilities"] = list(self.required_capabilities)
        else:
            payload.pop("required_capabilities", None)
        if self.required_live_kinds:
            payload["required_live_kinds"] = list(self.required_live_kinds)
        else:
            payload.pop("required_live_kinds", None)
        if not self.empty_live_results_allowed:
            payload.pop("empty_live_results_allowed", None)
        return payload


_COMMUNITIES = (
    "Kelowna",
    "West Kelowna",
    "Kamloops",
    "Vernon",
    "Penticton",
    "Salmon Arm",
    "Williams Lake",
    "Prince George",
    "Quesnel",
    "Cranbrook",
    "Nelson",
    "Revelstoke",
    "Whistler",
    "Terrace",
    "Fort St. John",
)

_NAMED_PLACE_TEMPLATES = (
    "Where are the current wildfires in {place}?",
    "Show me the wildfire situation around {place}.",
    "Is there a fire near {place} right now?",
    "Put the map on {place} and tell me what is happening.",
)

_NEAR_ME_QUESTIONS = (
    "Are there wildfires near me?",
    "Show fires close to my current location.",
    "Is anything burning around my home?",
    "Put the map where I am.",
    "How close is the nearest fire to me?",
    "Are there evacuation orders near my house?",
    "What wildfire is closest to my location?",
    "Check my area for active fires.",
    "Do I have an evacuation alert where I live?",
    "How far am I from the closest perimeter?",
)

_PROVINCE_LIVE_QUESTIONS = (
    "Where are the active wildfires in BC?",
    "Show the current BC wildfire map.",
    "How many active fire records are available across British Columbia?",
    "What evacuation alerts and orders are active in BC?",
    "Give me the latest BC wildfire situation.",
    "Which fires are currently listed by BC Wildfire Service?",
    "Show current incident and perimeter records for the province.",
    "What official wildfire information is available in BC right now?",
)

_SELECTED_RESULT_QUESTIONS = (
    "What is the current status of this fire?",
    "What is happening with the selected wildfire?",
    "Give me the official details for this incident.",
    "When was this fire record updated?",
    "How large is this fire?",
    "How far is this fire from me?",
    "What is the distance from my current location to this fire?",
    "How many kilometres away is the selected wildfire?",
)

_PREPAREDNESS_QUESTIONS = (
    "What belongs in a wildfire grab-and-go bag?",
    "What is the difference between an evacuation alert and an evacuation order?",
    "How can I reduce wildfire risk around my home?",
    "What should I know about wildfire smoke indoors?",
    "What do wildfire stages of control mean?",
    "How do structure-protection sprinklers work?",
    "What is the home ignition zone?",
    "How should my family prepare for a possible evacuation?",
    "What documents should I copy for an emergency kit?",
    "How should I prepare pets for evacuation?",
    "What should I do before leaving during an evacuation order?",
    "How often should I refresh emergency food, water, and batteries?",
)

_EVERYDAY_QUESTIONS = (
    "Help me make a simple weekend packing list.",
    "Explain the difference between weather and climate.",
    "Give me three ideas for a healthy lunch.",
    "How do I organize a household checklist?",
    "What is a good way to remember important documents?",
    "Explain air pressure in simple language.",
    "Can you help me plan a calm morning routine?",
    "What does probability mean in a weather forecast?",
    "How can I explain emergency planning to a child?",
    "What is the difference between smoke and fog?",
    "Help me write a short message to check on a neighbour.",
    "What are some ways to keep a phone charged during an outage?",
)

_FOLLOW_UPS = (
    (
        "What about pets?",
        (
            {"role": "user", "content": "What belongs in a wildfire emergency kit?"},
            {"role": "assistant", "content": "Include food, water, medicine, and documents."},
        ),
    ),
    (
        "Can you make that simpler?",
        (
            {"role": "user", "content": "Explain evacuation alerts and orders."},
            {"role": "assistant", "content": "An alert means prepare; an order means leave."},
        ),
    ),
    (
        "Which part should I do first?",
        (
            {"role": "user", "content": "How can I FireSmart my home?"},
            {
                "role": "assistant",
                "content": "Start by reducing combustible material near the home.",
            },
        ),
    ),
    (
        "What if I live in an apartment?",
        (
            {"role": "user", "content": "How should I prepare for a wildfire evacuation?"},
            {"role": "assistant", "content": "Make a plan and prepare a grab-and-go bag."},
        ),
    ),
    (
        "Can you turn that into a checklist?",
        (
            {"role": "user", "content": "How do I prepare for wildfire smoke?"},
            {
                "role": "assistant",
                "content": "Reduce indoor smoke and follow public-health advice.",
            },
        ),
    ),
    (
        "Why does that matter?",
        (
            {
                "role": "user",
                "content": "Keep the area closest to the house clear of combustibles.",
            },
            {"role": "assistant", "content": "That can reduce pathways for ignition."},
        ),
    ),
    (
        "What did you mean by that label?",
        (
            {"role": "user", "content": "What does being held mean?"},
            {"role": "assistant", "content": "Being held is a BC wildfire stage of control."},
        ),
    ),
    (
        "Give me a shorter version I can text someone.",
        (
            {"role": "user", "content": "What is an evacuation order?"},
            {
                "role": "assistant",
                "content": "It is an instruction from the issuing authority to leave.",
            },
        ),
    ),
)

_COLLOQUIAL_QUESTIONS = (
    "wheres the fire by kelowna rn",
    "any fires round kamloops today?",
    "show me vernon fire stuff on map",
    "is west k on evac alert",
    "whats a go bag actually need",
    "fire smart my place where do i start",
    "what does outta control fire mean",
    "smoke in my house what can i do",
    "evac alert vs order im confused",
    "how far is that fire from me tho",
)

_MIXED_QUESTIONS = (
    "Are there fires near Kelowna today, and what belongs in an emergency kit?",
    "Show fires around Kamloops and explain what being held means.",
    "Is Vernon under an evacuation alert, and how should I prepare my pets?",
    "What is happening near Penticton, and what should I pack?",
    "Show evacuation information for Williams Lake and explain alert versus order.",
    "Are there current fires around Nelson, and how can I reduce ember risk at home?",
    "Put the map on Prince George and give me a smoke-preparation checklist.",
    "What official records are near Cranbrook, and what should be in my family plan?",
)

_UNSUPPORTED_LIVE_QUESTIONS = (
    "What is the current air quality in Kelowna?",
    "What will the wind do near the Kelowna fires tonight?",
    "Is Highway 97 closed because of wildfire?",
    "Where are the firefighting aircraft right now?",
    "What is the current smoke forecast for Kamloops?",
    "Tell me whether it is safe to drive to Kelowna right now.",
)


def build_product_question_regression_cases() -> list[ProductQuestionCase]:
    """Return non-sealed V3 structural regressions for development replay.

    These cases deliberately live outside ``build_product_question_cases`` and the
    frozen v1 artifact.  Their checks cover typed response capabilities only; they
    do not establish semantic entailment or replace human review.
    """

    return [
        ProductQuestionCase(
            id="PQ-REG-MY-PLACE-01",
            bucket="regression_my_place",
            question="Are there fires near my place right now?",
            expected_modes=("requires_input",),
            location_expectation="required",
            required_capabilities=("required_input",),
        ),
        ProductQuestionCase(
            id="PQ-REG-MY-PLACE-02",
            bucket="regression_my_place",
            question="How close is the nearest perimeter to my home?",
            expected_modes=("requires_input",),
            location_expectation="required",
            required_capabilities=("required_input",),
        ),
        ProductQuestionCase(
            id="PQ-REG-NAMED-EVAC-01",
            bucket="regression_named_evacuation",
            question="Is Kelowna under an evacuation order right now?",
            expected_modes=("live",),
            location_expectation="inferred",
            required_capabilities=("resolved_location", "live_results"),
            required_live_kinds=("evacuation",),
            empty_live_results_allowed=True,
        ),
        ProductQuestionCase(
            id="PQ-REG-NAMED-EVAC-02",
            bucket="regression_named_evacuation",
            question="Show evacuation alerts around Kamloops today.",
            expected_modes=("live",),
            location_expectation="inferred",
            required_capabilities=("resolved_location", "live_results"),
            required_live_kinds=("evacuation",),
            empty_live_results_allowed=True,
        ),
        ProductQuestionCase(
            id="PQ-REG-PERIMETER-01",
            bucket="regression_perimeter",
            question="How close is the wildfire perimeter near Vernon today?",
            expected_modes=("live",),
            location_expectation="inferred",
            required_capabilities=("resolved_location", "live_results"),
            required_live_kinds=("perimeter",),
            empty_live_results_allowed=True,
        ),
        ProductQuestionCase(
            id="PQ-REG-PERIMETER-02",
            bucket="regression_perimeter",
            question="Show the current fire perimeter around Penticton.",
            expected_modes=("live",),
            location_expectation="inferred",
            required_capabilities=("resolved_location", "live_results"),
            required_live_kinds=("perimeter",),
            empty_live_results_allowed=True,
        ),
        ProductQuestionCase(
            id="PQ-REG-TELEGRAPHIC-01",
            bucket="regression_telegraphic_live",
            question="fires by Kelowna today",
            expected_modes=("live",),
            location_expectation="inferred",
            required_capabilities=("resolved_location", "live_results"),
            required_live_kinds=("incident",),
            empty_live_results_allowed=True,
        ),
        ProductQuestionCase(
            id="PQ-REG-TELEGRAPHIC-02",
            bucket="regression_telegraphic_live",
            question="perimeter near Kamloops now",
            expected_modes=("live",),
            location_expectation="inferred",
            required_capabilities=("resolved_location", "live_results"),
            required_live_kinds=("perimeter",),
            empty_live_results_allowed=True,
        ),
        ProductQuestionCase(
            id="PQ-REG-MIXED-01",
            bucket="regression_mixed_halves",
            question="Are there fires near Kelowna today, and what belongs in an emergency kit?",
            expected_modes=("mixed", "partial"),
            location_expectation="inferred",
            required_capabilities=("resolved_location", "live_results", "claims", "evidence"),
            required_live_kinds=("incident",),
            empty_live_results_allowed=True,
        ),
        ProductQuestionCase(
            id="PQ-REG-MIXED-HANDOFF-01",
            bucket="regression_mixed_handoff",
            question="Show fires around Kelowna and the current air quality.",
            expected_modes=("mixed", "scope_redirect"),
            location_expectation="inferred",
            required_capabilities=("resolved_location", "live_results", "related_links"),
            required_live_kinds=("incident",),
            empty_live_results_allowed=True,
        ),
        ProductQuestionCase(
            id="PQ-REG-PLACE-CORRECTION-01",
            bucket="regression_place_correction",
            question="I meant Vernon",
            expected_modes=("live",),
            location_expectation="inferred",
            history=(
                {"role": "user", "content": "Show fires around Kelowna."},
                {
                    "role": "assistant",
                    "content": "Current official information was shown for Kelowna.",
                },
            ),
            required_capabilities=("resolved_location", "live_results"),
            required_live_kinds=("incident",),
            empty_live_results_allowed=True,
        ),
        ProductQuestionCase(
            id="PQ-REG-PERSONAL-CORRECTION-01",
            bucket="regression_place_correction",
            question="I meant my place",
            expected_modes=("requires_input",),
            location_expectation="required",
            history=(
                {"role": "user", "content": "Show fires around Kelowna."},
                {
                    "role": "assistant",
                    "content": "Current official information was shown for Kelowna.",
                },
            ),
            required_capabilities=("required_input",),
        ),
        ProductQuestionCase(
            id="PQ-REG-CORRECTION-01",
            bucket="regression_correction_source_context",
            question="Correction: I meant wildfire smoke, not evacuation orders. What should I prepare?",
            expected_modes=("grounded", "partial"),
            history=(
                {"role": "user", "content": "What should I know about evacuation orders?"},
                {
                    "role": "assistant",
                    "content": "The source context was about evacuation orders.",
                },
            ),
            required_capabilities=("claims", "evidence"),
            notes="Structural claims/evidence presence does not prove semantic correction or source entailment.",
        ),
        ProductQuestionCase(
            id="PQ-REG-SOURCE-CONTEXT-01",
            bucket="regression_correction_source_context",
            question="According to the official guide, what belongs in a grab-and-go bag?",
            expected_modes=("grounded", "partial"),
            required_capabilities=("claims", "evidence"),
            notes="Exact citation identity is provenance evidence; human review remains required for meaning.",
        ),
        ProductQuestionCase(
            id="PQ-REG-RELATED-LINK-01",
            bucket="regression_correction_source_context",
            question="What is the current air quality in Kelowna?",
            expected_modes=("partial", "scope_redirect"),
            location_expectation="inferred",
            required_capabilities=("resolved_location", "related_links"),
            notes="A related official link is a scope handoff, not evidence that FireLens verified the value.",
        ),
    ]


def build_product_question_cases() -> list[ProductQuestionCase]:
    """Return the frozen exploratory catalog; this is not a sealed benchmark."""

    cases: list[ProductQuestionCase] = []
    for place_index, place in enumerate(_COMMUNITIES, start=1):
        for template_index, template in enumerate(_NAMED_PLACE_TEMPLATES, start=1):
            cases.append(
                ProductQuestionCase(
                    id=f"PQ-NAMED-{place_index:02d}-{template_index}",
                    bucket="named_place_live",
                    question=template.format(place=place),
                    expected_modes=("live", "capability"),
                    location_expectation="inferred",
                    notes="A named BC community should become coarse request-scoped map context.",
                )
            )
    for index, place in enumerate(_COMMUNITIES[:10], start=1):
        for suffix, question in (
            ("A", f"Is {place} under an evacuation order right now?"),
            ("B", f"Show evacuation alerts and orders around {place}."),
        ):
            cases.append(
                ProductQuestionCase(
                    id=f"PQ-EVAC-{index:02d}-{suffix}",
                    bucket="named_place_evacuation",
                    question=question,
                    expected_modes=("live", "capability"),
                    location_expectation="inferred",
                )
            )
    for index, question in enumerate(_NEAR_ME_QUESTIONS, start=1):
        cases.append(
            ProductQuestionCase(
                id=f"PQ-NEARME-{index:02d}",
                bucket="implicit_personal_location",
                question=question,
                expected_modes=("requires_input",),
                location_expectation="required",
            )
        )
    for index, question in enumerate(_PROVINCE_LIVE_QUESTIONS, start=1):
        cases.append(
            ProductQuestionCase(
                id=f"PQ-PROVINCE-{index:02d}",
                bucket="province_live",
                question=question,
                expected_modes=("live",),
            )
        )
    for index, question in enumerate(_SELECTED_RESULT_QUESTIONS, start=1):
        requires_location = index >= 6
        cases.append(
            ProductQuestionCase(
                id=f"PQ-SELECTED-{index:02d}",
                bucket="selected_map_followup",
                question=question,
                expected_modes=("requires_input",) if requires_location else ("live",),
                location_expectation="required" if requires_location else "none",
                context_fixture="first_incident",
            )
        )
    for index, question in enumerate(_PREPAREDNESS_QUESTIONS, start=1):
        cases.append(
            ProductQuestionCase(
                id=f"PQ-GUIDANCE-{index:02d}",
                bucket="reviewed_guidance",
                question=question,
                expected_modes=("grounded", "partial", "scope_redirect"),
            )
        )
    for index, question in enumerate(_EVERYDAY_QUESTIONS, start=1):
        cases.append(
            ProductQuestionCase(
                id=f"PQ-EVERYDAY-{index:02d}",
                bucket="everyday_chat",
                question=question,
                expected_modes=(
                    "background",
                    "capability",
                    "grounded",
                    "partial",
                    "scope_redirect",
                ),
            )
        )
    for index, (question, history) in enumerate(_FOLLOW_UPS, start=1):
        cases.append(
            ProductQuestionCase(
                id=f"PQ-FOLLOWUP-{index:02d}",
                bucket="conversation_followup",
                question=question,
                expected_modes=("grounded", "partial", "background", "scope_redirect"),
                history=history,
            )
        )
    for index, question in enumerate(_COLLOQUIAL_QUESTIONS, start=1):
        named_location = index <= 4
        selected_distance = index == 10
        cases.append(
            ProductQuestionCase(
                id=f"PQ-COLLOQUIAL-{index:02d}",
                bucket="colloquial_and_typos",
                question=question,
                expected_modes=(
                    ("requires_input",)
                    if selected_distance
                    else ("live", "capability")
                    if named_location
                    else ("grounded", "partial", "background", "scope_redirect")
                ),
                location_expectation=(
                    "required"
                    if selected_distance
                    else "inferred"
                    if named_location
                    else "none"
                ),
                context_fixture="first_incident" if selected_distance else "none",
            )
        )
    for index, question in enumerate(_MIXED_QUESTIONS, start=1):
        cases.append(
            ProductQuestionCase(
                id=f"PQ-MIXED-{index:02d}",
                bucket="mixed_live_and_guidance",
                question=question,
                expected_modes=("mixed", "partial", "live"),
                location_expectation="inferred",
            )
        )
    for index, question in enumerate(_UNSUPPORTED_LIVE_QUESTIONS, start=1):
        cases.append(
            ProductQuestionCase(
                id=f"PQ-LIVE-GAP-{index:02d}",
                bucket="unsupported_live_source",
                question=question,
                expected_modes=("partial", "background", "capability", "scope_redirect"),
                location_expectation="inferred"
                if "Kelowna" in question or "Kamloops" in question
                else "none",
                notes="Answer should explain the source boundary without a dead-end rejection.",
            )
        )
    return cases


def build_v1_6_user_end_cases() -> list[ProductQuestionCase]:
    """Load the separate 50-case end-user catalog without rewriting V1."""

    catalog_path = (
        Path(__file__).resolve().parents[3] / "data/evaluation/v1_6_user_end_questions_50.json"
    )
    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "firelens.v1_6_user_end_questions.v1":
        raise ValueError("unexpected V1.6 end-user question catalog schema")
    rows = payload.get("cases")
    if not isinstance(rows, list) or len(rows) != 50:
        raise ValueError("V1.6 end-user question catalog must contain 50 cases")

    location_map: dict[str, LocationExpectation] = {
        "none": "none",
        "coarse_in_question": "inferred",
        "required": "required",
        "selected_result": "none",
        "selected_or_required": "required",
        "history_correction": "inferred",
        "context_required": "required",
    }
    cases: list[ProductQuestionCase] = []
    for row in rows:
        family = str(row["family"])
        if family == "named_place_evacuation":
            bucket = "named_place_evacuation"
        elif family.startswith("mixed_"):
            bucket = "mixed_live_and_guidance"
        elif family.startswith("unsupported_"):
            bucket = "unsupported_live_source"
        else:
            bucket = family
        location_expectation = str(row["location_expectation"])
        if location_expectation not in location_map:
            raise ValueError(f"unsupported V1.6 location expectation: {location_expectation}")
        mapped_location = location_map[location_expectation]
        history = tuple(row.get("history", ()))
        live_kinds = tuple(row.get("live_result_kinds", ()))
        assertions = "; ".join(str(item) for item in row["assertions"])
        forbidden = ", ".join(str(item) for item in row["forbidden_behaviors"])
        required_capabilities: tuple[Capability, ...] = (
            ("resolved_location",)
            if mapped_location == "inferred"
            else ("required_input",)
            if mapped_location == "required"
            else ()
        )
        if live_kinds:
            required_capabilities += ("live_results",)
        cases.append(
            ProductQuestionCase(
                id=str(row["id"]),
                bucket=bucket,
                question=str(row["question"]),
                expected_modes=tuple(str(item) for item in row["expected_modes"]),
                location_expectation=mapped_location,
                context_fixture=(
                    "first_incident"
                    if row.get("context_fixture") == "first_incident_selected"
                    else "none"
                ),
                history=history,
                notes=f"Assertions: {assertions}. Forbidden: {forbidden}.",
                required_capabilities=required_capabilities,
                required_live_kinds=live_kinds,
                empty_live_results_allowed=bool(live_kinds),
            )
        )
    return cases
