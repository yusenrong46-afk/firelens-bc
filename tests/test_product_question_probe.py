from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from firelens.evaluation import product_question_cli
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


class ProductQuestionCliTests(unittest.TestCase):
    def test_regression_suite_does_not_rewrite_v1_and_failure_exits_nonzero(self) -> None:
        report = {
            "passed": 0,
            "failed": 1,
            "case_count": 1,
            "complete": True,
        }
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch.object(product_question_cli, "DEFAULT_OUT", Path(directory)),
                patch.object(product_question_cli, "dump_catalog") as dump_catalog,
                patch.object(
                    product_question_cli,
                    "run_probe",
                    new=AsyncMock(return_value=report),
                ) as run_probe,
            ):
                exit_code = product_question_cli.main(
                    [
                        "--suite",
                        "v3-regression",
                        "--limit",
                        "1",
                        "--label",
                        "test",
                    ]
                )

        self.assertEqual(exit_code, 2)
        dump_catalog.assert_not_called()
        self.assertEqual(
            run_probe.await_args.kwargs["dataset_version"],
            "product_question_regression.v3",
        )

    def test_filtered_regression_suite_cannot_claim_suite_completion(self) -> None:
        report = {
            "passed": 1,
            "failed": 0,
            "case_count": 1,
            "complete": True,
        }
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch.object(product_question_cli, "DEFAULT_OUT", Path(directory)),
                patch.object(product_question_cli, "dump_catalog") as dump_catalog,
                patch.object(
                    product_question_cli,
                    "run_probe",
                    new=AsyncMock(return_value=report),
                ),
            ):
                exit_code = product_question_cli.main(
                    ["--suite", "v3-regression", "--limit", "1", "--label", "test"]
                )

        self.assertEqual(exit_code, 2)
        dump_catalog.assert_not_called()

    def test_successful_complete_full_regression_suite_exits_zero(self) -> None:
        report = {
            "passed": 1,
            "failed": 0,
            "case_count": 1,
            "complete": True,
        }
        only_case = ProductQuestionCase(
            id="PQ-REG-ONLY",
            bucket="regression_named_evacuation",
            question="Is Kelowna under an evacuation order?",
            expected_modes=("live",),
            location_expectation="inferred",
        )
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch.object(product_question_cli, "DEFAULT_OUT", Path(directory)),
                patch.object(
                    product_question_cli,
                    "build_product_question_regression_cases",
                    return_value=[only_case],
                ),
                patch.object(
                    product_question_cli,
                    "run_probe",
                    new=AsyncMock(return_value=report),
                ) as run_probe,
            ):
                exit_code = product_question_cli.main(
                    ["--suite", "v3-regression", "--label", "test"]
                )

        self.assertEqual(exit_code, 0)
        self.assertEqual(run_probe.await_args.kwargs["catalog_cases"], [only_case])

    def test_probe_fails_closed_when_spend_cannot_be_verified(self) -> None:
        case = ProductQuestionCase(
            id="PQ-TEST",
            bucket="everyday_chat",
            question="Hello",
            expected_modes=("background",),
        )
        config = Mock(public_request_deadline_seconds=10)
        config.model_copy.return_value = config
        runtime = Mock()
        runtime.aclose = AsyncMock()
        live_service = Mock()
        live_service.aclose = AsyncMock()
        with (
            patch.object(product_question_cli.FireLensConfig, "from_env", return_value=config),
            patch.object(product_question_cli, "load_runtime", return_value=runtime),
            patch.object(product_question_cli, "LiveDataService", return_value=live_service),
            patch.object(product_question_cli, "create_app", return_value=Mock()),
            patch.object(
                product_question_cli,
                "_key_usage",
                new=AsyncMock(return_value=None),
            ),
        ):
            report = product_question_cli.asyncio.run(
                product_question_cli.run_probe([case], max_cost_usd=0.25)
            )

        self.assertFalse(report["complete"])
        self.assertFalse(report["spend_verified"])
        self.assertTrue(report["budget_verification_failed"])
        self.assertEqual(report["case_count"], 0)
        runtime.aclose.assert_awaited_once()
        live_service.aclose.assert_awaited_once()


