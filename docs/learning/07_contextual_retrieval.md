# Learning note 07: Add search context without changing the quotation

Consider a small source passage: “Start at the home and work outwards.” On its
own it may omit the terms a user searches for. A deterministic retrieval view
can add governed metadata:

```text
Publisher: FireSmart BC
Document: FireSmart BC Begins at Home Guide
Section: Home Ignition Zone
Temporal class: stable guidance
Passage: Start at the home and work outwards.
```

BM25, embeddings, and reranking may use this expanded string. Citation and
quote validation still use only the original passage. That separation prevents
metadata labels from being presented as source prose.

The strategy name belongs in the vector manifest and embedding-cache key. An
index built under one strategy cannot be opened under another. Context is an
experimental retrieval feature: development data decides whether it improves
recall, and the sealed holdout is not used for tuning.
