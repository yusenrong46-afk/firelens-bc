# Learning note 05: Generalized RRF combines evidence discovery

A compound question can need several search phrasings or authority classes.
For each standalone query, FireLens produces a BM25 ranking and a dense ranking.
Generalized reciprocal-rank fusion gives a document credit from every ranking
in which it appears:

```text
RRF score(document) = sum(1 / (k + rank)) across all rankings
```

With two queries there are four input rankings, not two separate answers. Chunk
IDs are deduplicated after fusion, deterministic tie-breaking is preserved, and
one final reranker evaluates the combined candidate set against the resolved
conversational question.

RRF deliberately combines rank positions rather than incomparable BM25 and
cosine scores. Query attribution is retained so a retrieval miss can be traced
to planning, lexical search, dense search, fusion, or reranking. Retrieval is
still evidence discovery; it does not itself prove that an answer is supported.
