# 08 — Publication and Verification

Publication is an application contract, not a confidence score from the model.

## Authority kinds

[`publication_contracts.py`](../../src/firelens/publication_contracts.py) defines:

- `structured_reviewed`: canonical text from a human-reviewed typed claim, bound to source revision/span and renderer;
- `official_live_typed`: deterministic text bound to one exact live result;
- `official_quote_only`: exact admitted official-corpus wording, labelled extraction-only;
- `source_linked_explanation`: lower authority; never promoted to reviewed fact by presentation;
- `general_background`: explicitly unreviewed model background;
- `unsupported`: no claim of evidentiary support.

## Owners and flow

| Stage | Owner | Input → output | Failure behavior |
| --- | --- | --- | --- |
| Compile high-risk | [`publication/compiler.py`](../../src/firelens/publication/compiler.py) | identifier-only plan + reviewed inventory/packet → canonical claims | unknown/unreviewed/unbound IDs are rejected or handed off |
| Validate compiled claims | [`publication/compiled_validation.py`](../../src/firelens/publication/compiled_validation.py) | claims + packet/current inventory → `ValidationReport` | fail-closed official-source handoff |
| Bind public claims | [`publication_response_binding.py`](../../src/firelens/publication_response_binding.py) | `AskResponse` claims/evidence/live results → error or acceptance | response construction fails on mismatched authority |
| Compose sections | [`contract_composition.py`](../../src/firelens/contract_composition.py) | authority-labelled sections → canonical answer | non-canonical live/mixed top-level prose rejected |
| Project proof | [`proof_presentation.py`](../../src/firelens/proof_presentation.py) | accepted claims/results → status banner/proof cards | stale or contradictory strengthening is rebuilt or rejected |

`AskResponse.validate_public_state()` is the final in-process master check. It validates response-mode semantics, evidence uniqueness, publication binding, live/current-record wording, result identity, proof presentation, sample membership, and roster consistency.

## Deterministic authority boundary

The model may propose a lower-risk draft whose quote IDs are checked against the packet. It does not supply `PublicationAuthority`, trust/freshness state, typed IDs, official result values, or proof metadata. Tier A/B generated claims that lack deterministic authority are removed or replaced by exact-source/handoff behavior.

A significance answer needs an explicit rationale in the same topic-matched
admitted quote. Inventory membership alone does not establish that rationale.
The existing compiler still decides publication, with action-only typed claims
excluded from replacing an explanation. A reviewed rationale gap remains a
terminal evidence limitation without model generation. Mixed supported guidance
retains its trust lane beside a separate personal-decision boundary.

## Known ownership wrinkle

`compiler.py` describes itself as the constructor for official live publication, while runtime live construction also uses internal helpers in [`_publication_authority.py`](../../src/firelens/_publication_authority.py); `compile_live_fact()` is mainly test-facing. Treat the response-binding validators as the decisive boundary and consolidate constructor ownership before extending live publication.

## What “verified” does not mean

An accepted deterministic contract proves structural and bounded semantic properties implemented by those validators. It does not prove that an upstream source is correct, that retrieval found all relevant guidance, that a lower-risk paraphrase is universally entailed, or that the current application is release-qualified.

