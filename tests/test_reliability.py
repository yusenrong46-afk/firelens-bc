from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError
from rag_helpers import make_chunk

from firelens.contracts import QueryRequest
from firelens.errors import IndexValidationError
from firelens.retrieval.embeddings import load_embedding_cache
from firelens.retrieval.hybrid import reciprocal_rank_fusion
from firelens.retrieval.vector import retrieval_hit_from_chunk
from firelens.storage import atomic_text_writer, exclusive_file_lock
from firelens.traces import TraceRecorder


class ContractPropertyTests(unittest.TestCase):
    @given(st.text(min_size=1, max_size=2_000).filter(lambda value: bool(value.strip())))
    def test_question_normalization_is_nonblank(self, question: str) -> None:
        request = QueryRequest(question=question)
        self.assertTrue(request.question)
        self.assertEqual(request.question, " ".join(question.split()))

    def test_history_is_not_silently_accepted(self) -> None:
        with self.assertRaises(ValidationError):
            QueryRequest.model_validate(
                {
                    "question": "How do I prepare for wildfire?",
                    "history": [{"role": "user", "content": "Earlier question"}],
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
