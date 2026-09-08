# Evacuation partial coverage repair — 2026-09-08 UTC

The official evacuation API was reachable. FireLens rejected an entire nearby
layer when an otherwise relevant row contained invalid geometry, and applied
order/alert selection too late. The retained source snapshot contains two invalid
native polygons, both alerts; exported GeoJSON has additional topology failures.
Counts, IDs and native pagination were checked against the existing official API.

The existing quarantine mechanism now preserves usable records in nearby queries.
Known excluded statuses are filtered before geometry admission; unknown statuses
remain unresolved omissions. Zero validated matches can coexist with partial
coverage. Partial state survives concurrent prefetch, evidence, composition,
publication and the interface. Individual supported spatial relationships remain
usable, but complete totals, global nearest rankings and negative containment
conclusions are withheld. Retrieval timestamps and EmergencyInfoBC handoffs remain
visible. No source coordinates, parser, provider, model or index were replaced.

Independent read-only High review accepted implementation candidate
`bf3d5cc9cda53599ca84eef76d85b4a1473445c3`, tree
`1d21fcf1ac201664bfe0ca55e6472c0785a0cb9d`, closing six findings across bounded
successors. The accepted review ran 64 tests, seven subtests and 32 probes.
The unchanged real corpus/index contains 178 chunks and 178 by 1536 embeddings.
Historical rc2.2 remains 96/105, including its frozen J01 failure; rc2.3 retains
97/105 and the separately accepted J01 behavior. Nine failed-row evidence hashes
change only for additive empty `partial_layers` fields. Fifteen runtime material
bindings and their consuming policy digest are rebound after acceptance; frozen
expectations and disposition classifications remain unchanged.

Real-source local browser journeys exercise Kamloops, Lillooet, Victoria and
province-wide requests at desktop, mobile and 320 pixels, including official-link
activation and accessibility. Local results are engineering evidence. Final exact
candidate verification, maintained CI, preview and production identity and browser
checks remain required for release qualification. Invalid upstream boundaries
remain explicitly partial; this repair cannot establish complete coverage for them.

Retained evidence: `firelens-partial-coverage-repair` beside the release checkout.
Independent review reports are individually sealed. Rollback baseline: main
`76635c8b36e905241271137891c886745bd303d0`, tree
`d2e5c1a1ca8aa29d454a35d248c92a75612835d4`, Vercel
`dpl_HMkQ36hDFDP9Hunv3BFZhcbfc9ho`. Deployment is authorized by Thomas's request
to repair, verify through the actual application, update main and deploy.
