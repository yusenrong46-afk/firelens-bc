from __future__ import annotations

import unittest

from firelens.ingestion.chunking import ChunkRecord
from firelens.retrieval.bm25 import BM25Index
from firelens.retrieval.evaluate import evaluate_retrieval


def make_chunk(source_id: str, page: int, text: str) -> ChunkRecord:
    return ChunkRecord(
        schema_version="chunk_record.v2",
        chunk_id=f"{source_id}:page:{page}:chunk:1",
        parent_record_id=f"{source_id}:page:{page}",
        source_id=source_id,
        title="Source",
        publisher="Publisher",
        canonical_url="https://example.test",
        temporal_class="stable_guidance",
        authority_class="authority",
        document_sha256="hash",
        page_number=page,
        chunk_index=1,
        section_title=None,
        text=text,
        char_count=len(text),
        retrieved_at="2026-07-25T12:00:00+00:00",
        locator=f"page:{page}",
    )


class RetrievalEvaluationTests(unittest.TestCase):
    def test_live_evidence_is_ignored_but_static_evidence_is_scored(self) -> None:
        index = BM25Index([make_chunk("static", 2, "Evacuation alert means prepare to leave.")])
        question = {
            "id": "GQ",
            "question": "What does evacuation alert mean?",
            "answerability": "multi_source",
            "requires_live_verification": True,
            "evidence": [
                {"source_id": "static", "pdf_pages": [2]},
                {"source_id": "live", "pdf_pages": []},
            ],
        }
        report = evaluate_retrieval(index, [question], corpus_source_ids={"static"}, top_k=3)
        row = report["questions"][0]
        self.assertTrue(row["hit_at_k"])
        self.assertEqual(row["expected_static_sources"], ["static"])
        self.assertEqual(row["source_coverage"], 1.0)


if __name__ == "__main__":
    unittest.main()
