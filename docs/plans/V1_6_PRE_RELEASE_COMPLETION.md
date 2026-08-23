# FireLens V1.6 pre-release completion plan

Status: frozen RC1 ready for independent examination.

Target: `1.6.0-rc.1` ready for a named human release decision. Publishing this
engineering candidate to GitHub `main` does not advance its qualification
state; this plan stops before production deployment and release approval.

## Starting state

- Working branch: `upgrade/v1-6-pre-release-candidate-1`
- Hardening report commit: `5ee867e7508cb35955c943ed8a383edf2a1c04b0`
- Evaluated hardening implementation: `9e4e01dd07257c2af926ede4c1b33e1798b7e6d8`
- Current status: `READY_FOR_INDEPENDENT_EXAM`
- Raw candidates dispositioned: 36/36
- Prepared proposals: 20, approved by Thomas and integrated; the immutable
  preparation artifact remains unchanged as raw proposal provenance
- Edited SPRINKLER decision: approved by Thomas and integrated
- Source-repair dispositions: 9/9 explicitly deferred outside V1.6

Every later execution must re-read branch, commit, tree, and worktree state.

## State ladder

```text
LOCAL_GITHUB_CHECKPOINT_READY
→ HUMAN_CLAIM_REVIEW_COMPLETE
→ SOURCE_REPAIR_SCOPE_CLOSED
→ FROZEN_V1_6_RC_CANDIDATE
→ INDEPENDENT_EXAM_PASSED
→ H0_H9_LOCAL_QUALIFICATION_COMPLETE
→ PAID_QUALIFICATION_COMPLETE
→ H10_EVIDENCE_COMPLETE
→ READY_FOR_HUMAN_RELEASE_DECISION
```

## Phase 0: local GitHub checkpoint

1. Commit the GitHub governance standard and CONTRIBUTING linkage.
2. Mark historical state as historical and update the current runbook and
   examination handoff.
3. Regenerate ignored review packets and verify their checked manifests.
4. Run secret scan, zero-cost identity/package gates, and `make verify`.
5. Keep the branch local until the owner says `push this branch`, `push to
   origin`, `open a pull request`, or `update the GitHub branch`.

GitHub authentication and remote CI are external to the local checkpoint.

## Phase 1: named claim decisions

Review batches 2 and 3 sequentially on
`review/v1-6-typed-claims-batch-2` and
`review/v1-6-typed-claims-batch-3`.

Completed: Thomas approved all 20 proposals as proposed. The source-bound
append-only journals are `V1_6_TYPED_CLAIM_REVIEW_BATCH_2_DECISIONS.yaml` and
`V1_6_TYPED_CLAIM_REVIEW_BATCH_3_DECISIONS.yaml`; their claims remain outside
the production inventory until Phase 3.

For every proposal, the human records one of:

```text
approve
approve_after_edit
reject
defer
```

Completed: Thomas approved `TC-SPRINKLER-001` after editing it to the complete
bound source surface. The coding agent prepared packets and validated bindings;
it did not supply reviewer identity or approval.

Phase 1 gate complete: all 21 approval decisions bind to admitted documents and
exact quotes. Production support was enabled only by the separate Phase 3
integration.

## Phase 2: source-repair scope

Completed: Thomas selected `defer_out_of_scope` for all nine extraction-defect
records. They remain absent from the production inventory.

The owner assigns each of the 9 `needs_source_repair` records exactly one
scope decision:

```text
repair_for_v1_6
defer_out_of_scope
```

Repairs must use admitted official material, retain provenance, receive a new
pending proposal, and pass named human review. Deferral is valid coverage
governance; the plan does not force defective extraction into structured
publication.

Gate: 9/9 scope decisions and no ambiguous repair backlog.

## Phase 3: RC integration and freeze

Completed implementation candidate: `a5cd967ee97fc22f38b3ca79ef9a1672e50260ba`
with tree `4c45af3bf6ec1e0f8fe91aa741295f300d4053d9`. The inventory contains
26 bound production-supported records and the integration is reproducible from
the decision journals.

Create `upgrade/v1-6-pre-release-candidate-1`. Integrate only human decision
journals, validated inventory/source repairs, explicit deferrals, current
documentation, and content-free manifests.

