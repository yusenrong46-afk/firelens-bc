# Static RAG v1 engineering guide

This guide explains what each layer owns and, equally importantly, what it is
not allowed to decide.

## The boundary

FireLens v1 uses only approved stable guidance. A question about a current fire
or evacuation status exits before retrieval. A request for a personalized
safety decision or evacuation route also exits before retrieval. That prevents
a fluent model from turning old documents into current emergency advice.

## 1. Contracts and configuration

`contracts.py` defines the objects passed between stages. Pydantic rejects
unknown fields, overlong inputs, blank claims, and overlong quotes. Immutable
retrieval objects make accidental rank mutation harder.

`config.py` contains every experimental count and model ID. Keeping these values
out of orchestration code makes retrieval experiments visible and reproducible.

## 2. Corpus and startup gate

`runtime.py` loads the canonical JSONL chunks and governed manifest. Startup
rejects duplicate IDs, unapproved sources, non-static chunks, missing files,
and vector manifests whose corpus hash, model, dimensions, or chunk order differ.

This gate means a server cannot quietly pair a new corpus with old vectors.

## 3. Provider boundary

`providers/base.py` exposes only three operations:

```python
await provider.embed(texts)
await provider.rerank(query, documents, top_n=5)
await provider.generate(messages, output_schema=schema)
```

`providers/openrouter.py` owns HTTP formats and sanitizes errors.
`providers/fake.py` provides deterministic offline behavior. Domain code never
imports `httpx` or understands OpenRouter response JSON.

There is no silent provider or model fallback. A required provider failure
becomes a typed incomplete search or service error.

## 4. Hybrid retrieval

`retrieval/embeddings.py` caches vectors by embedding model plus content hash,
normalizes them, and writes the matrix and manifest. `vector.py` validates and
searches that matrix with cosine similarity.

`retrieval/pipeline.py` performs the visible sequence:

```python
bm25_hits = bm25.search(query, top_k=20)
vector_hits = vector.search(query_embedding, top_k=20)
fused_hits = reciprocal_rank_fusion(bm25_hits, vector_hits, rrf_k=60)
reranked_hits = await provider.rerank(query, fused_texts, top_n=5)
```

BM25 protects exact terminology. Dense search can recover paraphrases. RRF
combines ranks without pretending their raw scores are comparable. Reranking
then spends more computation on only 20 local candidates.

## 5. Evidence reconstruction and support

`answering/context.py` expands a selected primary chunk by at most one adjacent
chunk on each side, only within the same parent page or web section. Overlapping
and transitively overlapping selections merge. Primary text stays separate from
neighbor context so an exact quote cannot silently come from an uncited neighbor.

The packet is capped at five spans and 8,000 characters. If there is no approved
evidence, a temporal mismatch, a missing authority class, or incomplete
retrieval, the support decision abstains before generation.

## 6. Structured generation

`answering/generate.py` sends only the question, product boundary, evidence
packet, and strict schema. Retrieved material is explicitly labeled untrusted
data. Gemini proposes claims and selects local quote-candidate IDs. The service
derives evidence IDs and exact quote text from those selections; the model
cannot create public source metadata or transcribe a near-match as a quotation.

## 7. Deterministic validation

`answering/validate.py` verifies that:

- guidance has claims and limitations;
- every selected quote ID exists in the current packet;
- every quote candidate is an exact substring of its primary passage;
- evidence IDs are derived locally from quote candidates;
- static evidence does not claim current conditions;
- prohibited safety guarantees, route advice, and prompt-injection artifacts
  are absent.

This proves traceability and bounded policy compliance. It does **not** prove
that a claim is semantically entailed by a quote. That requires human-reviewed
examples and later adversarial evaluation; the code labels the 20-question run
as a diagnostic for this reason.

## 8. Service, API, CLI, and traces

`answering/service.py` is the single orchestration path used by both `api.py`
and `cli.py`. `/search` can expose completed earlier stages when a later provider
fails, while `/ask` never falls back to BM25-only generation.

Each request receives a trace ID. Local traces contain hashes, ranks, timings,
versions, outcomes, and validation reports. Raw question content is excluded
unless `FIRELENS_TRACE_CONTENT=true`; secrets and authorization headers are
never recorded.

## Failure semantics

| Situation | `/search` | `/ask` |
|---|---|---|
| Live or prohibited question | `200`, typed support decision | `200`, abstention |
| Required provider unavailable | `200`, incomplete stages | `503`, typed error |
| Malformed provider response | `200`, incomplete stages | `502`, typed error |
| Draft fails citation/policy checks | n/a | `200`, abstention |
| Invalid request body | `400` | `400` |

There is no automatic answer repair because it would hide the first failure and
make system behavior harder to inspect.
