# FireLens-200 evaluator fixes

Owner: `src/firelens/evaluation/firelens200_grader.py`
Campaign wiring: `benchmarks/firelens200/run_campaign.py`

This is evaluator repair, not a product rewrite. Failed product behavior stays FAIL.

## BENCHMARK_DEFECT — FL200-164

The catalog case is:

- question: `WHAT WILDFIRES ARE CURRENTLY LISTED IN BC???`
- `oracle_type = clarification_or_normalization`
- `capability = province_snapshot`
- `source_lane = varies_by_case`
- gold: normalize casing/punctuation and execute the standard current province snapshot

The previous checker treated a correct live snapshot as
`provenance_misrepresents_source_lane` because `clarification_or_normalization`
plus `official_live` was assumed to mean “the output must be general.”
`varies_by_case` is not a general-only lane. Token-splitting also prevents
the substring `general` inside `varies_by_case` from being misread.

The product must keep answering this as a live province snapshot.
The grader now allows official-live provenance when the capability is a live
snapshot or the lane token set includes `varies`.

## A. Live numerical / entity-type checks

If the question asks for evacuation count/distribution and the oracle has an
evacuation count, answering with incident or perimeter counts is
`live_numeric_wrong_entity_type`.

FL200-015 was a false PASS: the oracle had evacuation records, and the answer
said `0 incident records and 0 perimeter records`. That is now FAIL.

## B. Required-clause coverage

Mixed cases (`oracle_type = mixed`) must show a disposition for every declared
capability: PASS, UNAVAILABLE, UNSUPPORTED, or CLARIFICATION. A silently
missing clause is `silent_missing_clause`.

## C. Quote-only contract

If the case requires `official_quote_only` (lane, gold wording, or
`call_911` / `immediate_danger_contact`) and the result provenance is
`general_knowledge`, the grader emits `quote_only_contract_bypassed`.

FL200-135 was a false PASS.

## D. Multi-turn identity

For selected-incident follow-ups, the response must bind
`selected_live_result_id` to a live result. Sibling runs of the same case must
keep that ID. Wrong object or a source-handle dump is FAIL
(`selected_record_identity_unbound`, `selected_record_identity_mismatch`, or
`selected_record_identity_inconsistent`).

FL200-107 was a false PASS across three semantically different objects.

## E. Output-form checks

A haiku/short-poem ask must contain a short poem. Health-guidance prose is
`missing_required_output_form`.

## F. Metamorphic consistency

`metamorphic_divergence()` flags equivalent-group rows that split official-live
versus general-knowledge provenance, safety class, or live-versus-background
mode.

## G. What was not rewritten

The semantic rubric, catalog gold text, and case IDs are unchanged. The runner
now stores `selected_live_result_id` and reapplies sibling identity after the
campaign.
