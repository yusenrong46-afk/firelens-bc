from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from rag_helpers import make_chunk

from firelens.document_context import (
    context_map_for_chunks,
    generate_document_context_sidecar,
)
from firelens.providers.fake import FakeProvider


class DocumentContextTests(unittest.IsolatedAsyncioTestCase):
    async def test_sidecar_is_versioned_and_does_not_mutate_raw_chunks(self) -> None:
        chunks = [make_chunk("chunk-a", "Raw exact citation passage about a household kit.")]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "contexts.jsonl"
            records = await generate_document_context_sidecar(
                chunks, provider=FakeProvider(), output_path=path
            )
            contexts = context_map_for_chunks(chunks, path)
        self.assertEqual(records[0].chunk_id, "chunk-a")
        self.assertEqual(records[0].document_sha256, chunks[0].document_sha256)
        self.assertIn("retrieval", contexts["chunk-a"])
        self.assertEqual(chunks[0].text, "Raw exact citation passage about a household kit.")
