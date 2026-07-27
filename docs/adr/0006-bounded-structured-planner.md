# ADR 0006: A bounded structured planner after safety routing

Status: accepted
Date: 2026-07-26

## Context

Keyword-only domain routing rejected valid wording and could not resolve a
follow-up such as “Which one comes first?” The V1 `QueryPlan` also allowed more
than one retrieval request while the pipeline executed only the first.

## Decision

FireLens uses three ordered decisions:

1. deterministic high-risk routing over the current question and bounded
   conversational context;
2. deterministic local handling for greetings, corpus discovery, and example
   prompts;
3. one strict structured planner call for all remaining requests.

The planner returns only a relation (`grounded_candidate`, `adjacent`, or
`tangent`), one to three standalone retrieval queries when the relation is
related, and a short diagnostic explanation. It receives no authority to
answer, cite sources, or change a safety decision. Duplicate normalized queries
are removed locally. Schema failure is a typed provider failure and does not
fall back invisibly to raw-question retrieval.

All planned queries are executed. Their lexical and dense rankings are fused
deterministically before one final reranker call. Query embeddings are batched
to keep the cost of decomposition bounded.

## Consequences

The model is used for the narrow ambiguity it handles well, while safety and
promotion remain deterministic. Follow-up behaviour becomes testable through a
small contract. The additional planner call adds latency and cost, so the
benchmark records exact paid stages and capability/safety routes must still
make zero provider calls.
