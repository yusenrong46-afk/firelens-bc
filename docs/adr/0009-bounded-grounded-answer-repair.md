# ADR 0009: Bounded grounded-answer repair

- Status: Accepted
- Date: 2026-07-29

## Context

Grounded answers are generated from a fixed evidence packet and then checked by deterministic validation. A first draft can fail because its citations, quote text, or claim structure do not satisfy the public contract even when the packet contains enough support for a useful answer.

Returning an immediate abstention wastes valid evidence. An open-ended repair loop, new retrieval, or provider fallback would make the result harder to reproduce and could introduce unsupported source metadata.

## Decision

FireLens permits exactly one grounded-answer repair after the first deterministic validation fails.

The repair:

- receives the same question and the same evidence packet;
- may use only source, chunk, quote, and authority identifiers already present in that packet;
- may not retrieve new evidence, invent source metadata, or add quote identifiers;
- may not authorize its own answer; and
- is checked by the same deterministic validator used for the first draft.

If the repaired answer passes, it is returned normally. If it still fails, deterministic claim salvage may expose only independently valid claims as a `partial` answer. When no independently valid material claim remains, FireLens abstains.

There is no second repair, hidden provider fallback, model substitution, or model-memory fallback.

Generation and repair observations record the stage, model, attempts, latency, token usage, and validation result. Release evidence must distinguish a first-pass answer, repaired answer, partial salvage, and abstention.

## Consequences

- Useful evidence can survive formatting or claim-assembly failures.
- The maximum model-call count is bounded and measurable.
- Retrieval remains independent from answer generation.
- Deterministic validation remains the authority for citations and visible claims.
- Repair cannot silently expand the evidence boundary.

