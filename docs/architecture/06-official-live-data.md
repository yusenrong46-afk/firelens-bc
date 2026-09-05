# 06 — Official Live Data

FireLens supports exactly three live kinds: incident, perimeter, and fire-related evacuation. Layer definitions and official endpoints live in [`live_support.py`](../../src/firelens/live_support.py); HTTP/cache behavior and normalization are owned by [`live.py`](../../src/firelens/live.py) with helpers in [`live_http.py`](../../src/firelens/live_http.py).

## Component contract

| Item | Contract |
| --- | --- |
| Input | Plan-authorized layers plus optional bounding box, coarse location/radius, or exact selected record ID |
| Output | `LiveResult` records, ordered `LiveLayerStatus` values, unavailable layers, aggregate freshness, and limitations |
| Invariants | Official metadata and features are schema-checked; geometry uses GeoJSON/WGS84; source and retrieval time stay separate; distance is a bound deterministic derivation |
| Failure modes | HTTP/metadata/schema failure, stale-cache fallback, future source clock, malformed geometry, malformed otherwise-official row, geocoder ambiguity, missing selected record |
| Observability | Results expose layer availability/freshness/limitations; request event exposes only counts. Per-layer error class and latency are not fully represented in the Ask event. |
| Tests | `test_live.py`, `test_live_answering.py`, `test_live_qualification.py`, `test_live_slo_evidence.py`, `test_empty_live_safety.py`, `test_regional_fire_queries.py` |
| Evaluation | Live fixtures, source-failure faults, geography mutations, selected-record trajectories, authorized live qualification when separately run |

## Fetch and normalization

For each layer, `LiveDataService` concurrently obtains ArcGIS metadata, the
first GeoJSON page, and an authoritative published count, then pages within
bounded limits until the unique-record count exactly matches. It validates
required fields, every geometry ordinate (including nested/3D collections),
size, status, and source time before constructing strict `LiveResult` objects.
A malformed feature makes the affected layer unavailable; it is not treated as
outside the requested area or silently removed. Location distance uses
`pyproj.Geod.inv` over WGS84, with perimeter nearest-point handling; the
resulting `DistanceDerivation` binds algorithm, units, inputs, time, and
publication state.

The public contract distinguishes:

- **available + zero matches**: the official layer was observed successfully and no matching rows remained;
- **unavailable**: the layer could not establish an observation and cannot claim timestamps or results;
- **stale**: a cached observation may be returned after refresh failure, with an explicit limitation;
- **future-clock quarantine**: an implausibly future source timestamp cannot be classified fresh.

## Current candidate repair

**CURRENT-CANDIDATE-LOCAL:** In the base implementation, malformed rows could
be silently skipped; a nonempty short page could publish as complete; named-fire
lookup could stop before the complete roster; present-but-invalid timestamps
could fall back; closed status was not normalized; and mixed disjoint counts
could collapse through `max`. The candidate quarantines an affected layer on
any row/geometry/size/timestamp/count contract failure. It requires fetched
unique-count equality with the authoritative count, pages named-fire lookup
through the bounded roster, matches closed statuses exactly after
case/whitespace normalization, and adds disjoint fire/evacuation totals.
Healthy siblings remain usable. A genuinely empty, successfully observed layer
remains available with count zero.

The regressions in [`tests/test_live.py`](../../tests/test_live.py) cover strict
row construction, recursive geometry ordinates, invalid/negative/non-finite
size and time, authoritative-count types/equality, partial pagination,
named-fire pagination, status normalization, mixed counts, healthy siblings,
and legitimate empty observations. Those regressions are local fixture evidence. Subsequent September 5 capture/replay
qualification at `b887cb4` fetched the complete 1,365-row incident roster and
returned 135 active records. The perimeter and evacuation endpoints returned
invalid polygon topology, so their layers remained unavailable. A healthy
incident sibling and a locally filtered empty observation remained distinct.
Later bounded V8 requests on `0c6b81a` returned three valid perimeters and four
mapped evacuation Order records; independent review checked their official
identities, geometry and original modification dates. The 135 active incidents
were also independently reconciled. Those later successes do not erase the
earlier malformed captures, and neither snapshot establishes present conditions.
The first capture harness had a decoding error; corrected retained-response
replay establishes adapter behavior, not an uninterrupted online run. See the
[System Card](../system-card/FIRELENS_SYSTEM_CARD.md) for exact scope.

## Publication

Live public claim text is rendered from typed records and bound back to the exact `result_id`. Status, distance, and count language must match the returned authorized result set. The model may explain a live packet only within the composed lane; it does not own official values.
