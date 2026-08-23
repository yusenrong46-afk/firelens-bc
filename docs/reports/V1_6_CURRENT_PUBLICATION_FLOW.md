# V1.6 current publication flow (starting candidate)

Inspected on `8b2da4ce8e334fcc53f053cbefb9e01e3caf17b2` /
`0e885a652e20d89ae54bb83d90bd41720149fd74` before any structured-publication
implementation. Labels: **INSPECTED** unless marked otherwise.

This map is the Stage 1 gate. It is not a claim that the new architecture
exists.

## Examiner finding

**Confirmed.** Typed inventory is optional post-validation canonicalization,
not a mandatory publication gate.

Evidence (INSPECTED):

1. `GroundedAnswerEngine` accepts a `GroundedDraft` whose claims carry
   free-form `text` plus quote IDs.
2. `validate_draft` decides acceptance from lexical/typed-snapshot checks.
3. On accept, every claim is published as `EvidenceStatus.VERIFIED_CORPUS`.
4. `canonicalize_claim_text` then *optionally* replaces that already-accepted
   text if a typed record matches the quote. If no record matches, the
   generated sentence remains `VERIFIED_CORPUS`.
5. Proof Cards set `support_state=supported` when `claim.supports` is
   non-empty and validation was accepted. They do not require a typed claim
   ID.
6. Live, background, conflict, and mixed live-half paths never call
   `load_inventory` / `match_quote`.

## Request-to-UI path

```text
HTTP Ask
  → agent coordinator / StaticAnswerService
      → answering.service.AskService
          → plan, retrieve, EvidencePacket
          → GroundedAnswerEngine.answer  OR  background  OR  conflict
      → AgentPacket.static_response
  → agent.loop (optional outer chat_turn / rewrite)
  → compose_response
  → AskResponse validator → attach_proof_presentation
  → frontend StatusBanner / Proof Cards / support checklist
```

## Every entry point for generated prose

| Entry | Module | What the model may write | Becomes public? |
| --- | --- | --- | --- |
| Grounded draft | `answering/generate.py` `GroundedDraft` / `DraftProposalClaim.text` | Free-form factual sentences + quote IDs | Yes, if `validate_draft` accepts |
| Grounded repair | `grounded.py` repair pass | Replacement free-form claims | Yes, if repair validates |
| Background draft | `generate.py` `BackgroundDraft` | Up to 3 explanatory claims | Yes, as `GENERAL_BACKGROUND` |
| Outer write | `agent/loop.py` `_provider_loop` | Full answer string from `official_packet` | Yes, as live/mixed `answer` and `CURRENT_RECORDS` |
| Outer rewrite | `agent/loop.py` `_rewrite` | Rewritten full answer | Yes, unless rails fall back |
| Offline fallback | `agent/loop.py` `fallback_write` | Deterministic templates | Yes |
| Conflict templates | `answering/responses.py` `conflict_response` | Deterministic “contains one of the conflicting requirements” | Yes, as `VERIFIED_CORPUS` |
| Quote salvage | `validate.py` `salvage_valid_grounded_claims` | Subset of already-generated claims | Yes, as partial grounded |
| Frontend fallback | `apps/web/.../proofPresentation.ts` | None; recomputes trust from citations | Can strengthen display |

The high-risk generation schema **contains** `claim_text` (field name `text`
on `DraftProposalClaim`). There is no identifier-only plan type.

## Every point support status is assigned

| Assignment | Location | Rule |
| --- | --- | --- |
| `EvidenceStatus.VERIFIED_CORPUS` | `grounded.py` after validate/canonicalize | Any accepted generated claim with supports |
| `EvidenceStatus.VERIFIED_CORPUS` | `responses.py` `conflict_response` | Template claim + exact quote |
| `EvidenceStatus.GENERAL_BACKGROUND` | `service.py` `_background_answer` | Background draft |
| `ClaimTrust` | `claim_trust.corpus_claim_trust` | Stamped on grounded claims from cited span review provenance |
| Proof Card `support_state` | `proof_presentation._support_state` | `supported` if `claim.supports` and validation accepted; `background` if `general_background`; `conflict` if mode is conflict; `unknown` if validation/critical fields failed |
| `supported_items` | `proof_presentation.build_supported_items` | Every `verified_corpus` claim or any claim with supports, plus live result names |
| Frontend fallback | `proofPresentation.ts` `getProofCards` / `getSupportChecklist` | Same citation heuristic if backend cards are absent |
| Rails | `agent/rails.py` | Can reject outer answer (`typed_claim_mutation`) but cannot create structured support |

