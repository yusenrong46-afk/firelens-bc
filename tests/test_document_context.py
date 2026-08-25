from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from rag_helpers import make_chunk

from firelens.document_context import (
    PROMPT_VERSION,
    context_map_for_chunks,
    generate_document_context_sidecar,
    prompt_sha256,
)
from firelens.errors import IndexValidationError
from firelens.providers.fake import FakeProvider


class DocumentContextTests(unittest.IsolatedAsyncioTestCase):
    async def test_sidecar_is_versioned_and_does_not_mutate_raw_chunks(self) -> None:
        chunks = [make_chunk("chunk-a", "Raw exact citation passage about a household kit.")]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "contexts.jsonl"
            records = await generate_document_context_sidecar(
                chunks,
                provider=FakeProvider(),
                output_path=path,
                expected_model_id="fake/context-generator",
            )
            contexts = context_map_for_chunks(
                chunks,
                path,
                expected_model_id="fake/context-generator",
            )
        self.assertEqual(records[0].chunk_id, "chunk-a")
        self.assertEqual(records[0].document_sha256, chunks[0].document_sha256)
        self.assertIn("retrieval", contexts["chunk-a"])
        self.assertEqual(chunks[0].text, "Raw exact citation passage about a household kit.")

    def test_loader_rejects_stale_schema_prompt_and_model_identity(self) -> None:
        chunk = make_chunk("chunk-a", "Raw exact citation passage about a household kit.")
        baseline = {
            "schema_version": PROMPT_VERSION,
            "document_sha256": chunk.document_sha256,
            "chunk_id": chunk.chunk_id,
            "model_id": "openai/gpt-5.6-luna",
            "prompt_sha256": prompt_sha256(),
            "context": "Current synthetic retrieval context.",
        }
        stale_values = {
            "schema_version": "retired_context_schema.v1",
            "prompt_sha256": "0" * 64,
            "model_id": "retired/context-model",
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "contexts.jsonl"
            for field, value in stale_values.items():
                with self.subTest(field=field):
                    payload = {**baseline, field: value}
                    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
                    with self.assertRaisesRegex(IndexValidationError, field.split("_")[0]):
                        context_map_for_chunks([chunk], path)
            missing_schema = dict(baseline)
            missing_schema.pop("schema_version")
            path.write_text(json.dumps(missing_schema) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(IndexValidationError, "schema"):
                context_map_for_chunks([chunk], path)
