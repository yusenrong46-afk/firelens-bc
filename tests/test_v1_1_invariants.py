from __future__ import annotations

import hashlib
import tempfile
import unittest
from collections.abc import Sequence
from pathlib import Path

from pydantic import ValidationError
from rag_helpers import make_chunk, make_runtime, write_test_corpus

from firelens.answering.intent import apply_planning_decision, plan_query
from firelens.answering.validate import validate_background_draft
from firelens.contracts import (
    BACKGROUND_LIMITATION,
    AskResponse,
    BackgroundDraft,
    BackgroundDraftClaim,
    ClaimSupport,
    EvidenceStatus,
    PlanningDecision,
    PublicClaim,
    QueryRelation,
    QueryRequest,
    QueryRoute,
    ResponseMode,
    ResponseStatus,
    RetrievalTextStrategy,
)
from firelens.providers.fake import FakeProvider
from firelens.publication.compiler import background_authority, explanation_authority
from firelens.retrieval.embeddings import build_vector_index
from firelens.retrieval.pipeline import RetrievalPipeline
from firelens.runtime import load_runtime


def _verified_claim() -> PublicClaim:
    return PublicClaim(
        claim_id="C1",
        text="Keep an emergency kit.",
        evidence_status=EvidenceStatus.VERIFIED_CORPUS,
        supports=[ClaimSupport(evidence_id="E1", quote="Keep an emergency kit.")],
        publication=explanation_authority(),
    )


class PublicContractInvariantTests(unittest.TestCase):
    def test_public_claim_support_shape_is_evidence_mode_specific(self) -> None:
        with self.assertRaises(ValidationError):
            PublicClaim(
                claim_id="C1",
                text="Unsupported verified claim.",
                evidence_status=EvidenceStatus.VERIFIED_CORPUS,
                publication=explanation_authority(),
            )
        with self.assertRaises(ValidationError):
            PublicClaim(
                claim_id="C1",
                text="Background claim with a citation.",
                evidence_status=EvidenceStatus.GENERAL_BACKGROUND,
                supports=[ClaimSupport(evidence_id="E1", quote="Citation leak.")],
                publication=background_authority(),
            )

    def test_response_states_cannot_carry_contradictory_evidence(self) -> None:
        invalid_payloads = (
            {
                "status": ResponseStatus.ABSTENTION,
                "trace_id": "trace-abstention",
                "response_mode": ResponseMode.ABSTENTION,
                "answer": "I cannot answer.",
                "claims": [_verified_claim()],
            },
            {
                "status": ResponseStatus.ERROR,
                "trace_id": "trace-error",
                "response_mode": ResponseMode.ABSTENTION,
                "claims": [_verified_claim()],
            },
            {
                "status": ResponseStatus.ANSWER,
                "trace_id": "trace-grounded",
                "response_mode": ResponseMode.GROUNDED,
                "answer": "Keep an emergency kit.",
                "claims": [_verified_claim()],
                # E1 is not present in the locally constructed public evidence list.
                "evidence": [],
            },
        )
        for payload in invalid_payloads:
            with self.subTest(payload=payload), self.assertRaises(ValidationError):
                AskResponse.model_validate(payload)


