from __future__ import annotations

import unittest

from firelens.evaluation.product_question_cases import ProductQuestionCase
from firelens.evaluation.product_question_cli import _score


class ProductQuestionScoringTests(unittest.TestCase):
    def test_named_place_requires_resolved_map_focus_without_reprompt(self) -> None:
        case = ProductQuestionCase(
            id="PQ-TEST",
            bucket="named_place_live",
            question="Where are the fires in Kelowna?",
            expected_modes=("live", "capability"),
            location_expectation="inferred",
        )

        passed, issues = _score(
            case,
            status_code=200,
            response={
                "status": "answer",
                "response_mode": "requires_input",
                "answer": "Share an approximate location.",
                "required_input": {"kind": "location"},
            },
            selected_result_id=None,
        )

        self.assertFalse(passed)
        self.assertIn("redundant_location_request", issues)
        self.assertIn("missing_map_focus", issues)

    def test_named_place_passes_with_coarse_focus(self) -> None:
        case = ProductQuestionCase(
            id="PQ-TEST",
            bucket="named_place_live",
            question="Where are the fires in Kelowna?",
            expected_modes=("live", "capability"),
            location_expectation="inferred",
        )

        passed, issues = _score(
            case,
            status_code=200,
            response={
                "status": "answer",
                "response_mode": "live",
                "answer": "Current official information: Test Fire.",
                "resolved_location": {"latitude": 49.89, "longitude": -119.5},
            },
            selected_result_id=None,
        )

        self.assertTrue(passed)
        self.assertEqual(issues, [])


if __name__ == "__main__":
    unittest.main()
