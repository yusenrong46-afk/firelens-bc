# ADR 0016: RC2.1 hard-probe expectation profile

- Status: Accepted
- Date: 2026-08-23

## Context

The reviewed grab-and-go guidance for A01 now answers two distinct requested
aspects: a human-reviewed structured instruction to build a bag and an exact
official quotation listing its contents. The safe response is therefore
`partial`, with the two publication kinds labelled independently. The frozen
historical expectation accepts only `grounded`, so it no longer describes this
more explicit authority boundary.

Neither the historical hard-probe dataset nor the ten-migration `rc2` profile
may be rewritten. A mode-only exception would also be insufficient: it could
accept a response missing either publication kind, unsupported text, rejected
validation, an incorrect reason code, or generation activity.

## Decision

Add the repository-owned, hash-bound `rc2.1` profile at
`data/evaluation/hard_probe_rc2_1_expectations.v1.yaml`. The CLI accepts only
the named profiles `historical`, `rc2`, and `rc2.1`; `historical` remains the
default and arbitrary overlay paths remain forbidden.

`rc2.1` copies the ten frozen RC2 migrations in their original order and
appends A01 as the eleventh migration. It retains the same 105 questions, report
schema `firelens_hard_probe_report.v2`, and `86/105` floor.

For A01, `rc2.1` adds only `partial` and requires all of the following:

- non-empty public claims and evidence;
- the exact publication-kind set `{structured_reviewed, official_quote_only}`,
  with both kinds present and no third kind;
- accepted validation;
- every non-empty support quote linked to emitted evidence and contained exactly
  in that evidence's `primary_text`;
- reason code `high_risk_claim_not_structured`; and
- zero generation-stage attempts and zero generation-stage cost.

The nine RC2 quote-only cases retain their exact all-`official_quote_only`
contract. J01 retains its exact deterministic official handoff contract.
The profile loader compares every migration field, ID, order, rationale, hash,
base binding, count, and floor against the named contract.

Candidate-evidence v2 uses `rc2.1` as its active qualification profile. Its
material roster includes both the frozen RC2 profile/manifest and the active
RC2.1 profile/manifest. The verifier recomputes A01's response contract from
claims, publication kinds, evidence, support quotations, validation, reason
code, and provider stages rather than accepting the report's case-pass boolean
as proof of those invariants.

## Consequences

- Historical and RC2 artifacts remain byte-for-byte unchanged.
- A01 remains a failure under RC2 and passes under RC2.1 only when every stronger
  mixed-publication invariant passes.
- Unlisted cases, questions, thresholds, schemas, and baseline evidence are not
  changed by the migration.
- Any later expectation change requires another named, independently hash-bound
  profile; RC2.1 cannot accept an arbitrary local overlay.
