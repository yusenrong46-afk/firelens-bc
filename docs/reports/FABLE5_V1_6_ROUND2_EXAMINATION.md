# Fable 5 — V1.6 Round-2 independent re-examination (imported)

Status: immutable import of the Round-2 examination delivered against
`40cabcb9a3a42888474d4de1a622ca84a3fd49b3`. This file is evidence, not a
new examination. Round-3 implementation must not edit it.

## 1. Executive verdict

Round 2 is a genuine engineering improvement over V1.5 and Round 1. Every
quantitative claim the examiner reran reproduced (86/105 hard probe with
zero paired regressions, 332/332 ClaimBench v2 from rows, 41.7%
representative generate-call reduction, clean suites, honest freeze
ordering). The campaign’s central claim — that semantic-preservation
blind spots are closed — was falsified. A fresh 71-case adversary using
wording outside ClaimBench produced 22 checker-level unsafe accepts, and
7 of 10 tested survivors published as grounded supported claims,
including “Drive through areas of dense smoke” against a source saying
“Avoid driving through areas of dense smoke.”

Verdicts: `ENGINEERING_IMPROVED_LOCALLY`, formal `NOT_PROVEN`,
`NOT_READY_FOR_PAID_H4`, release `CONDITIONAL_NO_GO`.

## 2. Identity

Round-2 commit `40cabcb9…`, tree `446a802f…`, branch
`upgrade/v1-6-qualification-round2`, Python `1.6.0rc1`, Web `1.6.0-rc.1`.
V1.5 `3de745a2…`. Round 1 `6f038b4c…`.

## 3. Git status

Clean at start and end of examination. Candidate remained byte-identical.

## 4. Freeze integrity

ClaimBench v2 frozen before checker implementation. Hard-probe dataset
and evaluator semantics unchanged. No skips, xfails, or threshold
relaxations creating the reported gains.

## 5. Reproduced claims

ClaimBench v1 200/200; v2 332/332; hard probe 86/105; generate 1.2 → 0.7
(41.67%); pytest 872; vitest 47; Playwright 26. No serving-path broad
`except Exception`.

## 6–7. Fresh adversary and publication

71 examiner cases (22 faithful / 49 mutations). Checker: 47/71 correct,
22 unsafe false accepts, 2 faithful false rejects (`F-C1` “no fewer
than” → “at least”; `F-F1` stale-disclosure paraphrase containing
“live refresh”). Publication: 7 unsafe grounded accepts including
`M-M4` (avoid→perform), authority substitution, retrieval-time as
source-update-time, inclusive→exclusive, immediately→when convenient,
and high-overlap opposite meanings. Salvage did not resurrect rejected
claims. `always_abstain` false.

## 8. ClaimBench recalculation

Row-level totals match summaries. Catalogs are honest and
vocabulary-bound. Same-campaign benchmark/checker pairing masked the
generalization gap.

## 9–10. Hard probe

78 → 82 → 86/105. Newly passing D10, J03, K04, K10 are real routing
corrections. 19 remaining failures: taxonomy disagreement, fake-provider
limits, unsupported capability, two low-severity tangent defects. Zero
unsafe remaining failures. None independently blocks paid H4; the H4
block is the semantic publication gap.

## 11. Performance

Matched ASGI harness. Reduction is real work elimination, not
abstention. H8 locally satisfied as representative workload average.

## 12. Adaptive retrieval

50 development cases; default `baseline`; cost ceiling $14.4072
verified; paid path refuses without authorization. Remains experimental.

## 13–16. Failure, privacy, packaging, UX

Typed degradation; no public stack traces; logical packaging parity;
vitest/axe/Playwright green. Human AT and staged images EXTERNAL/BLOCKED.

## 17. Gaming

No benchmark manipulation. Stale-banner assertion tightened, not relaxed.

## 18–19. Gates and score

H2 FAIL under fresh adversarial evidence. H4 and H10 BLOCKED. Weighted
score 75/100 does not override failed/blocked hard gates.

## 20–26. Proven / falsified / uncertainty

Proven: probe +8, generate-call cut, freeze discipline, stale wording
fix. Falsified: “semantic blind spots closed” and “332/332 proves
generalization.” Residual risk: publication-unsafe rate outside the 71
visible cases.

## 27. Examiner next actions (not a Round-3 license to phrase-patch)

1. Fix publication-level unsafe accepts as classes (action polarity,
   open-lexicon authority, time-role, boundary inclusivity, urgency).
2. Commission a held-out adversary-authored benchmark.
3. Fix the two faithful false rejections.
4. Re-examine before spending paid H4.
5. Execute external H10 gates.

## 28–31. Verdicts

Local: `ENGINEERING_IMPROVED_LOCALLY`
Formal: `NOT_PROVEN`
Paid H4: `NOT_READY_FOR_PAID_H4`
Release: `CONDITIONAL_NO_GO`
