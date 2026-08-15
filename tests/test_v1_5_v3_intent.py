from __future__ import annotations

import unittest

from firelens.answering.intent import (
    coarse_location_from_question,
    live_layers_for_question,
    live_query_requires_location,
    plan_query,
    static_guidance_fragment,
    unsupported_live_topics,
)
from firelens.contracts import LiveResultKind, QueryRequest, QueryRoute


class V3DeterministicIntentTests(unittest.TestCase):
    def test_named_and_group_safety_decisions_are_prohibited(self) -> None:
        for question in (
            "Is West Kelowna safe right now?",
            "Is Kelowna safe from the fire?",
            "Can people safely stay in Kelowna?",
            "Can residents safely return to Kelowna?",
            "Should Kelowna residents leave?",
        ):
            with self.subTest(question=question):
                plan = plan_query(QueryRequest(question=question))
                self.assertEqual(plan.route, QueryRoute.PROHIBITED)
                self.assertEqual(
                    plan.boundary_reason.value if plan.boundary_reason else None,
                    "personalized_safety_decision",
                )

    def test_supported_live_clause_survives_an_unsupported_live_clause(self) -> None:
        self.assertEqual(
            live_layers_for_question("Show fires around Kelowna and the current air quality."),
            (LiveResultKind.INCIDENT, LiveResultKind.PERIMETER),
        )
        self.assertEqual(
            live_layers_for_question("What is the current air quality in Kelowna?"),
            (),
        )

    def test_my_or_our_place_is_personal_and_never_a_named_label(self) -> None:
        for question in (
            "Can you check fires by my place?",
            "Can you check fires by our place?",
            "Are there wildfires near my place?",
            "Show fires around our place.",
        ):
            with self.subTest(question=question):
                self.assertIsNone(coarse_location_from_question(question))
                self.assertTrue(live_query_requires_location(question))
                self.assertEqual(
                    plan_query(QueryRequest(question=question)).route,
                    QueryRoute.LIVE,
                )

    def test_named_evacuation_question_routes_live_with_evacuation_layer(self) -> None:
        question = "Are there evacuation orders near Penticton?"
        location = coarse_location_from_question(question)
        self.assertIsNotNone(location)
        assert location is not None
        self.assertEqual(location.label, "Penticton")
        self.assertEqual(plan_query(QueryRequest(question=question)).route, QueryRoute.LIVE)
        self.assertEqual(
            live_layers_for_question(question),
            (LiveResultKind.EVACUATION,),
        )

    def test_standalone_perimeter_question_selects_only_perimeter(self) -> None:
        self.assertEqual(
            live_layers_for_question("What is the current perimeter?"),
            (LiveResultKind.PERIMETER,),
        )
        self.assertEqual(
            live_layers_for_question("What is the current fire perimeter near Penticton?"),
            (LiveResultKind.PERIMETER,),
        )

    def test_colloquial_named_place_commands_route_to_live_layers(self) -> None:
        expected = {
            "Kelowna fire now?": (
                "Kelowna",
                (LiveResultKind.INCIDENT, LiveResultKind.PERIMETER),
            ),
            "kelowna fire": ("kelowna", (LiveResultKind.INCIDENT, LiveResultKind.PERIMETER)),
            "map nelson": ("nelson", (LiveResultKind.INCIDENT, LiveResultKind.PERIMETER)),
            "show me vernon fire stuff on map": (
                "vernon",
                (LiveResultKind.INCIDENT, LiveResultKind.PERIMETER),
            ),
            "WEST K any fires": (
                "West Kelowna",
                (LiveResultKind.INCIDENT, LiveResultKind.PERIMETER),
            ),
            "Show fires around Kelowna and the current air quality.": (
                "Kelowna",
                (LiveResultKind.INCIDENT, LiveResultKind.PERIMETER),
            ),
            "Show fires around Kelowna and give me a simple weekend packing list.": (
                "Kelowna",
                (LiveResultKind.INCIDENT, LiveResultKind.PERIMETER),
            ),
            "How far is this fire from Kelowna?": (
                "Kelowna",
                (LiveResultKind.INCIDENT, LiveResultKind.PERIMETER),
            ),
            "Distance from Kamloops to this fire?": (
                "Kamloops",
                (LiveResultKind.INCIDENT, LiveResultKind.PERIMETER),
            ),
            "perimeter near Kamloops now": (
                "Kamloops",
                (LiveResultKind.PERIMETER,),
            ),
            "How close is the wildfire perimeter near Vernon today?": (
                "Vernon",
                (LiveResultKind.PERIMETER,),
            ),
            "Show the current fire perimeter around Penticton.": (
                "Penticton",
                (LiveResultKind.PERIMETER,),
            ),
            "How close is the nearest perimeter to Kelowna?": (
                "Kelowna",
                (LiveResultKind.PERIMETER,),
            ),
            "How close is this fire to Kelowna?": (
                "Kelowna",
                (LiveResultKind.INCIDENT, LiveResultKind.PERIMETER),
            ),
        }
        for question, (label, layers) in expected.items():
            with self.subTest(question=question):
                location = coarse_location_from_question(question)
                self.assertIsNotNone(location)
                assert location is not None
                self.assertEqual(location.label, label)
                self.assertEqual(
                    plan_query(QueryRequest(question=question)).route, QueryRoute.LIVE
                )
                self.assertEqual(live_layers_for_question(question), layers)

    def test_selected_pronoun_distance_origins_are_extracted_without_a_new_prompt(
        self,
    ) -> None:
        for question in (
            "How far is it from Kelowna?",
            "What is the distance from Kelowna to it?",
        ):
            with self.subTest(question=question):
                location = coarse_location_from_question(question)
                self.assertIsNotNone(location)
                assert location is not None
                self.assertEqual(location.label, "Kelowna")

    def test_static_smoke_and_province_questions_do_not_invent_places(self) -> None:
        static_questions = (
            "How can I protect my family from wildfire smoke?",
            "What should I know about protecting children from wildfire smoke?",
            "Explain wildfire behavior in simple terms.",
            "Tell me about wildfire smoke in plain English.",
            "What is the difference between a wildfire alert and an order in simple terms?",
            "How do I prepare for wildfire smoke?",
            "What does an evacuation order mean for residents?",
        )
        for question in static_questions:
            with self.subTest(question=question):
                self.assertIsNone(coarse_location_from_question(question))
                self.assertEqual(
                    plan_query(QueryRequest(question=question)).route,
                    QueryRoute.RELATED,
                )

        for question in (
            "Give me the latest BC wildfire situation.",
            "Which fires are currently listed by BC Wildfire Service?",
            "I heard about the Kelowna fire.",
        ):
            with self.subTest(question=question):
                self.assertIsNone(coarse_location_from_question(question))

    def test_unsupported_handoffs_require_a_current_information_intent(self) -> None:
        explanatory = (
            "Explain what drives wildfire spread.",
            "What does AQHI mean?",
            "Explain the weather cycle.",
            "How do firefighting aircraft work?",
        )
        for question in explanatory:
            with self.subTest(question=question):
                self.assertEqual(unsupported_live_topics(question), ())
                self.assertEqual(
                    plan_query(QueryRequest(question=question)).route,
                    QueryRoute.RELATED,
                )

        current = {
            "What is the current air quality in Kelowna?": "air quality",
            "What's the weather in Kelowna right now?": "weather or smoke forecast",
            "What is the current weather in Kelowna?": "weather or smoke forecast",
            "Where are the firefighting aircraft right now?": "firefighting aircraft",
            "Are Highway 97 road closures active now?": "road conditions",
        }
        for question, topic in current.items():
            with self.subTest(question=question):
                self.assertEqual(unsupported_live_topics(question), (topic,))
                self.assertEqual(
                    plan_query(QueryRequest(question=question)).route,
                    QueryRoute.LIVE,
                )

    def test_explanatory_mixed_clauses_remain_available_to_the_static_tool(self) -> None:
        for question in (
            "Show fires around Kelowna and explain what drives wildfire spread.",
            "Show fires around Kelowna and explain what AQHI means.",
            "Show fires around Kelowna and explain the weather cycle.",
        ):
            with self.subTest(question=question):
                self.assertEqual(unsupported_live_topics(question), ())
                self.assertEqual(
                    live_layers_for_question(question),
                    (LiveResultKind.INCIDENT, LiveResultKind.PERIMETER),
                )
                location = coarse_location_from_question(question)
                self.assertIsNotNone(location)
                assert location is not None
                self.assertEqual(location.label, "Kelowna")

    def test_alert_order_definitions_are_static_even_beside_live_records(self) -> None:
        definition = "explain the difference between an evacuation alert and an order"
        self.assertEqual(live_layers_for_question(definition), ())
        self.assertEqual(static_guidance_fragment(definition), definition)

        mixed = "Show evacuation information for Williams Lake and explain alert versus order."
        self.assertEqual(
            live_layers_for_question(mixed),
            (LiveResultKind.EVACUATION,),
        )
        self.assertEqual(
            static_guidance_fragment(mixed),
            "explain alert versus order",
        )


if __name__ == "__main__":
    unittest.main()
