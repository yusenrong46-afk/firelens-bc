# FireLens BC V1.5 execution state

Updated: 2026-07-30 (America/Vancouver)

## Repository truth

- Remediation worktree: `/Users/thomas/Downloads/firelens-bc-v1-5-lab`
- Remediation branch: `maintenance/v1-5-principal-remediation`
- Remediation base: `d49a33e99464dbcdf35126b66aa8fb28ac657ba5`
- Earlier V1.5 candidate on `main`: `fc1c7d0bb55aa18c94b2e6540cd6590c5385ad7c`
- V1.1 baseline: `209b4e5f8f16f13d7ac9af56a89e135f697ce052`
- The original dirty checkout, `main`, release branches, production, and secrets were not modified.
- A dedicated release-reconstruction worktree has not been created.

## Current decision

The principal-remediation implementation is locally verified, but V1.5 remains **not
release-qualified**. The remediated branch is the next review candidate; it has not been merged,
pushed, previewed, or deployed.

The corpus changed from 180 to 170 chunks because ten chunks derived from a FireSmart page repair
were not backed by human approval. The unapproved page remains in the repair registry as
`pending_owner_review`, but is absent from the runtime corpus and vector index. All older paid,
retrieval, latency, and semantic reports remain historical evidence for their recorded commits;
they do not qualify the new corpus hash.

## Current local evidence

- Full repository verification passes on the remediated code: secret scan, generated OpenAPI and
  TypeScript contract checks, Ruff, formatting, mypy, Python tests, frontend tests, production
  build, Sites packaging, and desktop/mobile Playwright. The final run recorded 203 Python tests
  passed, 10 opt-in network/paid tests skipped, 76 Python subtests, 12 frontend tests, 4 Sites
  packaging tests, and 18 Playwright flows.
- The permanent hard probe passes `105/105` in `offline` mode with controlled provider and live
  doubles and zero paid calls. The same run initially exposed ten failures; general question-to-
  evidence support, mixed-scope routing, deterministic evaluator fidelity, and status-definition
  validation were corrected before the clean result.
- Focused adversarial tests reproduce and close action inversion, changed quantities/dates,
  evacuation-status substitution, removed conditions, safety-action polarity, cross-authority
  conflict, irrelevant citations, unapproved repair provenance, stale live wording, unknown
  geometry, pagination, proxy spoofing, oversized streaming bodies, production debug exposure,
  readiness status, conversation-history round-trip, and public request deadlines.
- Runtime corpus: 8 sources, 170 chunks, SHA-256
  `d5fcd794f9ec0486a256ae511366fde982254342b7d07b9c83a21ea8ead291eb`.
- Runtime vector matrix: 170 × 1,536, SHA-256
  `fd0b171488809c5a87f3aee5c912b07358231cac6478bb621f6d2fc79d41efb7`.

Offline hard-probe success validates deterministic wiring and policy behavior. It is not evidence
of live-model semantic quality, production latency, provider reliability, or OpenRouter cost.

## Foundation alignment

- Deterministic code still owns safety, evidence admission, exact citations, protected-fact
  preservation, conflicts, freshness, geometry, schemas, and final answer acceptance.
- Models remain bounded proposal writers. No runtime LLM judge, fallback provider, GraphRAG path,
  new model, new corpus source, retrieval configuration, framework, or public response shape was
  introduced.
- Exact quote identity remains provenance evidence, not a claim of general entailment. Human
  semantic review remains mandatory.
- Live chat and map continue to share one typed data service. Degraded and stale states are
  explicit and no-result wording does not imply safety.
- The public surface remains the existing conversation plus evidence/map panel.

## Human, paid, and external gates still open

- Complete 105-case qualified OpenRouter hard-probe rerun on the remediated commit and corpus.
- Regenerated and signed 47-case retrieval review, followed by the one-time three-repetition
  sealed retrieval run requiring at least 46/47 Recall@5 in every repetition.
- Regenerated and signed 50-case semantic review with zero unsupported or unclear material claims.
- Fresh generalization, novel-document, live-source, cached-live latency, and concurrency evidence
  bound to the remediated commit.
- Anonymous preview, browser accessibility review, externally enforced distributed rate limit,
  rollback rehearsal, release-tree reconstruction/equality, and owner approval.

The in-repository Vercel firewall plan now renders enforced deny rules but does not publish them.
It is not a distributed-enforcement claim until an owner-approved preview proves the external
rule is active and shared across instances.

## Next authorized action

Review the remediation report and diff. If accepted, publish only this review branch for external
inspection. Complete the deferred paid and human gates on an unchanged commit before reconstructing
a release branch. Merge and production deployment remain separate owner-approved actions.

See `docs/reports/V1_5_PRINCIPAL_REMEDIATION.md` for the finding ledger, implementation commits,
executed commands, and remaining-risk discussion.
