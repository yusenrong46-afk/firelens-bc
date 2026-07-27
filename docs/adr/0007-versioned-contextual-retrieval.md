# ADR 0007: Versioned deterministic contextual retrieval

Status: accepted as an experiment; default selection pending measurement
Date: 2026-07-26

## Context

Short passages may lose the document, publisher, section, and locator terms
that help lexical and dense retrieval. Adding generated summaries would create
another paid, nondeterministic indexing dependency and could contaminate quoted
source text.

## Decision

FireLens supports two versioned retrieval-text strategies:

- `original_v1`: index the governed chunk text unchanged;
- `metadata_context_v1`: prepend deterministic local publisher, document,
  section, locator, and temporal-class labels to the passage used for search.

The retrieval representation may be used by BM25, embeddings, and reranking.
The original chunk remains the only citation and exact-quote authority. The
vector manifest and embedding-cache key include the strategy, and startup
rejects a strategy mismatch.

The new representation is an experiment, not an assumed improvement. Compare
the original single-query baseline, original multi-query retrieval, and
contextual multi-query retrieval on development labels. Select a new default
only if it preserves all safety conditions and improves the governed retrieval
metric by at least two percentage points. Do not tune on sealed holdout cases.

## Consequences

The experiment is reproducible and reversible. It may improve retrieval without
weakening citation integrity. It increases index size and requires rebuilding
vectors whenever the strategy changes. A negative result is retained as useful
evidence and leaves `original_v1` as the default.
