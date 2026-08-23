# FireLens V1.6.0-rc.1 Implementation Plan

Status: frozen before implementation. Mission and `FL-V16-S1` gates are unchanged.

This document preserves the V1.6 execution plan. The first coding commit contains
only the standard, baseline harness, and before-snapshot evidence.

## Mission

Upgrade the current FireLens V1.5 V3 candidate to **V1.6.0-rc.1** so it is
faster on ordinary supported questions, more complete on multi-aspect retrieval,
more explicit about evidence and trust, safer under semantic mutations, easier
to operate without storing private content, and demonstrably better than the
frozen V1.5 baseline.

Models may choose bounded tools and propose language. Approved source contracts,
deterministic code, and authorized humans decide what may be published as
supported fact.

## Starting identity

- Branch created from `3de745a22ad0801e19563f90ac64f18609ecae03` (`main` /
  `codex/v1-5-v3`)
- Working branch: `upgrade/v1-6`
- Package version at freeze: `1.5.3rc1` / `1.5.3-rc.1`
- Do not push. Do not use `codex/v1-6-moat-tutorial`.

## Assumptions

- Paid, preview, firewall, rollback, VoiceOver, participant UX, and sealed
  gates stay `EXTERNAL` unless later authorized with a cost ceiling.
- Do not mutate `data/evaluation/upgrade_benchmark_v1_5_2.yaml` or existing
  frozen catalogs.
- Adaptive retrieval stays behind `adaptive_v1` until H4 and H8 clear.
- The V1.5 test that requires one discarded outer Luna write is a contract to
  replace, not a safety test to weaken.
- Do not author the missing V3 sealed 47-case set.

## Standard

The frozen standard is `data/evaluation/firelens_v1_6_upgrade_standard.yaml`
(`FL-V16-S1`). Thresholds may not change after implementation results are
observed.

## Patch groups

1. Route budgets and pure-static fast path. Return validated static answers
   without an outer `chat_turn`.
2. Bounded adaptive retrieval behind `FIRELENS_RETRIEVAL_STRATEGY`, default
   `baseline`.
3. Additive claim-trust contract and frozen ClaimBench (≥200 cases).
4. Typed failures, content-free stage ledger, Source Change Radar, packaging
   parity.
5. Proof-carrying UX on the existing map-first assistant.
6. Module-size and documentation refresh, five golden traces.
7. Qualification and before/after comparison. No release GO without H10.

## Hard restrictions

No push, merge, deploy, firewall publish, secret retention, open-web retrieval,
microservices, GraphRAG, remote vector database, fine-tuning, or model-stack
novelty. A semantic model may reject only. Models may not invent official
arithmetic, names, statuses, dates, authorities, or distances.

## Definition of engineering-done

H0–H9 pass, score ≥90, no critical regression, at least three paired
improvements, and improvement is not manufactured through abstention. H10 is
required for release GO.
