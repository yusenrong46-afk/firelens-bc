# ADR 0018: Typed deterministic intent automaton

Status: accepted
Date: 2026-08-26

## Context

ADR 0017 made `AgentQueryPlan` the sole authorization for tools, layers,
geography, and reviewed-guidance subrequests. The *shape* of the user request
that feeds that plan was still assembled from overlapping phrase lists:
`request_grammar.py`, leftover live-pattern tables, geography-analysis regexes,
and independent location/national extractors. Those lists drifted. A current
cue plus `will`, a country qualifier after a BC place, or the word `national`
inside `National Park` could authorize the wrong lane.

Publication authority, privacy, and zero-cost behaviour must not depend on
which consumer happened to re-parse the question.

## Decision

One typed deterministic automaton owns request shape before policy and
retrieval. `parse_request_intent` in `src/firelens/answering/intent_automaton.py`
is the production owner for:

- clause boundaries;
- temporal scope (current, noncurrent, unspecified);
- live-record operations and official layers;
- explicit non-BC national scope;
- reviewed-guidance signals;
- raw location *candidates* (not gazetteer resolution).

`request_grammar.py` is a compatibility projection of that parse. Downstream
modules (`plan_query`, `live_layers_for_question`, `plan_agent_request`,
`coarse_location_from_question`, mixed-lane static fragments) project typed
fields. They may validate or geocode a candidate, apply a selected-record or
empty-map *policy* overlay, or refuse an out-of-province label. They must not
independently re-interpret the question with a second phrase grammar.

The automaton does not grant publication authority, fetch evidence, call a
provider, or decide that a place is a BC community.

## Consequences

- Live vs reviewed vs national vs historical decisions are inspectable from one
  frozen parse.
- Compatibility dataclasses and public Ask fields stay stable.
- Residual regex in safety, selected-record, and gazetteer modules remains
  local to those policies; it is not a second request parser.
- Household-prep tokens (`has_prefetchable_guidance`) authorize static
  prefetch without classifying the clause as reviewed guidance. That keeps
  planner/multi-query behaviour for packing questions while blocking live
  place-correction from treating "what should I pack" as a community.
- Colon-fronted discourse labels (`Harder:`, `Please:`) are a prefix class,
  not geography. Named-place extractors run before fronted scope, and
  existential "is there a <place> order" is a live-clause form.
- The web workspace still classifies map vs evidence vs analytical layout from
  the raw question in `apps/web/src/app/workspacePresentation.ts`. That regex
  is presentation-only: it does not authorize tools, layers, or geography, and
  it is not a second request parser. Map-first layout is limited to questions
  that explicitly contain `map`/`mapped`; geographic-analysis wording uses the
  analytical workspace over the evidence surface rather than opening the map
  first.

## Does not change

Public API fields, support kinds, corpus or typed-claim inventory, human review
decisions, sealed labels, or provider/paid evaluation.
