# Appendix — Data Contracts

Strict Pydantic models reject extra fields unless explicitly stated. This appendix names the semantic contracts; executable field definitions remain authoritative.

| Contract | Owner | Key contents | Required invariants |
| --- | --- | --- | --- |
| `QueryRequest` | [`contracts.py`](../../../src/firelens/contracts.py) | question, six-turn history, coarse location, map context | normalized bounded text; no exact-address location |
| Typed request intent | [`answering/intent_automaton_types.py`](../../../src/firelens/answering/intent_automaton_types.py) | clauses, temporal/live/static/location features | deterministic projection only; no tool authority |
| `AgentQueryPlan` | [`agent/query_plan.py`](../../../src/firelens/agent/query_plan.py) | route, mode, layers, geography, exact calls/subrequest, boundaries | live/mixed has layers; mixed has static subrequest; terminal has response; exact authorization |
| `LiveResult` | [`live_contracts.py`](../../../src/firelens/live_contracts.py) | ID/kind/authority/source/times/freshness/status/geometry/optional size/distance | nonnegative size/distance; timezone-aware; basis/geometry/derivation agree |
| `LiveLayerStatus` | same | kind/source/availability/times/freshness/count | available requires observation; unavailable carries no observation/results |
| `LiveMapResponse` | same | results, aggregate freshness, unavailable layers, layer statuses, limitations | status kinds unique; counts and unavailable list equal results/status |
| `NearMeResponse` | same | location/viewport/results/pagination/layers/fallbacks | pagination, requested order, result counts, freshness agree |
| `QueryPlan` | [`contracts.py`](../../../src/firelens/contracts.py) | normalized static plan, retrieval requests, required aspects | tangent cannot retrieve; related planning must retrieve |
| `RetrievalBundle` | same | BM25/vector/fused/reranked hits, errors, timings, usage, attempts, models | represents incomplete stages explicitly |
| `EvidencePacket` | same | question/corpus/items/quotes/conflicts/limitations | packet IDs, quote candidates, and chunks remain internally bound |
| `PublicClaim` | same | claim text, evidence status, supports, trust, publication | reviewed claim needs publication + support; background cannot cite corpus |
| `PublicationAuthority` | [`publication_contracts.py`](../../../src/firelens/publication_contracts.py) | kind, typed IDs, review/source hashes, renderer/provenance/tier | supported kinds require their governing identity fields |
| `ValidationReport` | [`api_contracts.py`](../../../src/firelens/api_contracts.py) | accepted/schema/citation/quote/support/policy flags + errors | acceptance is a bounded validator result, not source truth |
| `AskResponse` | [`contracts.py`](../../../src/firelens/contracts.py) | status/mode/answer/sections/history/claims/evidence/live/limitations/identity/proof | mode-specific invariants plus publication/current-record/proof/roster binding |
| `ProofCard` | [`proof_contracts.py`](../../../src/firelens/proof_contracts.py) | claim/support/authority/source/review/freshness/truth/publication/derivation | profile follows support state; verified metadata complete; derivation exact |
| `OperationalEvent` | [`operational_logging.py`](../../../src/firelens/operational_logging.py) | categorical identity, counts, latency, stages, tokens/cost | content-free allowlist; no raw question/answer/history/location/evidence |

## Live derivation constants

Published distances use CRS `EPSG:4326`, coordinate order `longitude_latitude`, unit `km`, and the recorded algorithm `pyproj.Geod.inv WGS84 after shapely nearest_points`. A distance claim without matching result ID, place input, freshness, basis, and derivation cannot receive verified derivation state.

## Availability truth table

| State | Results allowed | Observation metadata | Meaning |
| --- | --- | --- | --- |
| Available, count > 0 | yes | required | Source was observed and matching strict records were returned |
| Available, count = 0 | none | required | Successful observation returned no matching strict records; not a safety conclusion |
| Unavailable | none for that layer | forbidden | FireLens could not establish the layer; not zero |
| Stale available | yes | required and stale | Cached observation after refresh failure; not current |

