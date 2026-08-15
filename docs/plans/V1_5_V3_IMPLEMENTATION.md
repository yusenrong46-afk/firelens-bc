# FireLens BC V1.5 V3 implementation contract

## Product outcome

V1.5 V3 is one map-first wildfire agent. The provincial map is available without
location permission. Conversation, selected incident, visible official records,
and map viewport remain one task context. The existing reviewed-corpus and
official-live-data validators remain authoritative.

## Frozen behavior acceptance

1. Safe questions never end in a generic scope rejection. They receive reviewed
   guidance when supported or visibly labelled general background otherwise.
2. Current incident, perimeter, and evacuation facts come only from existing
   official live adapters. Missing or unavailable records are never called safe.
3. A selected live-result identifier is treated only as a lookup key. The server
   re-resolves it from the current official response before answering.
4. Province-wide records load without a location request.
5. Distance questions without an origin preserve the question and selected fire
   while requesting either a community or an approximate location.
6. Distance is WGS84 geodesic distance to an incident point or nearest perimeter
   boundary. It is never described as driving distance or a safety assessment,
   and an unmatched selected record never falls back to a different fire.
7. Browser and server round coordinates to two decimal places and do not persist
   question content, answer content, or precise location in production telemetry.
8. The application owns tool schemas, dispatch, source authority, limits, and
   validation. The language model cannot execute arbitrary tools or select a
   different provider.
9. Production requires OpenRouter ZDR for embedding and generation. Reranking may
   operate under the approved non-ZDR exception. Provider fallback remains disabled
   and every OpenRouter request sends `data_collection=deny`.
10. Existing public clients remain compatible; all new request fields are optional.

## Development regression boundary

The frozen `product_question_probe.v1.json` remains unchanged and is not a sealed
qualification artifact. V3 development regressions are kept in a separate case
family for `my place`, named evacuation, perimeter, telegraphic live asks, and
correction/source-context follow-ups. Their evaluator checks typed response
capabilities—such as coarse `resolved_location`, `required_input`, live-result
`kind`, claims/evidence, and related links where applicable—and requires both
halves of a mixed response. Structural checks are engineering evidence only;
they cannot prove semantic entailment, answer completeness, or human usability.

## Initial V3 tool surface

- `list_active_fires`
- `get_fire_details`
- `get_evacuation_information`
- `calculate_fire_distance`
- `search_reviewed_guidance`
- `answer_general_background`

## Production ZDR compatibility gate

The three OpenRouter stage models are explicit environment configuration:
`FIRELENS_EMBEDDING_MODEL`, `FIRELENS_RERANK_MODEL`, and
`FIRELENS_GENERATION_MODEL`. Privacy is stage-specific:

- embedding ZDR: required
- generation ZDR (planning, grounded, repair, background): required
- reranking ZDR: optional for the retrieval-qualified `cohere/rerank-4-pro`
- every request: `data_collection=deny`, `allow_fallbacks=false`, `require_parameters=true`

`data_collection=deny` is provider data-policy filtering. It is not ZDR. Production
startup checks the authenticated `GET /api/v1/endpoints/zdr` roster once and fails
closed if the embedding or generation model is missing. A missing ZDR endpoint for
the reranker does not prevent startup under this approved policy. A reranker marked
`required` would still fail closed if missing.

On 2026-08-13 and 2026-08-15, the roster included the default embedding model and
`openai/gpt-5.6-luna`, but not `cohere/rerank-4-pro`. Those observations remain
historical evidence collected under the previous all-model ZDR gate. A ZDR listing
alone does not promote a reranker. The staged candidate schema is
`firelens.runtime_candidate.v3` and binds data-collection policy, fallback policy,
stage ZDR requirements, model IDs, commit, release, corpus, embedding, and
retrieval-text strategy. A v2 all-ZDR candidate must not be interpreted as this
policy. Local processes may run with a mismatched candidate and must not be treated
as production-qualified artifacts.

## Release evidence boundary

Automated checks, local browser verification, and provider smokes are engineering
evidence. They are not independent human review, deployed-production evidence, or
a guarantee that unsupported claims are impossible outside the qualified cases.
