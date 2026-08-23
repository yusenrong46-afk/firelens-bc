# Fable 5 Round-1 examination (immutable import)

This file preserves the independent Fable 5 examination of candidate
`6f038b4cacc2204be2da0147240143ecfbde3c96`. It is testimony imported for
Round-2 qualification. Do not edit after Stage 0 freeze.

Source: independent examination returned in the prior conversation on
2026-08-17. Engineering implementation agents must not treat this as a
license to weaken tests or alter frozen benchmarks.

## Executive verdict (imported)

V1.6 is measurably better than frozen V1.5 on every locally executed axis,
with no paired regression and no benchmark gaming. Engineering verdict:
**NOT_PROVEN**. Release posture: **CONDITIONAL_NO_GO**.

H4 retrieval quality and parts of H8 were unmeasured. ClaimBench 200/200
does not prove general semantic robustness. Nine of fourteen examiner-crafted
nearby mutations passed `preservation_errors` in both V1.5 and V1.6.

## Proven paired improvements (imported)

```text
Frozen hard probe:             78/105 → 82/105  (0 broken)
Pure-static outer model calls: 1 → 0
Broad agent/API Exception catches: 5 → 0
Frozen ClaimBench vs each checker: 170/200 → 200/200
Docker/Vercel logical parity:  divergent → passing
Measured paired regressions:   0
```

## Examiner mutations that still passed the checker

```text
leave_to_stay          (later stopped by output rail)
immediate_to_delayed   (later stopped by output rail)
required_to_optional
unit_swap              1.5 metres → 1.5 feet
comparator_flip        at least ↔ at most
authority_swap         BC Wildfire Service → Environment Canada
exception_reversal     unless ↔ especially when
stale_as_current       2017 plan → current plan
overlap_opposite       does not mean ↔ does mean
```

Caught by the checker in both versions: alert↔order, negation drop,
1.5↔15 metres, date swap, condition omission.

Faithful paraphrases were accepted (always-abstain detector false).

## Hard gates (imported)

```text
H0 PASS
H1 PASS
H2 PARTIAL  (frozen catalog 200/200; generalization falsified)
H3 PASS local
H4 BLOCKED  (paid/sealed unmeasured)
H5 PARTIAL
H6 PARTIAL
H7 PASS automated; human AT EXTERNAL
H8 PARTIAL  (pure-static 1→0; fleet/p95 unmeasured)
H9 PASS
H10 EXTERNAL
```

Weighted score independently computed: 62/100.

## Remaining blockers used as Round-2 scope

1. Retrieval quality unmeasured.
2. Semantic preservation does not generalize outside the frozen catalog.
3. ClaimBench was co-developed with the checker.
4. Representative generative-call reduction unmeasured.
5. Route p50/p95 unmeasured in a matched environment.
6. Adaptive retrieval disabled and unqualified.
7. Twenty-three frozen hard-probe failures remain.
8. Paid, preview, rollback, firewall, deployed-provider, and human gates EXTERNAL.

## Non-negotiables carried forward

Do not alter the frozen V1.5 baseline, the 105-case hard-probe dataset or
evaluator semantics, or FL-V16-S1 thresholds. Do not inspect sealed labels.
Do not invent paid or sealed results.
