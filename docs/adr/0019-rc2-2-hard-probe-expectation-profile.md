# ADR 0019: RC2.2 hard-probe expectation profile

- Status: Accepted
- Date: 2026-08-26

## Context

A09 and A10 ask for the evacuation-alert versus evacuation-order distinction.
The runtime now publishes two-sided `structured_reviewed` coverage of
`TC-EVAC-ALERT-001` and `TC-EVAC-ORDER-001`, the same atomic pair required for
a grounded A02 comparison. The frozen RC2 and RC2.1 overlays still require an
exclusive `official_quote_only` publication-kind set for those two cases.
Because the overlay compares kind sets by equality, adding official quotes
alongside the reviewed claims cannot satisfy RC2.1 either.

Neither the historical hard-probe dataset, the ten-migration `rc2` profile, nor
the eleven-migration `rc2.1` profile may be rewritten. A later named overlay is
the same mechanism RC2.1 used for A01.

## Decision

Add the repository-owned, hash-bound `rc2.2` profile at
`data/evaluation/hard_probe_rc2_2_expectations.v1.yaml`. The CLI accepts the
named profiles `historical`, `rc2`, `rc2.1`, and `rc2.2`; `historical` remains
the default and arbitrary overlay paths remain forbidden.

`rc2.2` copies the eleven frozen RC2.1 migrations in their original order and
replaces only A09 and A10. It retains the same 105 questions, report schema
`firelens_hard_probe_report.v2`, and `86/105` floor.

For A09 and A10, `rc2.2` adds only `partial` and requires all of the following:

- non-empty public claims and evidence;
- the exact publication-kind set `{structured_reviewed}`, with no other kind;
- two-sided typed coverage of `TC-EVAC-ALERT-001` and `TC-EVAC-ORDER-001`;
- accepted validation;
- every non-empty support quote linked to emitted evidence and contained exactly
  in that evidence's `primary_text`; and
- zero generation-stage attempts and zero generation-stage cost.

A01 retains its exact mixed `{structured_reviewed, official_quote_only}`
contract. The remaining RC2 quote-only cases and J01 retain their RC2.1
contracts. The profile loader compares every migration field, ID, order,
rationale, hash, base binding, count, and floor against the named contract.

Candidate-evidence v2 uses `rc2.2` as its active qualification profile. Its
material roster includes the frozen RC2 pair, the frozen RC2.1 pair, and the
active RC2.2 pair. The verifier recomputes A09/A10 two-sided structured
coverage from claims, typed claim IDs, publication kinds, evidence, support
quotations, validation, and provider stages rather than accepting the report's
case-pass boolean as proof of those invariants.

## Consequences

- Historical, RC2, and RC2.1 artifacts remain byte-for-byte unchanged.
- A09 and A10 remain failures under RC2 and RC2.1 and pass under RC2.2 only
  when every two-sided structured invariant passes.
- Unlisted cases, questions, thresholds, schemas, and baseline evidence are not
  changed by the migration.
- Any later expectation change requires another named, independently hash-bound
  profile; RC2.2 cannot accept an arbitrary local overlay.
