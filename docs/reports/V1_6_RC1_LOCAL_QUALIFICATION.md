# FireLens V1.6 RC1 local qualification checkpoint

Date: 2026-08-23

## Verdict

```text
FROZEN_V1_6_RC_CANDIDATE
RC1_H8_TRADEOFF_ACCEPTED
READY_FOR_INDEPENDENT_EXAM
```

This checkpoint is not paid qualification, GitHub CI, preview/H10 evidence,
release approval, merge authority, or deployment proof.

## Evaluated implementation identity

| Field | Value |
| --- | --- |
| Branch | `upgrade/v1-6-pre-release-candidate-1` |
| Commit | `a5cd967ee97fc22f38b3ca79ef9a1672e50260ba` |
| Tree | `4c45af3bf6ec1e0f8fe91aa741295f300d4053d9` |
| Version | `1.6.0-rc.1` |
| Retrieval default | `baseline` |

The later evidence-only commit that checks in this report does not change the
evaluated runtime implementation.

## Decision integration

- Thomas approved all 20 prepared atomic proposals as proposed.
- Thomas approved `TC-SPRINKLER-001` after editing it to the complete bound
  official source text.
- Thomas deferred all nine extraction-defect candidates outside V1.6.
- The integrated inventory contains 26 unique production-supported typed
  records; every record has a valid authority binding.
- Candidate-to-production IDs and all decision hashes are recorded in
  `V1_6_RC_INTEGRATION_MANIFEST.json`.

| Artifact | SHA-256 |
| --- | --- |
| Integrated inventory | `75a183631a19dafbac9022ead6fd8dc3ba964eb7274981d17f4d479386673f38` |
| Integration manifest | `ba4f8628db08c7282a934bd16c49be846706a7c0c86334aacbac33c2f9c74dc1` |
| RC1 performance | `e930ad4218551a7a7d728209560eb69120b73bfa454122405a240393f17b8af2` |
| RC1 offline hard probe | `d0cfcb28a09be695455aafc0ea815df5fb623e2f175ceb4b053238a1deedb91f` |
| RC1 structured benchmark | `4bae0d4f80771154efd70593644c2cf4064da7e333227f7f397127e60d11337b` |

## Executed local gates

| Gate | Result |
| --- | --- |
| Focused decision/integration/architecture suite | 35 passed |
| Structural evaluator | Passed; all five leak counters zero |
| Offline hard probe | 86/105 at $0.00; same 19 failed IDs as Batch 1; zero paired regressions |
| Structured benchmark | 26 packets × 500 iterations; p50 `1.347417 ms`; p95 `1.924208 ms`; provider calls `0`; unrelated same-chunk selection `0` |
| Package contract | Passed; staged Docker/Vercel inventories unavailable locally |
| Frozen-standard loader | `FL-V16-S1`, seal and snapshot present |
| Retrieval dry run | Baseline retained; adaptive disabled; sealed labels not inspected; paid evidence blocked |
| Full `make verify` | 924 backend passed, 3 skipped, 448 subtests; 47 frontend passed; build passed; 4 Sites passed; 26 Playwright passed |

## Exact-candidate H8 measurement

The RC retains a 58.33% representative generation-call reduction, from `1.2`
to `0.5`, and pure-static publication makes zero generation calls. Every route
had zero failures. Three routes exceeded the frozen relative p95 boundary:

| Route | RC p95 | Relative change versus V1.5 |
| --- | ---: | ---: |
| `capability` | `6.384583 ms` | `+10.14%` |
| `mixed_live_and_static` | `25.208625 ms` | `+1633.74%` |
| `pure_static_guidance` | `14.850583 ms` | `+38.39%` |

Thomas accepted this exact representative-workload tradeoff. The decision is
bound to the RC1 report SHA-256 and evaluated implementation identity in
`V1_6_RC1_H8_TRADEOFF_DECISION.yaml`. It does not establish a production SLO or
waive remeasurement after any candidate change.

## Remaining gates

1. An independent reviewer examines the frozen implementation candidate without
   exposing held-out labels to the implementation loop.
2. Paid H4/H8 requires explicit command-level authorization and a cost ceiling.
   The adaptive development dry run estimates `$14.4072`, above the earlier
   proposed `$3.00` envelope.
3. Preview, rollback, firewall, privacy, VoiceOver, comprehension, and other
   H10 evidence remain external.
4. GitHub publication and CI remain separate from local qualification evidence.

No paid call, sealed-label inspection, push, PR, merge, preview, or deployment
was performed for this checkpoint.
