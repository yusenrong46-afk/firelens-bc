from __future__ import annotations

import json
import unittest
from dataclasses import replace
from pathlib import Path

from firelens.ingestion.chunking import (
    chunk_page_record,
    chunk_page_records,
    chunk_section_record,
    load_page_records,
)
from firelens.ingestion.html import SectionRecord
from firelens.ingestion.pdf import PageRecord


def make_page(
    text: str,
    *,
    page_number: int = 1,
    extraction_status: str = "text_extracted",
) -> PageRecord:
    return PageRecord(
        schema_version="page_record.v1",
        record_id=f"test_source:page:{page_number}",
        source_id="test_source",
        title="Test Source",
        publisher="Test Publisher",
        canonical_url="https://example.test/source.pdf",
        temporal_class="stable_guidance",
        authority_class="test_authority",
        document_sha256="abc123",
        page_number=page_number,
        page_count=2,
        text=text,
        char_count=len(text),
        extraction_status=extraction_status,
        quality_flags=(),
        retrieved_at="2026-07-25T12:00:00+00:00",
    )


class ChunkingUnitTests(unittest.TestCase):
    def test_suspect_page_is_excluded(self) -> None:
        page = make_page("(cid:31) broken", extraction_status="suspect_text")
        self.assertEqual(chunk_page_record(page), [])

    def test_chunks_inherit_exact_page_provenance(self) -> None:
        page = make_page(
            "PreparedBC\nWildfire Preparedness Guide\n"
            "EVACUATION ORDER\nLeave immediately.\n1"
        )
        chunks = chunk_page_record(page)

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].chunk_id, "test_source:page:1:chunk:1")
        self.assertEqual(chunks[0].parent_record_id, page.record_id)
        self.assertEqual(chunks[0].page_number, 1)
        self.assertEqual(chunks[0].document_sha256, page.document_sha256)
        self.assertNotIn("PreparedBC", chunks[0].text)
        self.assertFalse(chunks[0].text.endswith("\n1"))

    def test_split_occurs_between_logical_units(self) -> None:
        page = make_page(
            "FIRST SECTION\n"
            + "First complete instruction. " * 12
            + "\nSECOND SECTION\n"
            + "Second complete instruction. " * 12
        )
        chunks = chunk_page_record(page, max_chars=400)

        self.assertEqual(len(chunks), 2)
        self.assertTrue(chunks[0].text.startswith("FIRST SECTION"))
        self.assertTrue(chunks[1].text.startswith("SECOND SECTION"))

    def test_title_case_heading_starts_new_chunk(self) -> None:
        page = make_page(
            "Previous alert instruction with enough context to stand alone "
            "as a meaningful retrieval result for the user.\n"
            "Evacuation Order\n"
            "You must leave immediately and follow every direction issued "
            "by the responsible local authority."
        )
        chunks = chunk_page_record(page)

        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[1].section_title, "Evacuation Order")
        self.assertTrue(chunks[1].text.startswith("Evacuation Order"))

    def test_micro_heading_is_merged_with_following_guidance(self) -> None:
        page = make_page(
            "During a Wildfire\n"
            "FOLLOW INSTRUCTIONS\n"
            "Follow all evacuation directions from the responsible authority "
            "and keep monitoring official information."
        )
        chunks = chunk_page_record(page)

        self.assertEqual(len(chunks), 1)
        self.assertIn("During a Wildfire\nFOLLOW INSTRUCTIONS", chunks[0].text)

    def test_chunk_ids_restart_on_each_page(self) -> None:
        first = make_page("FIRST\nUseful guidance.", page_number=1)
        second = replace(
            make_page("SECOND\nOther guidance.", page_number=2),
            record_id="test_source:page:2",
        )
        chunks = chunk_page_records([first, second])
        self.assertEqual(
            [chunk.chunk_id for chunk in chunks],
            ["test_source:page:1:chunk:1", "test_source:page:2:chunk:1"],
        )

    def test_html_section_uses_section_locator_not_fake_page(self) -> None:
        text = "Stages of control\n" + ("Official stable definition. " * 45)
        section = SectionRecord(
            schema_version="section_record.v1",
            record_id="bcws:section:stages-of-control",
            source_id="bcws",
            title="Stages of control",
            publisher="BC Wildfire Service",
            canonical_url="https://example.test/stages",
            temporal_class="stable_guidance",
            authority_class="provincial_government",
            document_sha256="htmlhash",
            section_index=1,
            section_id="stages-of-control",
            heading_path=("Stages of control",),
            text=text,
            char_count=len(text),
            extraction_status="text_extracted",
            quality_flags=(),
            retrieved_at="2026-07-25T12:00:00+00:00",
        )
        chunks = chunk_section_record(section, max_chars=400)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(chunk.page_number is None for chunk in chunks))
        self.assertTrue(all(chunk.source_type == "html" for chunk in chunks))
        self.assertTrue(
            all(chunk.locator == "section:stages-of-control" for chunk in chunks)
        )


class ChunkingIntegrationTests(unittest.TestCase):
    def test_real_guide_keeps_critical_guidance_retrievable(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        pages_path = (
            project_root
            / "data/processed/preparedbc_wildfire_guide.pages.jsonl"
        )
        if not pages_path.exists():
            self.skipTest("PreparedBC page records have not been generated.")

        pages = load_page_records(pages_path)
        chunks = chunk_page_records(pages)

        indexed_pages = {chunk.page_number for chunk in chunks}
        self.assertEqual(indexed_pages.intersection({1, 19}), set())
        page_five = [chunk for chunk in chunks if chunk.page_number == 5]
        page_six = [chunk for chunk in chunks if chunk.page_number == 6]
        page_eleven = [chunk for chunk in chunks if chunk.page_number == 11]

        self.assertTrue(any("Food & water" in chunk.text for chunk in page_five))
        self.assertTrue(any("Bottled water" in chunk.text for chunk in page_six))
        self.assertTrue(
            any("must leave IMMEDIATELY" in chunk.text for chunk in page_eleven)
        )
        self.assertTrue(
            all(
                chunk.parent_record_id.endswith(f":page:{chunk.page_number}")
                for chunk in chunks
            )
        )


if __name__ == "__main__":
    unittest.main()