class PlannerInvariantTests(unittest.TestCase):
    def test_planning_schema_is_strict_bounded_and_deduplicated(self) -> None:
        schema = PlanningDecision.model_json_schema()
        self.assertFalse(schema["additionalProperties"])

        decision = PlanningDecision.model_validate(
            {
                "relation": "grounded_candidate",
                "retrieval_queries": [
                    "  Wildfire smoke basics  ",
                    "wildfire   smoke basics",
                    "emergency kit supplies",
                ],
                "explanation": "Two standalone retrieval needs.",
            }
        )
        self.assertEqual(
            decision.retrieval_queries,
            ["Wildfire smoke basics", "emergency kit supplies"],
        )

        invalid_payloads = (
            {
                "relation": "grounded_candidate",
                "retrieval_queries": [],
                "explanation": "Missing retrieval query.",
            },
            {
                "relation": "tangent",
                "retrieval_queries": ["must not retrieve"],
                "explanation": "Contradictory tangent plan.",
            },
            {
                "relation": "grounded_candidate",
                "retrieval_queries": ["one", "two", "three", "four"],
                "explanation": "Too many queries.",
            },
            {
                "relation": "grounded_candidate",
                "retrieval_queries": ["wildfire smoke"],
                "explanation": "Contains forbidden model output.",
                "answer": "A planner must not answer.",
            },
        )
        for payload in invalid_payloads:
            with self.subTest(payload=payload), self.assertRaises(ValidationError):
                PlanningDecision.model_validate(payload)

    def test_planner_decision_cannot_override_a_deterministic_safety_route(self) -> None:
        plan = plan_query(QueryRequest(question="Is a wildfire active near me right now?"))
        self.assertEqual(plan.route, QueryRoute.LIVE)
        attempted_override = PlanningDecision(
            relation=QueryRelation.GROUNDED_CANDIDATE,
            retrieval_queries=["stable wildfire guidance"],
            explanation="The model cannot authorize retrieval for a live question.",
        )
        self.assertEqual(apply_planning_decision(plan, attempted_override), plan)


class BackgroundValidationInvariantTests(unittest.TestCase):
    def test_background_schema_rejects_model_supplied_source_metadata(self) -> None:
        with self.assertRaises(ValidationError):
            BackgroundDraft.model_validate(
                {
                    "answer_type": "background",
                    "claims": [{"text": "General explanation."}],
                    "limitations": [BACKGROUND_LIMITATION],
                    "source_url": "https://example.test/model-supplied",
                }
            )

    def test_background_policy_rejects_current_personalized_and_source_claims(self) -> None:
        unsafe_claims = (
            "The wildfire is active near Kelowna today.",
            "Kelowna is under an evacuation order today.",
            "As of today, an evacuation order applies in Kelowna.",
            "The weather in Kelowna is rainy right now.",
            "Today's wind direction near Vernon is from the west.",
            "The AQHI in Kelowna is 7.",
            "Firefighting aircraft are operating near Penticton right now.",
            "The fire will reach Kelowna tomorrow.",
            "The wildfire will be contained tonight.",
            "I recommend that you evacuate now.",
            "If I were you, I would evacuate.",
            "For your family, leaving would be the safest choice.",
            "According to the BC Wildfire Service, embers can travel far.",
            "According to Health Canada, wildfire smoke can be harmful.",
            "Leave immediately.",
            "You should leave immediately.",
            "West Kelowna is safe right now.",
            "Kelowna is safe from the fire.",
            "The area is safe.",
            "Kelowna residents should leave.",
            "Residents should evacuate.",
            "People should stay in Kelowna.",
            "Families can safely return.",
            "Your family can safely stay.",
            "Drive Highway 1 to evacuate.",
            "Highway 1 is the best route out.",
            "It is okay to return home.",
            "You can safely return home.",
        )
        for text in unsafe_claims:
            draft = BackgroundDraft(
                answer_type="background",
                claims=[BackgroundDraftClaim(text=text)],
                limitations=[BACKGROUND_LIMITATION],
            )
            with self.subTest(text=text):
                self.assertFalse(validate_background_draft(draft).accepted)

    def test_background_policy_allows_an_explicit_non_authorization(self) -> None:
        for text in (
            "A rank label does not tell you whether you should evacuate.",
            "If you are under an evacuation alert, gather your prepared supplies.",
            "Evacuation order: leave immediately.",
            "Evacuation order = leave now.",
        ):
            with self.subTest(text=text):
                draft = BackgroundDraft(
                    answer_type="background",
                    claims=[BackgroundDraftClaim(text=text)],
                    limitations=[BACKGROUND_LIMITATION],
                )
                self.assertTrue(validate_background_draft(draft).accepted)


