# V1.6 structured publication engineering report

Historical snapshot: structured-publication freeze `6d62671850d7fb46b0b0f06ada8eb0462f081d18`.
It does not describe later named-human claim-review decisions.

Local zero-cost qualification of `upgrade/v1-6-structured-publication`.
This is not a release GO and not `READY_FOR_PAID_H4`. Independent
structured-publication examination is still required. Visible development
benchmarks are not independent proof.

## Identity at report time

Starting examined candidate:

- Commit: `8b2da4ce8e334fcc53f053cbefb9e01e3caf17b2`
- Tree: `0e885a652e20d89ae54bb83d90bd41720149fd74`
- Rollback: `examined/v1-6-semantic-round3`

Working branch: `upgrade/v1-6-structured-publication` (local only).

## What changed

High-risk publication is now:

```text
reviewed typed claim or typed live fact → deterministic compilation → supported publication
```

`GroundedAnswerEngine` no longer publishes free-form Tier A/B sentences as
`VERIFIED_CORPUS` support. Uncovered high-risk retrieved text becomes
`official_quote_only` or an official handoff. Proof Cards copy the compiled
block. The frontend does not infer support from citation presence.

## Inventory

Four records remain structured-available. `TC-EVAC-ALERT-001` and
`TC-SPRINKLER-001` are `pending_review` after failing comparison against
their own source spans. 36 additional candidates are pending. The coding
agent did not approve any record.

## Gates (EXECUTED, not independent)

- Structural publication gates: 0 violations
- Development architecture tests: pass
- ClaimBench v1: 200/200; v2: 332/332; catalogs unchanged
- Hard probe: 86/105; failed IDs identical to Round 3; zero paired regressions
- High-risk representative Ask: 0 grounded generation calls (FakeProvider)
- Frontend vitest: 47/47

Paid H4 remains BLOCKED.
