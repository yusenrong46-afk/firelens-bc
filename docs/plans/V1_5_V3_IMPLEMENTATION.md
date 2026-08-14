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
9. Production requires OpenRouter ZDR and provider fallback remains disabled.
10. Existing public clients remain compatible; all new request fields are optional.

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
`FIRELENS_GENERATION_MODEL`. Production startup checks every configured model
against OpenRouter's current `GET /api/v1/endpoints/zdr` roster and fails closed
if any stage is ineligible.

On 2026-08-13, the public roster included the default embedding model and
`openai/gpt-5.6-luna`, but not the currently benchmarked
`cohere/rerank-4-pro`. This observation is not a permanent model policy. A
production candidate must either qualify a ZDR-eligible reranker through the
retrieval regression suite or wait until the benchmarked reranker is eligible;
the release process must not bypass the preflight.

## Release evidence boundary

Automated checks, local browser verification, and provider smokes are engineering
evidence. They are not independent human review, deployed-production evidence, or
a guarantee that unsupported claims are impossible outside the qualified cases.
