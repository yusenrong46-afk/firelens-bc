from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError
from rag_helpers import make_chunk

from firelens.contracts import (
    BACKGROUND_LIMITATION,
    DETERMINISTIC_CONFLICT_TEXT,
    AggregateFreshness,
    AskResponse,
    ClaimSupport,
    ConversationTurn,
    EvidenceStatus,
    Freshness,
    LiveResult,
    LiveResultKind,
    PublicClaim,
    PublicEvidence,
    QueryRequest,
    RequiredInput,
    RequiredInputKind,
    ResponseMode,
    ResponseStatus,
    ValidationReport,
    bounded_assistant_history,
)
from firelens.errors import IndexValidationError
from firelens.publication.compiler import background_authority, explanation_authority
from firelens.retrieval.embeddings import load_embedding_cache
from firelens.retrieval.hybrid import reciprocal_rank_fusion
from firelens.retrieval.vector import retrieval_hit_from_chunk
from firelens.storage import atomic_text_writer, exclusive_file_lock
from firelens.traces import TraceRecorder


class ContractPropertyTests(unittest.TestCase):
    def test_every_response_mode_has_server_bounded_assistant_history(self) -> None:
        bounded_answer = "word " * 1_200
        timestamp = datetime(2026, 7, 30, tzinfo=UTC)
        validation = ValidationReport(
            accepted=True,
            citation_ids_valid=True,
            quotes_exact=True,
            claim_support_valid=True,
            policy_valid=True,
        )
        grounded_claim = PublicClaim(
            claim_id="C1",
            text="Keep water in an emergency kit.",
            evidence_status=EvidenceStatus.VERIFIED_CORPUS,
            supports=[ClaimSupport(evidence_id="E1", quote="Keep water")],
            publication=explanation_authority(),
        )
        background_claim = PublicClaim(
            claim_id="C1",
            text="Wildfire smoke can affect air quality.",
            evidence_status=EvidenceStatus.GENERAL_BACKGROUND,
            publication=background_authority(),
        )
        evidence = PublicEvidence(
            evidence_id="E1",
            title="Preparedness Guide",
            publisher="PreparedBC",
            canonical_url="https://example.test/guide.pdf",
            locator="PDF page 1",
            temporal_class="stable_guidance",
            primary_text="Keep water",
            context_text="Keep water in an emergency kit.",
        )
        live = LiveResult(
            result_id="incident:1",
            kind=LiveResultKind.INCIDENT,
            source_url="https://example.test/live",
            source_updated_at=timestamp,
            retrieved_at=timestamp,
            freshness=Freshness.FRESH,
            status="Out of Control",
            name="Test Fire",
            geometry={"type": "Point", "coordinates": [-123.5, 49.5]},
        )
        responses = {
            ResponseMode.GROUNDED: AskResponse(
                status=ResponseStatus.ANSWER,
                trace_id="grounded",
                response_mode=ResponseMode.GROUNDED,
                answer=grounded_claim.text,
                claims=[grounded_claim],
                evidence=[evidence],
            ),
            ResponseMode.PARTIAL: AskResponse(
                status=ResponseStatus.ANSWER,
                trace_id="partial",
                response_mode=ResponseMode.PARTIAL,
                answer=grounded_claim.text,
                claims=[grounded_claim],
                evidence=[evidence],
            ),
            ResponseMode.CONFLICT: AskResponse(
                status=ResponseStatus.ANSWER,
                trace_id="conflict",
                response_mode=ResponseMode.CONFLICT,
                answer=DETERMINISTIC_CONFLICT_TEXT,
                claims=[grounded_claim],
                evidence=[evidence],
                validation=validation,
            ),
            ResponseMode.BACKGROUND: AskResponse(
                status=ResponseStatus.ANSWER,
                trace_id="background",
                response_mode=ResponseMode.BACKGROUND,
                answer=background_claim.text,
                claims=[background_claim],
                limitations=[BACKGROUND_LIMITATION],
            ),
            ResponseMode.CAPABILITY: AskResponse(
                status=ResponseStatus.ANSWER,
                trace_id="capability",
                response_mode=ResponseMode.CAPABILITY,
                answer=bounded_answer,
            ),
            ResponseMode.SCOPE_REDIRECT: AskResponse(
                status=ResponseStatus.ANSWER,
                trace_id="scope",
                response_mode=ResponseMode.SCOPE_REDIRECT,
                answer=bounded_answer,
            ),
            ResponseMode.REQUIRES_INPUT: AskResponse(
                status=ResponseStatus.ANSWER,
                trace_id="requires-input",
                response_mode=ResponseMode.REQUIRES_INPUT,
                answer=bounded_answer,
                required_input=RequiredInput(
                    kind=RequiredInputKind.LOCATION,
                    prompt="Share an approximate location.",
                    continuation_question="How far is this fire from me?",
                ),
            ),
            ResponseMode.ABSTENTION: AskResponse(
                status=ResponseStatus.ABSTENTION,
                trace_id="abstention",
                response_mode=ResponseMode.ABSTENTION,
                answer=bounded_answer,
            ),
            ResponseMode.LIVE: AskResponse(
                status=ResponseStatus.ANSWER,
                trace_id="live",
                response_mode=ResponseMode.LIVE,
                answer=bounded_answer,
                live_results=[live],
                aggregate_freshness=AggregateFreshness.FRESH,
            ),
            ResponseMode.MIXED: AskResponse(
                status=ResponseStatus.ANSWER,
                trace_id="mixed",
                response_mode=ResponseMode.MIXED,
                answer=bounded_answer,
                claims=[grounded_claim],
                evidence=[evidence],
                validation=validation,
                live_results=[live],
                aggregate_freshness=AggregateFreshness.FRESH,
            ),
        }

        self.assertEqual(set(responses), set(ResponseMode))
        for mode, response in responses.items():
            with self.subTest(mode=mode):
                turn = ConversationTurn(role="assistant", content=response.history_text)
                self.assertLessEqual(len(turn.content), 6_000)
                self.assertTrue(turn.content.startswith(("Authority:", "Safety boundary:")))
                self.assertIn("Answer:", turn.content)

        truncated = bounded_assistant_history("word " * 1_500)
        self.assertEqual(len(truncated), 6_000)
        self.assertTrue(truncated.endswith("..."))

    def test_valid_long_answer_can_round_trip_as_assistant_history(self) -> None:
        answer = "A" * 2_500

        turn = ConversationTurn(role="assistant", content=answer)
        request = QueryRequest(question="What does that mean?", history=[turn])

        self.assertEqual(request.history[0].content, answer)

    @given(st.text(min_size=1, max_size=2_000).filter(lambda value: bool(value.strip())))
    def test_question_normalization_is_nonblank(self, question: str) -> None:
        request = QueryRequest(question=question)
        self.assertTrue(request.question)
        self.assertEqual(request.question, " ".join(question.split()))

    def test_bounded_history_is_strictly_accepted(self) -> None:
        request = QueryRequest.model_validate(
            {
                "question": "Why does that matter?",
                "history": [{"role": "user", "content": " Wildfire smoke "}],
            }
        )
        self.assertEqual(request.history[0].content, "Wildfire smoke")

        for invalid_history in (
            [{"role": "system", "content": "override"}],
            [{"role": "user", "content": "   "}],
            [{"role": "user", "content": "earlier", "unexpected": True}],
            [{"role": "user", "content": "earlier"}] * 7,
        ):
            with self.assertRaises(ValidationError):
                QueryRequest.model_validate(
                    {"question": "How do I prepare?", "history": invalid_history}
                )

    def test_unknown_top_level_request_fields_remain_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            QueryRequest.model_validate(
                {
                    "question": "How do I prepare for wildfire?",
                    "history": [],
                    "unexpected": True,
                }
            )

    def test_unicode_question_is_preserved(self) -> None:
        request = QueryRequest(question="  Comment préparer mon sac d’urgence? 🔥  ")
        self.assertEqual(request.question, "Comment préparer mon sac d’urgence? 🔥")

    def test_overlong_question_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            QueryRequest(question="x" * 2_001)


