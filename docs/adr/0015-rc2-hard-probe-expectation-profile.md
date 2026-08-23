# ADR 0015: RC2 hard-probe expectation profile

- Status: Accepted
- Date: 2026-08-23

## Context

Mandatory structured publication changed ten deterministic hard-probe responses without
changing their questions or the runtime safety boundary. Nine cases now publish reviewed
official wording as `partial` / `official_quote_only`; J01 now returns a deterministic
`scope_redirect` to the issuing authority because no reviewed structured claim covers the
high-risk follow-up. The frozen public `hard_probe.v1.yaml` remains useful as historical
regression evidence and must not be rewritten to make the new behavior pass.

The release floor remains 86 of 105. A mode-only exception would be too weak: it could
accept generated prose, missing evidence, a rejected validation result, or a handoff that
does not preserve the intended authority boundary.

## Decision

The hard-probe CLI has two named expectation profiles:

- `historical` is the default and uses the frozen dataset expectations unchanged.
- `rc2` loads the repository-owned, hash-bound
  `data/evaluation/hard_probe_rc2_expectations.v1.yaml` overlay.

There is no CLI argument for an arbitrary overlay path. The RC2 overlay has the exact
top-level fields `schema_version`, `profile`, `base_dataset_sha256`, `minimum_passed`, and
`migrations`. Its manifest binds the overlay hash, base dataset hash, ten sorted migration
IDs, migration count, and 86-case floor. Pydantic rejects additional fields, and the loader
also rejects any changed migration ID, order, mode addition, invariant, rationale, hash,
base binding, count, or floor.

The effective expectation digest is the SHA-256 of canonical JSON using sorted keys,
compact separators, and UTF-8 without ASCII escaping. Its payload is:

```text
{
  schema_version: firelens.hard_probe_effective_expectations.v1,
  profile,
  base_dataset_sha256,
  minimum_passed,
  cases: [
    {id, allowed_modes, migration}
  ]
}
```

Cases stay in frozen dataset order. Allowed modes stay in their base order, followed only
by the non-duplicate profile addition. `migration` is the full overlay migration or null.
The base dataset hash binds the questions, expected text, history, priority, case count,
and all unlisted expectations, so the overlay cannot change them.

## RC2 migrations

The exact migration IDs are A04, A05, A07, A08, A09, A10, I01, I02, J01, and J02.

For the nine cases other than J01, RC2 adds only `partial` and requires:

- at least one public claim and one evidence item;
- every public claim to have publication kind `official_quote_only`;
- accepted validation;
- every support quote to be non-empty, linked to emitted evidence, and contained exactly
  in that evidence's `primary_text`; and
- zero generation-stage attempts and zero generation-stage cost.

For J01, RC2 adds only `scope_redirect` and requires:

- zero claims and zero evidence;
- reason code `high_risk_claim_not_structured`;
- the exact deterministic official issuing-authority handoff; and
- zero generation-stage attempts and zero generation-stage cost.

Mode acceptance and these invariants are conjunctive. A migrated case fails when either
the existing semantic checks or any migration invariant fails.

## Report contract

New runs emit `firelens_hard_probe_report.v2`. The report manifest retains every prior
material/runtime hash and adds the Git tree, expectation profile, overlay SHA-256 (null for
historical), and effective-expectations SHA-256. Each case records its effective allowed
modes, the full applied migration or null, existing base semantic issues, and each migration
invariant with its name, expected value, actual value, and pass result.

Historical mode preserves the previous case scoring and exit behavior. A full RC2 run is
successful when at least 86 of the same 105 cases pass; a selected RC2 subset remains
successful only when every selected case passes. Offline success remains wiring and
deterministic-contract evidence, not independent semantic proof.

## Consequences

- The original dataset and its manifest remain byte-for-byte unchanged.
- Candidate validators can recompute the overlay and effective hashes and independently
  inspect every migrated response and provider stage.
- Any future expectation change requires a new named profile and a new hash-bound artifact;
  it cannot be smuggled into RC2 through a local path.
