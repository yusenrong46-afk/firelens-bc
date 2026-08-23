# V1.6 typed inventory audit

Historical snapshot: structured-publication freeze `6d62671850d7fb46b0b0f06ada8eb0462f081d18`.
It does not describe later named-human Batch 1 decisions.

Inspected on the structured-publication working tree after demoting
source-mismatched records. Labels: **EXECUTED** for comparison,
**INSPECTED** for coverage notes.

## Production inventory

File: `data/typed_claims/high_risk_v1.yaml`

| claim_id | review state | source binding | snapshot vs own span | structured support |
| --- | --- | --- | --- | --- |
| TC-EVAC-ALERT-001 | pending_review | span present, revision `page:10` | removes a material condition | no |
| TC-EVAC-ORDER-001 | approved_static | valid | match | yes |
| TC-EVAC-RESCIND-001 | approved_static | valid | match | yes |
| TC-GAS-001 | approved_static | valid | match | yes |
| TC-SPRINKLER-001 | pending_review | span present, revision `page:3` | removes a material condition | no |
| TC-FRESHNESS-001 | approved_static | internal freshness language | match | yes |

Counts:

- valid / structured-available: 4
- pending re-review: 2
- invalid source binding: 0
- missing required constructor fields: 0 on the four available records

The coding agent did not rewrite ALERT or SPRINKLER and retain
`approved_static`. Candidate corrections are in
`docs/reports/V1_6_INVENTORY_CANDIDATE_CORRECTIONS.md` and remain
unapproved.

## Coverage domain

Still uncovered for structured support (quote-only / partial / handoff):

- most smoke driving and exposure actions
- closed roads / stay-out guidance (sparse or absent in the static corpus)
- campfire bans (not found in the ingested static corpus)
- FireSmart quantities and boundaries beyond the four remaining records
- vulnerable-population guidance
- most conditions and exceptions

36 pending candidates were extracted into
`data/typed_claims/candidates_pending_v1.yaml`. None are human-reviewed.
Reviewer identity is unset.

## Review command

```text
.venv/bin/python scripts/typed_claim_review_export.py \
  --output tmp/typed_claim_review_queue.html
```
