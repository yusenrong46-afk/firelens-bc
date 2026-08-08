# Technical glossary

Use this as a teaching aid, not as proof that a term is implemented. Each entry names the current FireLens location to inspect.

## Evidence-bound RAG

- **Plain English:** retrieve reviewed passages, then answer only within what those passages support.
- **General meaning:** retrieval-augmented generation with an explicit evidence/acceptance boundary.
- **This repository:** `answering/context.py`, `answering/grounded.py`, `answering/validate.py`.

## Chunk

- **Plain English:** a bounded piece of an ingested document used for retrieval.
- **General meaning:** a passage or node in a retrieval index.
- **This repository:** `ingestion/chunking.py:25-48` defines `ChunkRecord`; processed chunks are in `data/processed/`.

## BM25

- **Plain English:** a lexical search score that rewards query terms appearing in useful documents and discounts common terms.
- **General meaning:** a probabilistic term-frequency/inverse-document-frequency ranking function.
- **This repository:** `retrieval/bm25.py`; used by `retrieval/pipeline.py:135-166` and planning preflight.

## Embedding / vector search

- **Plain English:** represent text as numbers and find passages with nearby vectors.
- **General meaning:** dense semantic retrieval using an embedding model and similarity metric.
- **This repository:** `retrieval/embeddings.py`, `retrieval/vector.py`, and `pipeline.py:170-227`; OpenRouter configuration is in `config.py`.

## Reciprocal Rank Fusion (RRF)

- **Plain English:** combine several ranked lists so an item appearing high in multiple lists rises.
- **General meaning:** commonly `score(d) = Σ 1 / (k + rank_i(d))` across rankings.
- **This repository:** `retrieval/hybrid.py`; the retained `rrf_k` is configured in `config.py` and recorded by benchmarks.

## Reranking

- **Plain English:** ask a second model to reorder a bounded candidate set for the query.
- **General meaning:** a later-stage relevance model after broad retrieval.
- **This repository:** `retrieval/rerank.py` validates provider indices; `retrieval/pipeline.py:242-299` calls the provider.

## Evidence packet

- **Plain English:** the small local packet of source spans and exact quote candidates given to the writer.
- **General meaning:** a grounded context object with provenance and citation handles.
- **This repository:** `answering/context.py:317-421` builds it from reranked hits.

## Structured output

- **Plain English:** the provider must return a typed JSON shape rather than arbitrary prose.
- **General meaning:** schema-constrained model output.
- **This repository:** `providers/openrouter.py`, `answering/generate.py`, and Pydantic draft models in `contracts.py`.

## Grounded draft

- **Plain English:** a proposed answer whose claims select exact quote IDs from the packet.
- **General meaning:** an intermediate model output subject to evidence validation.
- **This repository:** `GroundedDraft`, `draft_schema`, and `GroundedAnswerEngine` in `answering/generate.py`, `answering/grounded.py`.

## Semantic invariant

- **Plain English:** a deterministic check that rejects dangerous changes such as altered quantities, dates, status, conditions, or polarity.
- **General meaning:** a property that must remain true across transformations.
- **This repository:** `answering/semantic_invariants.py`; it is deliberately narrower than general entailment.

## Support decision

- **Plain English:** the local decision about whether selected evidence can answer the request.
- **General meaning:** a policy/sufficiency gate before generation.
- **This repository:** `answering/context.py:423-560` returns answerable, partial, insufficient, live-required, prohibited, or conflict states.

## Provider boundary

- **Plain English:** the small interface through which the application asks a model service to plan, embed, rerank, or write.
- **General meaning:** dependency inversion around an external service.
- **This repository:** `providers/base.py` defines the protocol; `providers/openrouter.py` and `providers/fake.py` implement it.

## Live data

- **Plain English:** current official records fetched at request time, not stable document guidance.
- **General meaning:** time-sensitive external data with freshness and outage semantics.
- **This repository:** `live.py`, `live_answering.py`, and `api.py` map routes.

## Release evidence

- **Plain English:** a run artifact tied to exact code, data, configuration, and reviewer state.
- **General meaning:** reproducible evidence for a release decision.
- **This repository:** `benchmark.py`, `qualification.py`, owner-review scripts, `docs/reports/`, and `docs/releases/`.
