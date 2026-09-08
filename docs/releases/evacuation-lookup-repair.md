# Evacuation lookup repair — 2026-09-08 UTC

The production Kamloops starter question reported an unreachable EmergencyInfoBC
source when the adapter had actually rejected an invalid native evacuation
polygon. The same generic wording appeared in unavailable-source answers and
frontend validation banners. Evacuation handoffs placed the BCWS map first and
incorrectly said FireLens did not track those feeds.

This repair carries `LiveLayerStatus.unavailability_reason=invalid_geometry`
through the agent's concurrent prefetch merge and deterministic composition.
Answers explain the boundary-validation failure without asserting current
network reachability, including after cached invalid data survives a failed
refresh. Other failures use load/validation language. Empty partial responses
describe absence only for successfully validated layers. EmergencyInfoBC leads
evacuation handoffs; frontend labels say current status is unconfirmed.

Strict geometry validation, record admission, unavailable-versus-empty behavior,
distance/ranking, source URLs, provider routing, and the real 178-chunk index
remain unchanged. This does not correct the issuing source's invalid polygons
or establish complete evacuation coverage. A missing polygon is not an all-clear.

Independent High review accepted implementation candidate
`50be0decd5712907c6be5ab57b2d862105d1b518`, tree
`3aa7da6ac2cd5859d88ddd0253df9283bb86f5da`, after two identified gaps were repaired.
Regressions cover full agent prefetch, direct and paginated queries, failed
refresh with cached invalid geometry, genuine connection failure, and partial
empty results. All nine frozen hard-probe projections remain unchanged:
historical rc2.2 stays 96/105, including its J01 failure. Only seven reviewed
runtime hashes and the consuming evidence digest are rebound.

The built application was exercised against real official feeds and the real
index, with desktop, mobile and 320-pixel screenshots, official-link activation,
overflow and accessibility checks. The checked questions use the deterministic
live-record path and make no model calls. Local execution is engineering
evidence; final full verification, CI, preview and production identity/browser
checks remain required for release qualification.

Retained evidence: `firelens-evacuation-lookup-repair` beside the release checkout.
The independent review reports are sealed separately from subsequent runs.
Rollback baseline: main `73bfc8777887060714f8fd8c487186d7c947ecee`, Vercel
`dpl_Cnf6aTvujWucbntX2xEe2MNyz4FD`. Deployment is authorized by Thomas's request
to fix, double-check through the application, and deploy after verification.