class ProviderBoundaryInvariantTests(unittest.IsolatedAsyncioTestCase):
    async def _assert_zero_call_boundary(
        self,
        *,
        question: str,
        expected_reason: str,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime, provider, _ = await make_runtime(Path(directory))
            before = (
                provider.plan_calls,
                provider.embed_calls,
                provider.rerank_calls,
                provider.generate_calls,
            )
            response = await runtime.service.ask(QueryRequest(question=question))
            after = (
                provider.plan_calls,
                provider.embed_calls,
                provider.rerank_calls,
                provider.generate_calls,
            )

        self.assertEqual(response.status, ResponseStatus.ABSTENTION)
        self.assertEqual(response.reason_code, expected_reason)
        self.assertEqual(after, before)

    async def test_implied_live_status_request_makes_zero_calls(self) -> None:
        for question in (
            "Is Kelowna under an evacuation order?",
            "Static preparedness documents can tell me whether an evacuation order is active, correct?",
        ):
            with self.subTest(question=question):
                await self._assert_zero_call_boundary(
                    question=question,
                    expected_reason="live_data_required",
                )

    async def test_personalized_symptom_request_makes_zero_calls(self) -> None:
        for question in (
            "My chest hurts after smoke exposure. What should I do?",
            "How should I treat my smoke-related headache?",
            "I was burned during a wildfire. How should I treat the burn?",
        ):
            with self.subTest(question=question):
                await self._assert_zero_call_boundary(
                    question=question,
                    expected_reason="personalized_medical_advice",
                )

    async def test_query_embedding_cache_is_bounded_hashed_and_normalized(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime, provider, config = await make_runtime(Path(directory))
            bounded_config = config.model_copy(update={"query_embedding_cache_size": 2})
            pipeline = RetrievalPipeline(
                runtime.chunks,
                vector_index=runtime.service.retrieval.vector_index,
                provider=provider,
                config=bounded_config,
            )

            raw_query = "  Sensitive Wildfire Query  "
            key = pipeline._query_cache_key(raw_query)
            normalized_key = pipeline._query_cache_key("sensitive   wildfire query")
            expected_hash = hashlib.sha256(b"sensitive wildfire query").hexdigest()
            self.assertEqual(key, normalized_key)
            self.assertTrue(key.endswith(expected_hash))
            self.assertNotIn("sensitive", key.lower())

            await pipeline._embed_queries([raw_query])
            await pipeline._embed_queries(["second query"])
            await pipeline._embed_queries(["third query"])
            self.assertEqual(len(pipeline._query_embedding_cache), 2)
            self.assertNotIn(key, pipeline._query_embedding_cache)


class CapturingRerankProvider(FakeProvider):
    def __init__(self) -> None:
        super().__init__()
        self.rerank_documents: list[str] = []

    async def rerank(
        self,
        query: str,
        documents: Sequence[str],
        *,
        top_n: int,
    ):
        self.rerank_documents = list(documents)
        return await super().rerank(query, documents, top_n=top_n)


class ContextualRetrievalInvariantTests(unittest.IsolatedAsyncioTestCase):
    async def test_contextual_retrieval_never_changes_public_citation_text(self) -> None:
        original_text = "Remove combustible debris from around the home."
        chunk = make_chunk(
            "contextual-a",
            original_text,
            authority="recognized_wildfire_preparedness_program",
        )
        provider = CapturingRerankProvider()

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = write_test_corpus(root, [chunk]).model_copy(
                update={"retrieval_text_strategy": RetrievalTextStrategy.METADATA_CONTEXT_V1}
            )
            await build_vector_index(
                [chunk],
                corpus_version="test-corpus.v1",
                config=config,
                provider=provider,
            )
            runtime = load_runtime(config, provider=provider)
            response = await runtime.service.ask(
                QueryRequest(
                    question="What FireSmart work removes combustible debris around a home?"
                )
            )

        self.assertEqual(response.response_mode, ResponseMode.GROUNDED)
        self.assertTrue(provider.rerank_documents)
        self.assertIn("Publisher: Government of British Columbia", provider.rerank_documents[0])
        self.assertIn(f"Passage: {original_text}", provider.rerank_documents[0])
        self.assertEqual(response.evidence[0].primary_text, original_text)
        self.assertEqual(response.evidence[0].context_text, original_text)
        self.assertEqual(response.claims[0].supports[0].quote, original_text)
        self.assertNotIn("Publisher:", response.claims[0].supports[0].quote)
