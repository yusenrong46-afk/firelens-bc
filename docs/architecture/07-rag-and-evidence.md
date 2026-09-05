# 07 — RAG and Evidence

[`answering/service.py`](../../src/firelens/answering/service.py) is the static RAG orchestrator. It is called only after the agent plan has authorized an exact static subrequest.

## Pipeline

1. Static planning produces up to three normalized retrieval requests and required aspects.
2. [`retrieval/pipeline.py`](../../src/firelens/retrieval/pipeline.py) runs BM25 and dense retrieval, fuses rankings with reciprocal-rank fusion, then reranks a bounded set.
3. [`answering/context_packet.py`](../../src/firelens/answering/context_packet.py) turns candidate hits into an `EvidencePacket` with exact quote candidates, conflicts, provenance, corpus version, and limitations.
4. Support logic determines answerable, partial, insufficient, prohibited, or conflict state.
5. High-risk eligible claims compile from reviewed typed records; lower-risk grounded content may use bounded generation.
6. Validation binds all public support back to the packet.

## Component contract

| Item | Contract |
| --- | --- |
| Input | Plan-authorized stable-guidance question and current versioned corpus/index |
| Output | `RetrievalBundle`, `EvidencePacket`, support decision, and a validated static `AskResponse` |
| Invariants | No open-web search; evidence IDs are packet-specific; public quotes are exact source substrings; general background carries no corpus support |
| Failure modes | Planner/provider unavailable, index/corpus mismatch, incomplete embedding batch, invalid rerank indices, insufficient authority/aspect coverage, conflicting sources, generation failure |
| Observability | Retrieval bundle records stage counts/timings/models/usage; local traces retain allowlisted aggregates. Endpoint telemetry currently collapses stage timing to total. |
| Tests | `test_static_rag.py`, `test_v1_5_rag.py`, `test_adaptive_retrieval.py`, `test_evidence_packet_identity.py`, `test_conflict_handling.py`, `test_corpus_admission.py` |
| Evaluation | ProductBench static cases, ClaimBench, hard probe, sealed retrieval protocol, source-aware conversation |

## Default strategy

The default configuration is `baseline`: BM25 top 30, vector top 30, fused top 30, rerank top 5, and up to 5 evidence spans. `adaptive_v1` can perform a second bounded retrieval cycle for missing aspects, but the current runbook records it as retained experimental behavior, not the promoted default and not qualified.

Default provider model identifiers are `openai/text-embedding-3-small`, `cohere/rerank-4-pro`, and `openai/gpt-5.6-luna`, all routed through the OpenRouter adapter. Those identifiers also appeared in the named production baseline’s readiness response on 2026-09-04. Readiness is not a provider call receipt and does not prove the endpoint, fallback, retention, quality, or cost of an inference.

## Evidence limits

Explicit source requirements survive a missing source or plural wording such
as “guides” and “checklists.” The static service reuses the shared attribution
grammar instead of downgrading the request based on candidate overlap.
Unsupported handoffs claim source discovery only after matching packet source
IDs/chunk IDs or distinctive requested names. Unmatched retrieval is not a
requested document, and matched links are still not proof of an answer.
General-background proof cards identify model knowledge, never an unrelated
live publisher or the generic “FireLens reviewed sources” fallback.

Personal documents to pack are belongings, not source identifiers. A bounded
document-preparation grammar in `guidance_capabilities.py` selects the existing
hash-bound documents/medications capability, including its exact approved
retrieval aspects and quote allowlist. It does not accept named-source prefixes,
extra clauses, or unrelated paperwork requests. No corpus text or approval was
added. Integration tests check actual document content, not only a partial mode
or the presence of an authoritative but irrelevant sprinkler claim.

Retrieval relevance is not semantic entailment. Exact quotation establishes textual occurrence, not that a generated paraphrase preserves every action, quantity, condition, status, or date. Tier A/B publication therefore uses deterministic typed records or exact quote-only fallback; lower-risk validation remains bounded and must not be described as comprehensive semantic verification.
