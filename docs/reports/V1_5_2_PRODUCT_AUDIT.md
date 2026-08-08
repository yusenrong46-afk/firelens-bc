# FireLens BC V1.5-2 product and accessibility audit

Status: diagnostic current-checkout audit; not release qualification

Captured: 2026-08-06 (America/Vancouver)

Surface artifact: `output/benchmark/frontend_surface_probe/report.json`

Protocol: `data/evaluation/frontend_surface.v1.yaml` (provisional; not frozen)

## Audit scope

The current built React/Vite experience was captured across ten safety/product states at mobile,
tablet, and desktop sizes: idle, grounded, partial, abstention, provider failure, live, mixed,
stale, no result, and partial layer. The primary user goals were:

1. ask a preparedness question and inspect exact support; and
2. find current wildfire records, understand freshness/coverage, and reach an official source.

The automated pass also exercised three keyboard/privacy/history journeys and two frozen lab
performance profiles. This report combines those current-run artifacts with inspection of the
accepted screenshots. It does not claim full WCAG conformance or human usability evidence.

## Overall verdict

The product has a strong trust model but a weak interaction hierarchy. Grounded evidence,
abstention, stale data, partial data, and provider failure are all visible and honest. The same
safety information is often repeated in multiple large regions, however, and the single chat shell
buries the separate Near Me task. The typography is too small, many controls are too small or
browser-like, and the mobile experience becomes a long document rather than a focused task.

The visual redesign should preserve the explicit evidence and freshness language while replacing
the card stack with an open conversation canvas, anchored evidence rail, and a dedicated map/list
workspace.

## Captured flow

| Step | What was inspected | Health | Evidence-backed finding |
| ---: | --- | --- | --- |
| 1 | Idle entry and task discovery | Needs improvement | The safety boundary is clear, but Ask and Near Me share one composer and the location action is visually secondary. The desktop canvas leaves a large inactive region while the left rail carries most actions. |
| 2 | Grounded answer and exact source inspection | Mixed/healthy | Claim-to-source traceability is the strongest current surface. The selected claim, publisher, locator, exact passage, and official link are visible, but the dense framed panels and 8--11 px metadata make inspection feel like a document viewer. |
| 3 | Fresh Near Me map and record list | Failing | The map is visible, but the browser contacts third-party OSM tile hosts and the accessible list renders only records 1--8 from a ten-record response while all ten markers exist. Map/list parity therefore fails. |
| 4 | Stale and partial-layer live data | Mixed | Stale/partial warnings are explicit and retain official-source escalation. They are repeated around a large map and list, which increases scanning cost and can obscure the primary next action. |
| 5 | Abstention and no-result states | Needs improvement | FireLens fails closed and says that no result is not a safety determination. On mobile, similar explanation appears in both the conversation and the lower detail region, producing a long two-screen response. Internal-looking reason codes need plain-language presentation. |
| 6 | Provider failure and retry | Needs improvement | The retry is actionable and no fallback answer is invented. The same failure is then restated in a large lower panel, creating excess whitespace and repetition on mobile. |
| 7 | Mobile/tablet responsive layout | Failing | No horizontal overflow was detected, but the compressed desktop structure becomes a long stacked page. Near Me needs a full-map view plus accessible bottom sheet/list instead of map-after-chat. |
| 8 | Keyboard/privacy/history journeys and lab performance | Healthy wiring; incomplete UX proof | All three scripted journeys and both performance profiles passed. Scripted journeys do not establish screen-reader quality, target usability, comprehension, or real task completion. |

## Initial measurements

- 30/30 state/viewport rows completed with zero structural, stylesheet-load, horizontal-overflow,
  clipping, page-error, or unexpected-console failures.
- 0/30 rows qualified under the provisional surface gates.
- 27/30 rows contain an automated serious color-contrast finding.
- 30/30 rows fail at least one text-size, target-size, or styled-control rule.
- The live ten-record fixture renders ten map markers but only eight accessible list records; all
  three live viewports fail exact parity.
- The matrix observed 200 direct third-party tile requests. The target is zero browser-to-tile-host
  requests through a same-origin cached path or a local tile-free basemap with attribution intact.