`VERIFIED_CORPUS` is the unqualified public “supported” signal for static
claims. There is no `STRUCTURED_REVIEWED`, `OFFICIAL_LIVE_TYPED`, or
`OFFICIAL_QUOTE_ONLY` state.

## Every typed-inventory lookup

| Call | Location | Effect |
| --- | --- | --- |
| `match_quote(quote_text)` | `grounded.py` publish loop | Feeds `canonicalize_claim_text` only |
| `records_for_span` / `load_inventory` | tests and residual gates | Not a publication constructor |
| `render_typed_claim` | `claim_render.py` | Returns `canonical_text` if `production_supported()` |
| `canonicalize_claim_text` | `claim_render.py` | If generated text already matches the quote snapshot, keep generated text. Else, if a record exists and the generated snapshot is high-risk, replace. If no record, return generated text. |
| `typed_preservation_errors` | `validate.py`, `rails.py` | Residual checker / rail. Rejection-capable. Cannot authorize publication. |

Inventory file: `data/typed_claims/high_risk_v1.yaml` (6 records,
`human_review_state: approved_static`). `TypedClaimRecord.production_supported()`
requires Tier A/B and `approved_static` or `human_verified_repair`.

There is no path that says: “no reviewed typed claim ⇒ cannot be
`VERIFIED_CORPUS`.”

## Every path that bypasses typed claims

1. **Accepted generated grounded claim** with no inventory match.
2. **Accepted generated grounded claim** whose snapshot already compares
   equal to the quote (canonicalization no-ops).
3. **Salvage** of independently valid generated claims.
4. **Conflict** template claims.
5. **Background** generated explanation.
6. **Live** `AskResponse.answer` written by the outer model from
   `live_record_fact` fields (status, freshness, timestamps, distance).
7. **Mixed** `CURRENT_RECORDS` section = outer model string; static claims
   are copied through but were themselves produced by path 1.
8. **Frontend** inferring `supported` from citation presence.

## Proof Card trust derivation

`AskResponse` validation always calls `attach_proof_presentation`.

`_claim_card` copies `claim.claim_id`, `claim.text`, and derives
`support_state` from citations/validation — not from a compiled block ID,
source-revision hash, renderer ID, or review state of a typed record.

`source_revision` on the card is `evidence.locator`, not
`source_revision_sha256` / `source_span_sha256`.

Frontend `getProofCards` prefers backend cards. If cards are missing it
recomputes `supported` from `supports.length`. That can strengthen quote-only
or generated content.

## Mixed / live / static composition

| Path | Composer | Factual text owner |
| --- | --- | --- |
| Pure static accepted | `loop.py` skips outer write; returns `static.answer` | Grounded engine (generated + optional canonicalize) |
| Mixed live+static | `compose.py` `_build_ask_response` | Outer `answer` for records; `render_claim_texts(static.claims)` for guidance |
| Live only | `compose.py` | Outer `answer` + `LiveResult` rows |
| Static + official handoff | `live_composition.supported_static_when_live_missing` | Static claims + deterministic handoff |
| Rewrite | `loop.py` `_rewrite` | Model may rewrite the **entire** previous answer, including static claim sentences. Rails may reject `typed_claim_mutation` after the fact. |
| Quoted-guidance rescue | `compose.quoted_guidance_response` | Reuses already-published static claims when rails trip |

`live_record_fact` already separates `retrieved_at` from `source_updated_at`.
The outer model still emits the public live sentence.

## Review infrastructure (present, unused as publication authority)

- `src/firelens/review_workspace/` — durable human-review sessions.
- `src/firelens/owner_review.py` — hash-bound owner semantic review of
  conversation-benchmark reports, not typed-claim approval.
- No review queue for pending typed-claim candidates.
- Coding-agent approval of inventory records is possible today because
  YAML `human_review_state: approved_static` is load-time trusted.

## Architectural conclusion

The starting candidate improved residual checking and added six reviewed
surfaces. Publication authority remains:

```text
model sentence + quote ID → validate_draft → VERIFIED_CORPUS → Proof Card supported
```

Typed inventory is a post-hoc rewriter, not the constructor of supported
Tier A/B public claims.
