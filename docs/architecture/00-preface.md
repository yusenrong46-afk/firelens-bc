# 00 — Preface

This book describes what the current checkout implements. It does not describe an idealized architecture, certify upstream data, or carry release approval.

The accepted backend repairs are retained in the
[bounded repair record](../reports/BOUNDED_REPAIR.md). The current `37de779`
backend qualification and preview, and historical `b887cb4` UI measurements,
are identified separately in the
[System Card](../system-card/FIRELENS_SYSTEM_CARD.md). Earlier branch names and
counts below describe their dated observation, not a current release decision.

## Evidence method

The inspection followed one request from transport to publication, then checked contracts, direct tests, and known parallel owners. Assertions here use the evidence labels defined in the [book index](README.md#how-to-read-evidence). Historical reports are linked only when their identity remains visible.

The original Sol inspection base (historical, not the current repair identity) is:

- branch: `codex/firelens-eval-driven-upgrade`
- commit: `ae975132c5d65800c1e960c7b6e0c46844959dfe`
- tree: `c7952d897b09c2640cd0a2cc4313c925c32cd6ac`
- package/runtime version default: `1.6.4`
- state: historical local inspection; equivalence to the
  separately observed production baseline is **UNPROVEN**

Separately, the public production baseline was observed on 2026-09-04 at deployment `dpl_Ffh3orbdgQj8p7fdqwGmwZPuLYMh`, build `40c4c970bf33192ce6a543a6b8dcf5b4799036bd`. Readiness reported ready, release `1.6.4`, corpus `firelens_static_corpus.v1` with 179 chunks, and the configured embedding/rerank/generation models. This establishes a named observation, not current-candidate equivalence or production qualification. See the [System Card](../system-card/FIRELENS_SYSTEM_CARD.md).

## Truth hierarchy

1. Strict runtime contracts and deterministic validators.
2. The exact implementation and tests in the inspected checkout.
3. Generated repository maps, when their validator passes.
4. This architecture book and current-state record.
5. Historical plans, reports, screenshots, and release notes.

If two descriptions disagree, localize the first divergence and fix the earliest authoritative owner. Do not make a diagram cleaner by moving authority into prose.

## Scope

The book covers the FastAPI service, public Ask agent, official live adapters, static retrieval, publication contracts, React client, evaluation surfaces, observability, and qualification boundary. Exact wire shapes and owners live in the appendices: [API contracts](appendices/api-contracts.md), [data contracts](appendices/data-contracts.md), and [module map](appendices/module-map.md).
