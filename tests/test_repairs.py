from __future__ import annotations

import unittest
from types import SimpleNamespace

from firelens.ingestion.pdf import IngestionError, PageRecord
from firelens.ingestion.repairs import apply_text_repairs, validate_chunk_repair_provenance


def make_page() -> PageRecord:
    return PageRecord(
        schema_version="page_record.v1",
        record_id="source:page:5",
        source_id="source",
        title="Source",
        publisher="Publisher",
        canonical_url="https://example.test/source.pdf",
        temporal_class="stable_guidance",
        authority_class="authority",
        document_sha256="correct-hash",
        page_number=5,
        page_count=10,
        text="(cid:31) broken",
        char_count=15,
        extraction_status="suspect_text",
        quality_flags=("unmapped_font_glyphs",),
        retrieved_at="2026-07-25T12:00:00+00:00",
    )


class TextRepairTests(unittest.TestCase):
    def test_exact_hash_match_repairs_and_marks_page(self) -> None:
        repair = {
            "source_id": "source",
            "page_number": 5,
            "document_sha256": "correct-hash",
            "replacement_text": "Verified visible text " * 5,
            "review_status": "human_verified",
        }
        repaired = apply_text_repairs([make_page()], [repair])[0]
        self.assertEqual(repaired.extraction_status, "text_extracted")
        self.assertIn("human_reviewed_text_repair", repaired.quality_flags)
        self.assertEqual(repaired.char_count, len(repaired.text))

    def test_wrong_hash_cannot_silently_apply(self) -> None:
        repair = {
            "source_id": "source",
            "page_number": 5,
            "document_sha256": "wrong-hash",
            "replacement_text": "Verified visible text " * 5,
            "review_status": "human_verified",
        }
        with self.assertRaisesRegex(IngestionError, "did not match"):
            apply_text_repairs([make_page()], [repair])

    def test_automated_visual_review_is_not_approved_for_corpus_use(self) -> None:
        repair = {
            "source_id": "source",
            "page_number": 5,
            "document_sha256": "correct-hash",
            "replacement_text": "Visually checked source text " * 5,
            "review_status": "automated_visual_reviewed",
        }
        with self.assertRaisesRegex(IngestionError, "human_verified"):
            apply_text_repairs([make_page()], [repair])

    def test_pending_repair_chunk_is_rejected_by_runtime_provenance_gate(self) -> None:
        repair = {
            "source_id": "source",
            "page_number": 5,
            "document_sha256": "correct-hash",
            "replacement_text": "Visually checked source text " * 5,
            "review_status": "pending_owner_review",
        }
        chunk = SimpleNamespace(
            chunk_id="source:page:5:chunk:1",
            source_id="source",
            page_number=5,
            document_sha256="correct-hash",
            review_provenance="native_text",
        )

        with self.assertRaisesRegex(IngestionError, "pending human verification"):
            validate_chunk_repair_provenance([chunk], [repair])

    def test_human_repair_provenance_must_survive_chunking(self) -> None:
        repair = {
            "source_id": "source",
            "page_number": 5,
            "document_sha256": "correct-hash",
            "replacement_text": "Verified visible text " * 5,
            "review_status": "human_verified",
        }
        chunk = SimpleNamespace(
            chunk_id="source:page:5:chunk:1",
            source_id="source",
            page_number=5,
            document_sha256="correct-hash",
            review_provenance="native_text",
        )

        with self.assertRaisesRegex(IngestionError, "lost its human repair provenance"):
            validate_chunk_repair_provenance([chunk], [repair])


if __name__ == "__main__":
    unittest.main()
