# Live geometry repair — 2026-09-07

## Scope and authority

Thomas explicitly approved native ArcGIS decoding, record-level quarantine,
normal main/PR update and Vercel deployment on September 7. This is a bounded
successor to deployed `7474dc16acc8680d1b230b0792d59e0f26b1ae17` (rollback target
`dpl_6eRhLHy2tZ8aY9npcRGLxShJ5y9F`), not a new source or provider.

## Reproduced failure and correction

The official GeoJSON export classified interior perimeter rings as independent
shells. Captured perimeter V10755 failed with nested shells; native ring decoding
preserves the two holes and passes the unchanged geometry validator. Captured
native evacuation records also include two self-intersecting polygons; those
are not repaired or rendered. Four retained official records in
`tests/fixtures/arcgis/` provide dated source regression fixtures, not live data.

Native perimeter/evacuation JSON from the same allowlisted sources is converted
using documented exterior/interior winding and containment, preserving every
coordinate. Only the map route retains valid records alongside geometry
omissions. Its response and UI explicitly mark partial layers, usable returned
counts and omitted counts. Strict chat, nearby and summary paths still withhold
incomplete layers. No model calls, dependency changes, source-admission changes,
index rebuild or evaluator-policy migration are part of this repair.

## Qualification state

Initial live engineering check returned 131 incidents, 85 perimeters and 30
usable evacuation records, with two evacuation geometry omissions. The strict
path retained the first two layers and withheld evacuation results. This is a
dated local live-source observation, not yet a production-release claim.

Focused source/geometry/API/nearby regressions passed (109 tests, 74 subtests).
The independent High review checked the native ring conversion against an
independent even-odd fill oracle and confirmed exact coordinate preservation.
All nine historical hard-probe semantic projections remain unchanged (96/105
in frozen rc2.2). Its reviewed runtime binding is refreshed for only the three
changed backend files and the new decoder; the policy's binding digest follows
that record. No evaluator semantics, thresholds or frozen answers change.
The summary wording says a complete evacuation *total* is unavailable, avoiding
confusion with the usable subset on the map. Frontend unit tests: 204 passed.
Full verification, CI and deployment verification remain required before
production qualification is declared.

Private raw source captures and candidate map/strict responses are retained in
`/Users/thomas/Documents/Codex/2026-09-06/firelens-geometry-investigation`.
The committed fixtures are extracted exact native records from those captures.
Future counts may change. Partial coverage is not an all-clear.
