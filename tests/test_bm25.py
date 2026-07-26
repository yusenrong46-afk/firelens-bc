from __future__ import annotations

import unittest
from pathlib import Path

from firelens.ingestion.chunking import ChunkRecord
from firelens.retrieval.bm25 import BM25Index, load_chunk_records, tokenize


def make_chunk(chunk_id: str, text: str, *, page_number: int = 1) -> ChunkRecord:
    return ChunkRecord(
        schema_version="chunk_record.v1",
        chunk_id=chunk_id,
        parent_record_id=f"test_source:page:{page_number}",
        source_id="test_source",
        title="Test Source",
        publisher="Test Publisher",
        canonical_url="https://example.test/source.pdf",
        temporal_class="stable_guidance",
        authority_class="test_authority",
        document_sha256="abc123",
        page_number=page_number,
        chunk_index=1,
        section_title=None,
        text=text,
        char_count=len(text),
        retrieved_at="2026-07-25T12:00:00+00:00",
    )


class BM25UnitTests(unittest.TestCase):
    def test_tokenizer_normalizes_case_hyphens_and_apostrophes(self) -> None:
        self.assertEqual(
            tokenize("Grab-and-go: Don’t WAIT!"),
            ["grab", "and", "go", "don't", "wait"],
        )

    def test_exact_rare_terms_rank_first(self) -> None:
        expected = make_chunk(
            "source:page:1:chunk:1",
            "An evacuation order means leave immediately.",
        )
        other = make_chunk(
            "source:page:2:chunk:1",
            "Prepare food and water for your household.",
            page_number=2,
        )
        results = BM25Index([other, expected]).search("evacuation order", top_k=2)

        self.assertEqual(results[0].chunk_id, expected.chunk_id)
        self.assertGreater(results[0].score, 0)
        self.assertEqual(results[0].rank, 1)

    def test_empty_or_punctuation_query_returns_no_results(self) -> None:
        index = BM25Index([make_chunk("source:page:1:chunk:1", "Some guidance")])
        self.assertEqual(index.search("..."), [])

    def test_duplicate_chunk_ids_are_rejected(self) -> None:
        chunk = make_chunk("duplicate", "Some guidance")
        with self.assertRaisesRegex(ValueError, "unique"):
            BM25Index([chunk, chunk])

    def test_score_does_not_claim_answerability(self) -> None:
        chunk = make_chunk(
            "source:page:1:chunk:1",
            "Prepare your emergency wildfire plan.",
        )
        result = BM25Index([chunk]).search("current wildfire location")

        self.assertEqual(len(result), 1)
        self.assertNotIn("answerable", result[0].__dict__)


class BM25IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        project_root = Path(__file__).resolve().parents[1]
        chunks_path = (
            project_root
            / "data/processed/preparedbc_wildfire_guide.chunks.jsonl"
        )
        if not chunks_path.exists():
            raise unittest.SkipTest("PreparedBC chunks have not been generated.")
        cls.index = BM25Index(load_chunk_records(chunks_path))

    def assert_page_in_top_k(
        self,
        query: str,
        expected_page: int,
        *,
        top_k: int = 3,
    ) -> None:
        pages = [
            result.page_number
            for result in self.index.search(query, top_k=top_k)
        ]
        self.assertIn(expected_page, pages, msg=f"{query!r} returned pages {pages}")

    def test_evacuation_order_retrieval(self) -> None:
        results = self.index.search(
            "What does an evacuation order mean?",
            top_k=5,
        )
        self.assertEqual(results[0].page_number, 10)
        self.assertTrue(
            any(
                result.page_number == 11
                and result.section_title == "Evacuation Order"
                and "must leave IMMEDIATELY" in result.text
                for result in results
            )
        )

    def test_grab_and_go_bag_retrieval(self) -> None:
        results = self.index.search(
            "What belongs in a wildfire grab-and-go bag?",
            top_k=5,
        )
        self.assertEqual(results[0].page_number, 5)
        self.assertTrue(any(result.page_number == 6 for result in results))

    def test_pet_preparation_retrieval(self) -> None:
        results = self.index.search(
            "What should I prepare for my pets during an evacuation?",
            top_k=3,
        )
        self.assertEqual(results[0].page_number, 6)
        self.assertIn("Pets are part of the family", results[0].text)

    def test_annual_plan_review_retrieval(self) -> None:
        self.assert_page_in_top_k(
            "How often should I review my household emergency plan?",
            4,
        )

    def test_natural_gas_retrieval(self) -> None:
        self.assert_page_in_top_k(
            "Should I shut off natural gas during an evacuation order?",
            12,
        )


if __name__ == "__main__":
    unittest.main()
