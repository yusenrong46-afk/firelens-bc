# ADR 0014: Mandatory structured publication

Status: accepted
Date: 2026-08-17

## Context

Independent examination of `8b2da4ce` / `0e885a65` returned
`SEMANTIC_SAFETY_FAILED`. The residual linguistic checker still false-accepted
a majority of held-out unsafe mutations, and 39 of 100 unsafe cases reached
supported publication. The architectural cause, confirmed by source
inspection, is that typed inventory is optional post-validation
canonicalization. Any LLM string that passes `validate_draft` becomes
`VERIFIED_CORPUS` and a Proof Card marked `supported`.

Phrase-list expansion cannot close this class. The publication model itself
must change.

Paid retrieval remains blocked. This ADR does not authorize H4.

## Decision

Replace:

```text
free-form LLM claim → linguistic checker → supported publication
```

with:

```text
reviewed typed claim or typed live fact → deterministic compilation → supported publication
```

For Tier A and Tier B, the model may select approved fact identifiers. It
may not create the factual sentence. The typed-claim inventory is a
mandatory publication authority.

## Non-negotiable rules

### Rule 1 — Risk may only rise

A deterministic classifier assigns or upgrades claim risk. The model may
propose a risk tier but must never lower:

```text
Tier A → Tier B
Tier A → Tier C
Tier B → Tier C
```

Application code takes `max(deterministic_tier, proposed_tier)` with
A > B > C.

### Rule 2 — Tier A/B model output contains no factual text

The high-risk answer-plan schema may contain only bounded identifiers and
organization decisions, for example:

```json
{
  "claim_ids": ["TC-EVAC-ORDER-001"],
  "quote_only_evidence_ids": [],
  "unknown_aspects": [],
  "section_order": ["reviewed_guidance"]
}
```

It must not contain `claim_text` or any equivalent free-form factual field.
Any outer-model Tier A/B sentence is ignored and never published.

### Rule 3 — Supported Tier A/B claims require reviewed authority

A Tier A/B claim may receive a supported public state only when it
references a human-reviewed typed claim or a typed official live fact
rendered by deterministic code. Required constructor fields:

```text
typed_claim_id or typed_live_fact_id
review state
source revision
renderer ID
support provenance
```

Agent-generated candidate records begin as `pending_review` and cannot be
marked human-reviewed by a coding agent.

### Rule 4 — Uncovered high-risk content fails safely

When no reviewed typed claim exists for retrieved high-risk evidence:

```text
exact official quote labelled quote-only
partial response
or official-source handoff
```

Reason code: `HIGH_RISK_CLAIM_NOT_STRUCTURED`. Never a generated supported
paraphrase.

### Rule 5 — Public trust types are distinct

Additive public publication kinds:

```text
STRUCTURED_REVIEWED
OFFICIAL_LIVE_TYPED
OFFICIAL_QUOTE_ONLY
SOURCE_LINKED_EXPLANATION
GENERAL_BACKGROUND
UNSUPPORTED
```

Unqualified `VERIFIED_CORPUS` is deprecated as the Tier A/B support signal.
The legacy `evidence_status` field may remain on the wire for frozen
evaluators, but Proof Cards and UI must display the publication kind.
Frontend code must not infer support from citation presence.

### Rule 6 — One atomic claim per public block

A public claim block represents one subject/action/status/quantity
relationship. An answer containing two safe facts and one unsafe fact cannot
be marked supported as one unit. Salvage may drop claims; it may not promote
an untyped high-risk generated claim.

### Rule 7 — Proof Cards use the same immutable object

Public text, claim ID, source revision, support state, and Proof Card
originate from one compiled claim block. The frontend must not recalculate
or strengthen trust.

### Rule 8 — Source changes invalidate support

A typed claim whose `source_revision_sha256` or `source_span_sha256` no
longer matches the bound source becomes unavailable until re-reviewed.

### Rule 9 — Semantic models reject only

A MiniCheck/HalluGuard/NLI-style component may reject or downgrade Tier C
content. It cannot promote, rewrite, supply evidence, establish authority,
establish freshness, or authorize Tier A/B publication. It cannot override a
deterministic rejection.

### Rule 10 — Existing generative RAG becomes Tier C only

`GroundedAnswerEngine` may remain for low-risk source-linked explanation.
Its public label is `SOURCE_LINKED_EXPLANATION`, not structured support. It
must not create supported Tier A/B public claims.

## Compiler

One publication compiler is the only path that may construct
`STRUCTURED_REVIEWED` or `OFFICIAL_LIVE_TYPED` blocks. It:

1. Loads approved typed records.
2. Binds each record to exact source revision and source span.
3. Validates review status.
4. Renders approved surface text or a deterministic live template.
5. Emits the public block and its Proof Card from that object.
6. Returns a typed failure when any invariant fails.

Canonicalization means: approved claim selected, then approved text
compiled. It does not mean: generated text accepted first, optionally
replaced afterward.

## Mixed composition

Mixed answers are concatenated immutable sections:

```text
typed live blocks
+ structured static blocks
+ labelled Tier C explanation
+ unknowns
```

The connective model cannot rewrite compiled Tier A/B text.

## Consequences

- Unreviewed or source-mismatched inventory records cannot publish as
  structured support. Quote-only / partial / handoff remain available.
- Usefulness for uncovered high-risk spans is official wording, not
  FireLens paraphrase.
- Hard-probe and ClaimBench catalogs stay frozen. The hard-probe evaluator
  still reads `evidence_status`; publication kind is additive.
- Paid H4 stays blocked until an independent examiner passes this
  architecture.
