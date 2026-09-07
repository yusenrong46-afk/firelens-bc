# J01 current acceptance proposal — decision pending

This is separate from the adopted PreparedBC source decision. It changes the
current evaluation contract, not production answer behavior.

The frozen `hard_probe_rc2_2_expectations.v1.yaml` requires `scope_redirect`,
zero claims, zero evidence, zero generation and the exact issuing-authority
handoff for “Why does that matter?” after the grab-and-go conversation. The
accepted product-completion test instead requires a supported partial answer
and a rationale or an explicit limitation when an explanation is unsupported.
The revised source contains the preparation rationale on page 4. The current
focused test passes with an exact source quotation and no generation. The old
candidate-evidence validator must still reject it under its frozen rules.

## Proposed owner decision

Authorize a separately versioned current J01 migration, while preserving the
legacy dataset, profiles, validator and failed artifacts without alteration.
The candidate package must carry the legacy result and independently recompute
the new current gate. It must not relabel the old J01 as PASS or omit the case.

The new gate must require all of the following:

1. The same original question and conversation history.
2. A partial response with accepted validation and nonempty supported claims.
3. Only exact official quotations, from admitted current document identities;
   every support must be a substring of its bound evidence passage.
4. A source-supported preparation rationale, or an explicit limitation that
   the selected source does not explain why; a positive checklist alone may
   not silently count as an explanation.
5. Zero generation calls and zero generation cost.
6. No personal stay, leave, return or evacuation decision and no current-status
   conclusion derived from static preparedness material.

Controls must reject missing/misattributed quotes, retired revisions, unsupported
rationale, positive checklists without the missing-explanation limitation,
generated rationale and fabricated conversation/source antecedents. Existing
unanchored follow-up and personal-safety tests remain protected.

Owner decision: **PENDING**. No active profile or candidate validator has been
changed by this proposal. Source admission is not acceptance-policy approval.

## Bounded execution allowance proposed separately

A new aggregate ceiling of **US$1** would cover the 34 missing embedding inputs
and one bounded real-provider smoke (up to eight Ask requests), using the existing
OpenRouter credential. Reuse only the 144 vectors whose complete rendered inputs
and embedding configuration were verified equal. No new key, model, large paid
evaluation campaign or deployment-secret change is proposed. Stop if the cost
ceiling cannot be enforced or the allowance is exhausted. No paid call has been
made during this resumed work.
