from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from firelens.ingestion.html import ingest_html
from firelens.ingestion.pdf import IngestionError


SOURCE = {
    "source_id": "test_html",
    "title": "Test Guidance",
    "publisher": "Test Publisher",
    "canonical_url": "https://example.test/guidance",
    "temporal_class": "stable_guidance",
    "authority_class": "test_authority",
}


class HtmlIngestionUnitTests(unittest.TestCase):
    def test_headed_content_is_extracted_without_navigation(self) -> None:
        markup = b"""<html><body>
        <nav>Unwanted navigation</nav>
        <div class="topicContent__main">
          <h2>First stage</h2>
          <p>This is stable official guidance with enough text to retain as evidence.</p>
          <h3>Details</h3>
          <ul><li>Follow the directions issued by the responsible authority.</li></ul>
        </div></body></html>"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.html"
            path.write_bytes(markup)
            records = ingest_html(
                path,
                SOURCE,
                retrieved_at=datetime(2026, 7, 25, tzinfo=timezone.utc),
            )

        self.assertEqual(len(records), 2)
        self.assertEqual(records[0].heading_path[-1], "First stage")
        self.assertIn("stable official guidance", records[0].text)
        self.assertNotIn("Unwanted navigation", records[0].text)
        self.assertEqual(records[1].section_id, "details")

    def test_live_status_html_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "live.html"
            path.write_text(
                "<html><main><p>Current alert information that can change.</p></main></html>",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(IngestionError, "Live-status"):
                ingest_html(path, {**SOURCE, "temporal_class": "live_status"})


if __name__ == "__main__":
    unittest.main()