- Forty-five OSM tile requests aborted during Leaflet refits; they remain runtime failures and were
  not hidden by an allowlist.
- All three functional journeys passed.
- The frozen 1-warmup + 7-cold-sample profiles passed: worst observed LCP p75 was 828 ms, CLS p75
  0.01692, interaction proxy p75 30.6 ms, and map-ready p75 829.9 ms. These are lab observations on
  the recorded Apple M5/Chromium environment, not field Core Web Vitals.

## Accessibility foundation follow-up — 2026-08-08

A fresh capture after the typography, focus, control-target, link, and accessible-roster fixes
completed the same 30 state/viewport rows. It qualified 18/30 rather than 0/30. Across all rows it
found zero axe WCAG A/AA violations, zero undersized text elements, zero undersized interactive
elements, and zero map/list parity failures. The ten-record fixture now exposes all ten records in
both the map and accessible list.

The remaining 12 failed rows are exactly the map-bearing states. They still made 200 direct OSM
tile requests; five rows also retained 40 aborted tile requests. This remains a privacy and
reliability blocker. The [OSM Tile Usage Policy](https://operations.osmfoundation.org/policies/tiles/)
discourages casual caching proxies and requires a clear contactable User-Agent plus cache-header or
seven-day retention compliance, so FireLens must choose and govern a map provider/cache rather than
hide the defect behind an ad hoc proxy.

Both functional journeys passed. Two performance samples were structurally invalid, so this
follow-up makes no performance claim and does not replace the earlier valid lab-performance
diagnostic. The protocol is still provisional and no human accessibility, safety, or UX result is
implied.

## Local-vector map follow-up — 2026-08-08

The direct tile-host blocker is now removed. The runtime no longer loads OpenStreetMap tiles or
contacts another basemap host. It renders incident/perimeter/evacuation geometry over a locally
bundled, topology-preserving simplification of the official Government of British Columbia ABMS
provincial boundary, identifies the source and Open Government Licence – BC beside the map, and
keeps the detailed official BCWS map as the escalation path. The source boundary was retrieved once
at implementation time in EPSG:4326 and simplified at a 0.01-degree tolerance; it is orientation
context, not a navigation or legal-boundary product.

The final diagnostic completed all 30 state/viewport rows and passed all 30 automated surface rows,
all functional journeys, and both lab-performance profiles. It observed zero direct third-party
tile requests, zero axe A/AA findings, zero undersized text or targets, and zero map/list parity
failures. The protocol remains provisional, so this closes the diagnosed browser-to-tile-host
privacy/reliability defect but does not establish WCAG conformance, human product safety, or a
frozen before/after UX result.

## Highest-impact changes

1. Put **Ask** and **Wildfires near me** at the top level. Near Me should start with community or
   explicitly consented coarse location, then move directly into map/list results.
2. Make the Near Me roster complete or explicitly paginated; map, list, chat, and API IDs must
   remain identical.
3. Preserve the implemented local-vector map boundary and source/licence disclosure; do not
   reintroduce direct browser tile-host calls without a governed provider contract.
4. Raise body/metadata type and target sizes, fix contrast, add visible focus, stop the spinner
   under reduced motion, and complete manual keyboard/VoiceOver/zoom/reflow/live-region testing.
5. Replace repeated cards with whitespace, type, dividers, a selected-evidence rail, lightweight
   status bands, and progressive disclosure. Safety state must remain explicit, not decorative.
6. On mobile, use task tabs and a full-screen map with an accessible bottom sheet/list. Collapse
   duplicate failure/explanation regions into one primary recovery surface.

## Evidence limits

- The protocol remains provisional, so this is a diagnostic baseline rather than the frozen
  before score.
- Automated axe and DOM/style checks cannot establish full WCAG 2.2 AA conformance.
- The local simplified boundary is orientation context only and is not evidence of legal-boundary,
  road, terrain, address, or navigation accuracy.
- No real participant, VoiceOver, dangerous-ambiguity, or accessibility-specialist review was run.
- The performance numbers are lab observations and require an identical environment for a valid
  paired before/after claim.

The latest machine-readable result and screenshots are saved under
`output/benchmark/frontend_surface_local_boundary_20260808_final/`.
