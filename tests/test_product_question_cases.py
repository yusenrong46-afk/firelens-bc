from __future__ import annotations

import hashlib
import json
import unittest
from collections import Counter
from pathlib import Path

from firelens.answering.location_intent import coarse_location_from_question
from firelens.evaluation.product_question_cases import (
    build_product_question_cases,
    build_product_question_regression_cases,
)


class ProductQuestionCatalogTests(unittest.TestCase):
    def test_catalog_is_large_unique_and_balanced(self) -> None:
        cases = build_product_question_cases()
        counts = Counter(case.bucket for case in cases)

        self.assertEqual(len(cases), 162)
        self.assertEqual(len({case.id for case in cases}), len(cases))
        self.assertGreaterEqual(counts["named_place_live"], 60)
        self.assertGreaterEqual(counts["implicit_personal_location"], 10)
        self.assertGreaterEqual(counts["everyday_chat"], 10)
        self.assertTrue(all(case.question.strip() for case in cases))

    def test_frozen_v1_artifact_is_not_rewritten_by_development_cases(self) -> None:
        path = Path(__file__).parents[1] / "data/evaluation/product_question_probe.v1.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        encoded = json.dumps(payload["cases"], sort_keys=True, separators=(",", ":")).encode()
        self.assertEqual(payload["dataset_version"], "product_question_probe.v1")
        self.assertEqual(payload["sha256"], hashlib.sha256(encoded).hexdigest())
        self.assertEqual(payload["case_count"], 162)
        self.assertEqual(
            [case.as_dict() for case in build_product_question_cases()], payload["cases"]
        )

    def test_named_places_and_near_me_have_distinct_location_expectations(self) -> None:
        cases = build_product_question_cases()
        named = [case for case in cases if case.bucket == "named_place_live"]
        near_me = [case for case in cases if case.bucket == "implicit_personal_location"]

        self.assertTrue(all(case.location_expectation == "inferred" for case in named))
        self.assertTrue(all(case.location_expectation == "required" for case in near_me))

    def test_v1_location_expectations_match_deterministic_extraction(self) -> None:
        for case in build_product_question_cases():
            location = coarse_location_from_question(case.question)
            with self.subTest(case_id=case.id, question=case.question):
                if case.location_expectation == "inferred":
                    self.assertIsNotNone(location)
                elif case.location_expectation == "none":
                    self.assertIsNone(location)

    def test_development_regressions_are_separate_and_structural(self) -> None:
        cases = build_product_question_regression_cases()
        self.assertGreaterEqual(len(cases), 10)
        self.assertEqual(len({case.id for case in cases}), len(cases))
        self.assertTrue(all(case.id.startswith("PQ-REG-") for case in cases))
        buckets = {case.bucket for case in cases}
        self.assertTrue(
            {
                "regression_my_place",
                "regression_named_evacuation",
                "regression_perimeter",
                "regression_telegraphic_live",
                "regression_mixed_handoff",
                "regression_place_correction",
                "regression_correction_source_context",
            }.issubset(buckets)
        )


if __name__ == "__main__":
    unittest.main()
