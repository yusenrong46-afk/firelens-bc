# Learning note 02: Test the stage that can fail

A single answer score hides where RAG failed. FireLens records BM25, dense, RRF,
reranker, routing, generation, validation, citation, latency, cost, and human
support separately. Retrieval tuning uses development labels only. Safety cases
exercise early exits without spending provider credit. The holdout is opened
only after configuration selection.

The current report demonstrates the value of separation: safety and quote
validity pass, while Recall@5 and answer-versus-abstention quality remain below
gate. Improving generation would not repair missing evidence.
