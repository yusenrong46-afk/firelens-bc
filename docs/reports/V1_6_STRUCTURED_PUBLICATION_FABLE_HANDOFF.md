# Independent structured-publication examination handoff

Do not run paid retrieval. Do not inspect sealed H4 labels. Do not copy a
held-out catalog into this repository. The development benchmark is not
the examination set.

## Candidate

Recipients must re-read git identity after the freeze commit:

```text
git rev-parse --abbrev-ref HEAD
git rev-parse HEAD
git rev-parse 'HEAD^{tree}'
git status --porcelain
```

Current RC branch: `upgrade/v1-6-pre-release-candidate-1`

Frozen implementation commit:
`a5cd967ee97fc22f38b3ca79ef9a1672e50260ba`; tree:
`4c45af3bf6ec1e0f8fe91aa741295f300d4053d9`.

Thomas's decisions are integrated: 20 prepared approvals, the edited
SPRINKLER approval, and nine out-of-scope source-repair deferrals. This
candidate is ready for independent examination, not paid H4 or release.

## Decisive checks

1. Can any model-created Tier A/B text become supported?
2. Can an unreviewed claim become supported?
3. Can mixed, rewrite, salvage, or fallback bypass the compiler?
4. Can Proof Cards strengthen quote-only or generated content?
5. Does a missing chunk, changed document, changed quote, or changed approved
   surface invalidate support?
6. Does usefulness collapse into generic unexplained abstention?
7. Does an unrelated fact sharing a larger source chunk select a reviewed
   claim?
8. Do all 36 raw candidates have one disposition, do the 20 integrated
   proposals remain atomic and corpus-bound, and are all nine deferred defects
   absent from structured support?

## Commands

```text
.venv/bin/python -m pytest -q \
  tests/test_typed_claim_inventory.py \
  tests/test_typed_claim_authority_binding.py \
  tests/test_typed_claim_candidate_preparation.py \
  tests/test_typed_claim_integration.py \
  tests/test_typed_claim_review_decisions.py \
  tests/test_typed_claim_review_export.py \
  tests/test_structured_publication_architecture.py \
  tests/test_structured_publication_dev_cases.py
.venv/bin/python scripts/v1_6_structured_publication_eval.py
.venv/bin/python scripts/run_hard_probe.py --mode offline --output /tmp/structured_pub_hard_probe.json
.venv/bin/python scripts/v1_6_structured_publication_benchmark.py --iterations 500 --output /tmp/structured_pub_benchmark.json
```

Require at least 86/105 with zero paired regression and no more than 10%
p95 regression. Do not treat development-suite scores as the held-out verdict.
