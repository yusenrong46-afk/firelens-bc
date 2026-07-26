# R1 Pre-Embedding Checkpoint

> Historical checkpoint. Current readiness, hashes, and release evidence are in
> `docs/releases/V1_EVIDENCE.md`.

Date: `2026-07-25`

## Outcome

The complete static-corpus path now works without an API key:

```text
source registry
  -> raw official PDF/HTML snapshots
  -> page or section records
  -> reviewed repair gate
  -> citation-preserving chunks
  -> combined corpus
  -> BM25 index
  -> gold-question evaluation
```

## Corpus

- Eight approved static sources are included.
- The current combined corpus contains 175 chunks.
- EmergencyInfoBC current status is excluded from the static corpus.
- The PreparedBC web page is excluded as a duplicate of the approved guide.
- Each PDF chunk cites a visible one-indexed page.
- Each HTML chunk cites a headed section rather than a fabricated page.

## Quality controls

- Every source snapshot is content-hashed.
- Live-status HTML fails closed at ingestion.
- Known-bad PDF extraction is excluded by default.
- PreparedBC page 5 has one human-reviewed, hash-pinned repair.
- The repair cannot silently apply to a changed PDF.
- Source and chunk IDs are deterministic.
- Duplicate chunk IDs stop the build.

## Verification

- 27 tests pass.
- BM25 Hit@5 is 15/17 (88.2%) over questions with static evidence.
- Mean static-source coverage at 5 is 82.4%.
- MRR@5 is 0.755.
- Three questions with no static evidence are skipped by design.

The two BM25 misses are retained as semantic-retrieval acceptance cases:

1. a broad request for practical FireSmart actions, where lexical ranking
   retrieves helpful related chunks but not the gold page in the first five;
2. an adversarial guarantee question, where BM25 cannot reliably understand
   negation and risk-versus-guarantee meaning.

## Next gate

The next stage requires an embedding API:

1. embed all 175 chunks;
2. embed each query;
3. compare vector retrieval with BM25 on the exact same gold questions;
4. fuse lexical and vector results;
5. introduce reranking only if measured evidence recall justifies it.

No LLM should generate customer-facing answers until retrieval and evidence
coverage gates pass.