class ProductQuestionStructuralScoringTests(unittest.TestCase):
    def test_safety_abstention_cannot_false_pass_an_ordinary_case(self) -> None:
        case = ProductQuestionCase(
            id="PQ-TEST-LUNCH",
            bucket="everyday_chat",
            question="Suggest a healthy lunch.",
            expected_modes=("background",),
        )
        passed, issues = _score(
            case,
            status_code=200,
            response={
                "status": "abstention",
                "response_mode": "abstention",
                "answer": "I cannot decide whether that is safe.",
                "reason_code": "personalized_safety_decision",
                "limitations": ["No personalized safety decision."],
            },
            selected_result_id=None,
        )

        self.assertFalse(passed)
        self.assertIn("non_answer_status", issues)
        self.assertIn("unexpected_mode:abstention", issues)

    def test_explicit_safety_boundary_is_valid_for_unsupported_live_handoff(self) -> None:
        case = ProductQuestionCase(
            id="PQ-TEST-SAFE-DRIVE",
            bucket="unsupported_live_source",
            question="Tell me whether it is safe to drive to Kelowna right now.",
            expected_modes=("scope_redirect",),
            location_expectation="inferred",
        )
        passed, issues = _score(
            case,
            status_code=200,
            response={
                "status": "abstention",
                "response_mode": "abstention",
                "answer": (
                    "FireLens cannot provide personalized safety advice. Open DriveBC "
                    "for current road conditions."
                ),
                "reason_code": "personalized_safety_decision",
                "limitations": ["FireLens cannot decide whether travel is safe."],
                "related_links": [{"title": "DriveBC road conditions"}],
                "resolved_location": {"latitude": 49.89, "longitude": -119.5},
            },
            selected_result_id=None,
        )

        self.assertTrue(passed)
        self.assertEqual(issues, [])

    def test_named_place_capability_is_not_a_live_answer(self) -> None:
        case = ProductQuestionCase(
            id="PQ-TEST-NAMED",
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
                "response_mode": "capability",
                "answer": "FireLens can show official wildfire records.",
                "resolved_location": {"latitude": 49.89, "longitude": -119.5},
            },
            selected_result_id=None,
        )
        self.assertFalse(passed)
        self.assertIn("capability_not_acceptable_for_named_place", issues)

    def test_mixed_case_requires_live_and_static_halves(self) -> None:
        case = ProductQuestionCase(
            id="PQ-TEST-MIXED",
            bucket="mixed_live_and_guidance",
            question="Are there fires near Kelowna, and what belongs in a kit?",
            expected_modes=("mixed", "live"),
            location_expectation="inferred",
        )
        live_only = {
            "status": "answer",
            "response_mode": "live",
            "answer": "Current official information: Test Fire.",
            "resolved_location": {"latitude": 49.89, "longitude": -119.5},
            "live_results": [{"kind": "incident"}],
        }
        passed, issues = _score(
            case, status_code=200, response=live_only, selected_result_id=None
        )
        self.assertFalse(passed)
        self.assertIn("mixed_mode_required", issues)
        self.assertIn("mixed_missing_static_half", issues)

        mixed = {
            **live_only,
            "response_mode": "mixed",
            "claims": [{"claim_id": "C1"}],
            "evidence": [{"evidence_id": "E1"}],
        }
        passed, issues = _score(case, status_code=200, response=mixed, selected_result_id=None)
        self.assertFalse(passed)
        self.assertIn("mixed_invalid_live_half", issues)
        self.assertIn("mixed_invalid_static_half", issues)

        linked_mixed = {
            "status": "answer",
            "response_mode": "mixed",
            "answer": "Current official information and reviewed kit guidance.",
            "resolved_location": {"latitude": 49.89, "longitude": -119.5},
            "live_results": [
                {
                    "result_id": "incident:1",
                    "kind": "incident",
                    "authority": "BC Wildfire Service",
                    "source_url": "https://example.test/incidents",
                    "source_updated_at": "2026-08-25T00:00:00Z",
                    "retrieved_at": "2026-08-25T00:01:00Z",
                    "freshness": "fresh",
                    "status": "active",
                }
            ],
            "claims": [
                {
                    "claim_id": "C1",
                    "text": "Keep water in an emergency kit.",
                    "evidence_status": "verified_corpus",
                    "supports": [{"evidence_id": "E1", "quote": "Keep water."}],
                }
            ],
            "evidence": [
                {
                    "evidence_id": "E1",
                    "title": "Preparedness Guide",
                    "publisher": "Government of British Columbia",
                    "canonical_url": "https://example.test/preparedness",
                    "primary_text": "Keep water.",
                }
            ],
        }
        passed, issues = _score(
            case, status_code=200, response=linked_mixed, selected_result_id=None
        )
        self.assertTrue(passed)
        self.assertEqual(issues, [])

        malformed_links = copy.deepcopy(linked_mixed)
        malformed_links["live_results"][0]["source_url"] = "not a link"
        malformed_links["live_results"][0]["source_updated_at"] = "not a timestamp"
        malformed_links["evidence"][0]["canonical_url"] = "not a link"
        passed, issues = _score(
            case, status_code=200, response=malformed_links, selected_result_id=None
        )
        self.assertFalse(passed)
        self.assertIn("mixed_invalid_live_half", issues)
        self.assertIn("mixed_invalid_static_half", issues)

    def test_named_evacuation_requires_evacuation_record(self) -> None:
        case = ProductQuestionCase(
            id="PQ-TEST-EVAC",
            bucket="named_place_evacuation",
            question="Is Kelowna under an evacuation order?",
            expected_modes=("live",),
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
                "live_results": [{"kind": "incident"}],
            },
            selected_result_id=None,
        )
        self.assertFalse(passed)
        self.assertIn("missing_evacuation_live_result", issues)

    def test_location_query_can_pass_when_official_layer_has_no_matching_record(self) -> None:
        case = ProductQuestionCase(
            id="PQ-TEST-NO-RESULT",
            bucket="regression_named_evacuation",
            question="Is Kelowna under an evacuation order?",
            expected_modes=("live",),
            location_expectation="inferred",
            required_capabilities=("resolved_location", "live_results"),
            required_live_kinds=("evacuation",),
            empty_live_results_allowed=True,
        )
        passed, issues = _score(
            case,
            status_code=200,
            response={
                "status": "answer",
                "response_mode": "live",
                "answer": (
                    "No matching official record was found. This does not mean the area "
                    "is safe."
                ),
                "resolved_location": {"latitude": 49.89, "longitude": -119.5},
                "live_results": [],
                "limitations": ["No matching record is not a safety determination."],
            },
            selected_result_id=None,
        )

        self.assertTrue(passed)

    def test_legacy_empty_evacuation_result_requires_visible_uncertainty(self) -> None:
        case = ProductQuestionCase(
            id="PQ-EVAC-01-A",
            bucket="named_place_evacuation",
            question="Is Kelowna under an evacuation order?",
            expected_modes=("live",),
            location_expectation="inferred",
            required_capabilities=("resolved_location", "live_results"),
            required_live_kinds=("evacuation",),
        )
        passed, issues = _score(
            case,
            status_code=200,
            response={
                "status": "answer",
                "response_mode": "live",
                "answer": "Everything is safe.",
                "resolved_location": {"latitude": 49.89, "longitude": -119.5},
                "live_results": [],
                "limitations": [],
            },
            selected_result_id=None,
        )

        self.assertFalse(passed)
        self.assertIn("missing_empty_result_uncertainty", issues)
        self.assertIn("unsafe_empty_result_language", issues)

    def test_selected_fixture_acquisition_failure_is_not_ignored(self) -> None:
        case = ProductQuestionCase(
            id="PQ-SELECTED-01",
            bucket="selected_result_followup",
            question="How large is this fire?",
            expected_modes=("live",),
            context_fixture="first_incident",
        )
        passed, issues = _score(
            case,
            status_code=200,
            response={
                "status": "answer",
                "response_mode": "live",
                "answer": "Current official information.",
            },
            selected_result_id=None,
        )

        self.assertFalse(passed)
        self.assertIn("selected_fixture_unavailable", issues)

    def test_empty_results_do_not_hide_a_wrong_nonempty_layer(self) -> None:
        case = ProductQuestionCase(
            id="PQ-TEST-WRONG-LAYER",
            bucket="regression_named_evacuation",
            question="Is Kelowna under an evacuation order?",
            expected_modes=("live",),
            location_expectation="inferred",
            required_capabilities=("resolved_location", "live_results"),
            required_live_kinds=("evacuation",),
            empty_live_results_allowed=True,
        )
        passed, issues = _score(
            case,
            status_code=200,
            response={
                "status": "answer",
                "response_mode": "live",
                "answer": "Current official information: Test Fire.",
                "resolved_location": {"latitude": 49.89, "longitude": -119.5},
                "live_results": [{"kind": "incident"}],
            },
            selected_result_id=None,
        )

        self.assertFalse(passed)
        self.assertIn("missing_live_result_kinds:evacuation", issues)

    def test_empty_results_reject_false_safety_and_require_visible_uncertainty(self) -> None:
        case = ProductQuestionCase(
            id="PQ-TEST-FALSE-SAFE",
            bucket="regression_named_evacuation",
            question="Is Kelowna under an evacuation order?",
            expected_modes=("live",),
            location_expectation="inferred",
            required_capabilities=("resolved_location", "live_results"),
            required_live_kinds=("evacuation",),
            empty_live_results_allowed=True,
        )
        passed, issues = _score(
            case,
            status_code=200,
            response={
                "status": "answer",
                "response_mode": "live",
                "answer": "Everything is safe.",
                "resolved_location": {"latitude": 49.89, "longitude": -119.5},
                "live_results": [],
                "limitations": [],
            },
            selected_result_id=None,
        )

        self.assertFalse(passed)
        self.assertIn("unsafe_empty_result_language", issues)
        self.assertIn("missing_empty_result_uncertainty", issues)

    def test_no_location_case_rejects_an_invented_map_focus(self) -> None:
        case = ProductQuestionCase(
            id="PQ-TEST-PROVINCE",
            bucket="province_live",
            question="Give me the latest BC wildfire situation.",
            expected_modes=("live",),
        )
        passed, issues = _score(
            case,
            status_code=200,
            response={
                "status": "answer",
                "response_mode": "live",
                "answer": "Current official information: Test Fire.",
                "resolved_location": {"latitude": 49.89, "longitude": -119.5},
                "live_results": [{"kind": "incident"}],
            },
            selected_result_id=None,
        )

        self.assertFalse(passed)
        self.assertIn("unexpected_map_focus", issues)

    def test_related_link_requirement_is_structural(self) -> None:
        case = ProductQuestionCase(
            id="PQ-TEST-LINK",
            bucket="regression_correction_source_context",
            question="What is the current air quality in Kelowna?",
            expected_modes=("scope_redirect",),
            location_expectation="inferred",
            required_capabilities=("resolved_location", "related_links"),
        )
        response = {
            "status": "answer",
            "response_mode": "scope_redirect",
            "answer": "Use the official air-quality service for the current value.",
            "resolved_location": {"latitude": 49.89, "longitude": -119.5},
        }
        passed, issues = _score(
            case, status_code=200, response=response, selected_result_id=None
        )
        self.assertFalse(passed)
        self.assertIn("missing_related_links", issues)

        response["related_links"] = [{"title": "AQHI"}]
        passed, issues = _score(
            case, status_code=200, response=response, selected_result_id=None
        )
        self.assertTrue(passed)
        self.assertEqual(issues, [])


if __name__ == "__main__":
    unittest.main()