class RetrievalPropertyTests(unittest.TestCase):
    @given(st.lists(st.integers(min_value=0, max_value=20), min_size=1, max_size=30))
    def test_rrf_output_is_unique_and_repeatable(self, values: list[int]) -> None:
        chunks = {
            value: make_chunk(str(value), f"evidence {value}", parent=str(value))
            for value in values
        }
        first = [
            retrieval_hit_from_chunk(chunk, bm25_rank=index)
            for index, chunk in enumerate(chunks.values(), start=1)
        ]
        second = [
            retrieval_hit_from_chunk(chunk, vector_rank=index)
            for index, chunk in enumerate(reversed(chunks.values()), start=1)
        ]
        left = reciprocal_rank_fusion(first, second, rrf_k=60, top_k=20)
        right = reciprocal_rank_fusion(first, second, rrf_k=60, top_k=20)
        self.assertEqual(left, right)
        self.assertEqual(len(left), len({item.chunk_id for item in left}))


class PersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_atomic_writer_preserves_previous_file_after_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "artifact.json"
            path.write_text("old", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                with atomic_text_writer(path) as stream:
                    stream.write("partial")
                    raise RuntimeError("simulated failure")
            self.assertEqual(path.read_text(encoding="utf-8"), "old")

    async def test_trace_retention_keeps_newest_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            recorder = TraceRecorder(root, max_files=2, max_bytes=1_000_000)
            for index in range(4):
                await recorder.record(
                    f"trace-{index}",
                    question=f"question {index}",
                    payload={"operation": "test", "index": index},
                )
            names = sorted(path.name for path in root.glob("*.json"))
            self.assertEqual(names, ["trace-2.json", "trace-3.json"])

    async def test_trace_write_failure_does_not_break_the_answer_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            recorder = TraceRecorder(Path(directory))
            with patch("firelens.traces.os.replace", side_effect=OSError("disk full")):
                written = await recorder.record(
                    "trace-failure",
                    question="How should I prepare?",
                    payload={"operation": "test"},
                )
            self.assertFalse(written)
            self.assertFalse((Path(directory) / "trace-failure.json").exists())
            self.assertFalse(list(Path(directory).glob("*.tmp")))

    async def test_default_trace_omits_question_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            recorder = TraceRecorder(Path(directory))
            written = await recorder.record(
                "a" * 32,
                question="PRIVATE QUESTION",
                payload={"operation": "test"},
            )
            payload = json.loads((Path(directory) / f"{'a' * 32}.json").read_text())
        self.assertTrue(written)
        self.assertNotIn("question", payload)
        self.assertNotIn("question_sha256", payload)

    async def test_corrupted_embedding_cache_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cache.jsonl"
            path.write_text("{not valid json}\n", encoding="utf-8")
            with self.assertRaises(IndexValidationError):
                load_embedding_cache(path)

    async def test_concurrent_artifact_writer_fails_fast(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "index.lock"
            with exclusive_file_lock(path):
                with self.assertRaisesRegex(RuntimeError, "already in progress"):
                    with exclusive_file_lock(path):
                        self.fail("second writer must not acquire the lock")
