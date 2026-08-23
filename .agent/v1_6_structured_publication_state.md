# Historical FireLens V1.6 structured-publication freeze state

Kept under 300 lines.

This file records the `6d62671` freeze. It is not current candidate truth.
The successor branch is `upgrade/v1-6-structured-publication-harden-1`; see
`docs/reports/V1_6_STRUCTURED_PUBLICATION_HARDEN_1_REPORT.md` and re-read Git
identity before relying on it.

## Frozen candidate (EXECUTED)

- Historical branch: `upgrade/v1-6-structured-publication`
- Historical commit: `6d62671850d7fb46b0b0f06ada8eb0462f081d18`
- Rollback: `examined/v1-6-semantic-round3` @ `8b2da4ce8e334fcc53f053cbefb9e01e3caf17b2`
- Package: `1.6.0rc1` / `1.6.0-rc.1`
- Status: `NEEDS_HUMAN_CLAIM_REVIEW`

Recipients must run `git rev-parse HEAD` and `git rev-parse 'HEAD^{tree}'`.

## Loop result

At this historical freeze, architecture and zero-cost gates passed. Two
existing inventory records and 36 candidates required disposition. The later
hardening loop approved the edited ALERT surface, left SPRINKLER non-compilable,
dispositioned all 36 raw candidates, and prepared 20 atomic pending proposals.
Quote-only fallback remains the uncovered-content boundary.

Current continuation status is `READY_FOR_HUMAN_CLAIM_REVIEW_CONTINUATION`,
not `READY_FOR_PAID_H4`.

## Review command

```text
.venv/bin/python scripts/typed_claim_review_export.py --batch 2 \
  --output tmp/v1_6_typed_claim_review_batch_02.html \
  --decision-template tmp/v1_6_typed_claim_review_batch_02_decisions.yaml

.venv/bin/python scripts/typed_claim_review_export.py --batch 3 \
  --output tmp/v1_6_typed_claim_review_batch_03.html \
  --decision-template tmp/v1_6_typed_claim_review_batch_03_decisions.yaml
```

## Paid/external

- Paid retrieval: BLOCKED
- Sealed H4: not inspected
- Independent structured-publication exam: required after human review and a
  new exact-candidate freeze

## Rollback

```text
git switch examined/v1-6-structured-publication
```
