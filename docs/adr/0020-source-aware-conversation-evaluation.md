# ADR 0020: Execute source-aware conversation fixtures against the real agent

Status: proposed

## Decision

The V1.6.3 source-aware conversation suite remains development-unsealed and is
evaluated by executing the application agent with a fresh local vector index,
the deterministic fake provider, and deterministic official-record fixtures.
Observed route, response mode, source lane, publication kind, tool trace,
provider-stage counters, and failure status are scored independently of the
expected labels. The suite contains the 24 guided questions, at least three
paraphrases each, reproduced multi-turn conversations, and explicit safety,
mixed-lane, empty, provider-failure, and location fixtures.

The report binds the dataset and manifest, guided/capability registries, corpus
and vector artifacts, typed inventory, and Git commit/tree identity. It records
external network/model calls separately from local fake-provider calls. The
runner exits non-zero when routing recall, official compliance, handoff rate,
authority escalation, safe-general separation, or the zero Tier A/B generation
gate fails.

## Consequences

This proves that the current code path produces the observed contract under
deterministic fixtures; it does not prove provider quality, sealed-label
performance, source freshness, deployment readiness, or human review. A failed
offline result is preserved as a repair signal and must not be hidden by copying
expected labels into a report or by lowering the declared thresholds.
