from __future__ import annotations

import unittest

from firelens.ingestion.pdf import IngestionError, PageRecord
from firelens.ingestion.repairs import apply_text_repairs


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

    def test_automated_visual_review_is_labeled_separately(self) -> None:
        repair = {
            "source_id": "source",
            "page_number": 5,
            "document_sha256": "correct-hash",
            "replacement_text": "Visually checked source text " * 5,
            "review_status": "automated_visual_reviewed",
        }
        repaired = apply_text_repairs([make_page()], [repair])[0]
        self.assertIn("automated_visual_reviewed_text_repair", repaired.quality_flags)
        self.assertNotIn("human_reviewed_text_repair", repaired.quality_flags)


if __name__ == "__main__":
    unittest.main()
