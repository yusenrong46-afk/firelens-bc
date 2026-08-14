from __future__ import annotations

import unittest
from collections import Counter

from firelens.evaluation.product_question_cases import build_product_question_cases


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

    def test_named_places_and_near_me_have_distinct_location_expectations(self) -> None:
        cases = build_product_question_cases()
        named = [case for case in cases if case.bucket == "named_place_live"]
        near_me = [case for case in cases if case.bucket == "implicit_personal_location"]

        self.assertTrue(all(case.location_expectation == "inferred" for case in named))
        self.assertTrue(all(case.location_expectation == "required" for case in near_me))


if __name__ == "__main__":
    unittest.main()
