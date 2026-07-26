from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from pypdf import PdfWriter

from firelens.ingestion.pdf import (
    IngestionError,
    ingest_pdf,
    load_source_record,
    sha256_file,
    write_jsonl,
)


SOURCE = {
    "source_id": "test_source",
    "title": "Test Source",
    "publisher": "Test Publisher",
    "canonical_url": "https://example.test/source.pdf",
    "temporal_class": "stable_guidance",
    "authority_class": "test_authority",
}


class PdfIngestionUnitTests(unittest.TestCase):
    def test_blank_pdf_produces_one_indexed_page_records(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pdf_path = Path(directory) / "blank.pdf"
            writer = PdfWriter()
            writer.add_blank_page(width=200, height=200)
            writer.add_blank_page(width=200, height=200)
            with pdf_path.open("wb") as stream:
                writer.write(stream)

            retrieved_at = datetime(2026, 7, 25, 12, tzinfo=timezone.utc)
            records = ingest_pdf(pdf_path, SOURCE, retrieved_at=retrieved_at)

            self.assertEqual([record.page_number for record in records], [1, 2])
            self.assertTrue(all(record.page_count == 2 for record in records))
            self.assertTrue(all(record.extraction_status == "empty" for record in records))
            self.assertEqual(records[0].record_id, "test_source:page:1")
            self.assertEqual(records[0].retrieved_at, retrieved_at.isoformat())
            self.assertEqual(records[0].document_sha256, sha256_file(pdf_path))

    def test_non_pdf_is_rejected_before_extraction(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "not-a-pdf.pdf"
            path.write_text("not a pdf", encoding="utf-8")

            with self.assertRaisesRegex(IngestionError, "PDF header"):
                ingest_pdf(path, SOURCE)

    def test_jsonl_contains_one_self_contained_record_per_line(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            pdf_path = Path(directory) / "blank.pdf"
            output_path = Path(directory) / "pages.jsonl"
            writer = PdfWriter()
            writer.add_blank_page(width=200, height=200)
            with pdf_path.open("wb") as stream:
                writer.write(stream)

            records = ingest_pdf(pdf_path, SOURCE)
            count = write_jsonl(records, output_path)
            payload = json.loads(output_path.read_text(encoding="utf-8").strip())

            self.assertEqual(count, 1)
            self.assertEqual(payload["source_id"], "test_source")
            self.assertEqual(payload["page_number"], 1)
            self.assertIn("document_sha256", payload)
            self.assertIn("canonical_url", payload)


class PdfIngestionIntegrationTests(unittest.TestCase):
    def test_preparedbc_pdf_preserves_visible_page_six(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        pdf_path = project_root / "data/raw/preparedbc_wildfire_guide.pdf"
        registry_path = project_root / "data/sources/source_registry.yaml"
        if not pdf_path.exists():
            self.skipTest("Approved PreparedBC PDF has not been downloaded.")

        source = load_source_record(registry_path, "preparedbc_wildfire_guide")
        records = ingest_pdf(pdf_path, source)

        self.assertEqual(len(records), 20)
        self.assertEqual(records[0].extraction_status, "suspect_text")
        self.assertIn("unmapped_font_glyphs", records[0].quality_flags)
        self.assertIn("Bottled water", records[5].text)
        self.assertIn("personal medications", records[5].text)
        self.assertEqual(records[5].page_number, 6)
        self.assertEqual(records[5].extraction_status, "text_extracted")


if __name__ == "__main__":
    unittest.main()
