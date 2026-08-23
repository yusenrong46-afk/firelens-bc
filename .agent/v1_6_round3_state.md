# FireLens V1.6 Round-3 state

Kept under 300 lines.

## Starting identity

- Round-2 examined candidate: `40cabcb9a3a42888474d4de1a622ca84a3fd49b3`
- Round-2 tree: `446a802f112da5ce34abe8c398475ee2413d8ed9`
- Immutable local ref: `examined/v1-6-round2`
- Frozen V1.5 baseline: `3de745a22ad0801e19563f90ac64f18609ecae03`
- Working branch: `upgrade/v1-6-semantic-round3` (local only; do not push)
- Package: `1.6.0rc1` / `1.6.0-rc.1`
- Standard FL-V16-S1 sha256: `55e16b86960d51fb732970691a0c00850f6c56eb258cd363fd74a418b34d1bef`
- ClaimBench v1 sha256: `bcf885f65345e0b869982113c0890314bca522b8a9a3877eaf90140c6c6362d1`
- ClaimBench v2 sha256: `402b3dca3a53227d823861d2216446148a426174f388e94e8558eebf14ca3557`
- Hard probe dataset sha256: `ac1cd4980a9f3caff7c9ff3612a9d696c1f2bf5ee83d24f9793ae2d555975035`
- Fable Round-2 verdict being closed: `ENGINEERING_IMPROVED_LOCALLY` / formal `NOT_PROVEN` / `NOT_READY_FOR_PAID_H4` / `CONDITIONAL_NO_GO`

## Current patch group

Documentation and development-eval evidence. Implementation commits 1–8 are on the branch.

## Tests red/green

- Fable 71 checker: 71/71; unsafe FA 0; faithful FR 0; always_abstain false
- Round-3 extra 52: 52/52; unsafe publication 0
- ClaimBench v1 200/200; v2 332/332
- Hard probe 86/105; zero paired regressions vs Round 2
- Representative generate-call reduction 33.3% vs V1.5 (1.2 → 0.8)
- Verification: 891 pytest / 47 vitest / 26 e2e (e2e full-suite retry)
- Package-verify: logical pass; staged inventories BLOCKED

## Next exact action

Frozen. Do not push. Hand off for independent semantic re-examination.

## Benchmark status

Visible development benchmarks are not independent proof.
Adaptive retrieval remains disabled and unqualified.
Paid H4 remains BLOCKED until Fable reports READY_FOR_PAID_H4.

## Paid/external authorization state

- Paid retrieval: BLOCKED
- Sealed 46/47: EXTERNAL
- Preview/firewall/rollback/human AT: EXTERNAL
- Independent held-out semantic exam: not yet requested

## Residual risks

- Most corpus high-risk spans are not inventory-rendered
- Mixed FakeProvider path now uses one in-engine repair (3 generate calls)
- Isolated-harness F-U3/F-X1 still hit pre-existing validate_draft policies

## Rollback reference

```text
git switch examined/v1-6-round2
```