Record exact branch, commit, tree, package, corpus, inventory, evaluation,
provider, and retrieval identities. Any later source, corpus, index, prompt,
model, threshold, configuration, dependency, code, or approved-surface change
invalidates downstream evidence and requires a new candidate number.

## Phase 4: independent examination

Ready to start: Thomas accepted the exact RC1 representative-workload H8
tradeoff in the hash-bound `V1_6_RC1_H8_TRADEOFF_DECISION.yaml`. This is not a
production SLO or paid qualification result.

An independent reviewer examines the frozen candidate without exposing held-out
labels to implementation. The examination must cover authority bypasses,
semantic entailment, critical-field preservation, same-chunk false selection,
partial coverage, Proof Card identity, and usefulness without invented support.

Allowed verdicts:

```text
READY_FOR_QUALIFICATION
NEEDS_REPAIR
IMPLEMENTATION_REGRESSED
```

Any repair restarts the freeze and examination phases.

## Phase 5: exact-candidate H0-H9

Run on the unchanged frozen candidate:

```text
make secret-scan
make v1-6-package-verify
make v1-6-gate
.venv/bin/python scripts/v1_6_structured_publication_eval.py
.venv/bin/python scripts/run_hard_probe.py --mode offline --output /tmp/v1_6_rc_hard_probe.json
.venv/bin/python scripts/v1_6_structured_publication_benchmark.py --iterations 500 --output /tmp/v1_6_rc_publication_benchmark.json
make v1-6-pre-release-performance
make v1-6-retrieval-dry-run
make verify
```

Gate: zero structural leaks, 100% critical-field preservation, hard probe at
least 86/105 with zero paired regression, no p95 regression above 10%, frozen
thresholds unchanged, baseline retrieval retained, and all repository checks
green.

## Phase 6: authorized paid H4/H8

Do not start until independent examination passes and the owner explicitly
authorizes each command and ceiling.

Proposed maximum budget:

| Run | Ceiling |
| --- | ---: |
| Three-repeat sealed retrieval | $0.75 |
| Qualified hard probe | $0.25 |
| Canary | $0.50 |
| Paid conversation/performance | $1.50 |
| Total | $3.00 |

H4 requires recall at least 95%, evidence precision@5 at least 80%, no paired
regression, and sealed retrieval at least 46/47 in each of three final
repetitions. H8 requires the frozen route-call budgets and no unexplained p95
regression above 10%.

## Phase 7: preview and H10

Requires explicit preview, firewall, rollback, and paid authorization. Bind the
preview to the frozen commit and verify required ZDR, deny-collection,
no-fallback, baseline-retrieval, readiness, privacy, debug-route, and runtime
artifact contracts.

Execute preview probes, deployment gates, a real rollback, firewall/rate-limit
review, VoiceOver tasks, and human comprehension tasks. Automation is not human
accessibility or UX evidence.

Gate: paid, human, preview, firewall, rollback, accessibility, privacy, and
sealed evidence is complete on the unchanged candidate.

## Phase 8: release-decision packet

Prepare a cumulative draft PR to `main` with exact identity, human decisions,
repair/defer ledger, independent examination, H0-H10 evidence, actual paid
cost, preview and rollback proof, accessibility/UX notes, GitHub CI, and
remaining limitations. Require named critical review. Do not enable auto-merge.

Terminal status: `READY_FOR_HUMAN_RELEASE_DECISION`.

## Stop conditions

| Condition | Status |
| --- | --- |
| Starting identity differs | `BLOCKED_IDENTITY_MISMATCH` |
| Worktree dirty before push or qualification | `BLOCKED_DIRTY_WORKTREE` |
| GitHub authentication unavailable | `BLOCKED_GITHUB_AUTH` |
| Human decisions incomplete | `NEEDS_HUMAN_CLAIM_REVIEW` |
| Independent examination fails | `NEEDS_REPAIR` |
| Safety, truth, privacy, or benchmark invariant regresses | `IMPLEMENTATION_REGRESSED` |
| Paid or external authority missing | `BLOCKED_EXTERNAL_AUTHORIZATION` |
| H10 evidence incomplete | `H10_INCOMPLETE` |
| Candidate changes after qualification | invalidate and freeze a new candidate |
