# Pacific Operations central-page revision

The owner rejected the first local UI's visual hierarchy and asked for a substantially
closer match to the selected Pacific Operations image. This revision starts at clean
`dbe924dabf6e206a243e7c67c13f5fb4e3721bfc`, tree
`d53aac48ff55eb48dba51b9b5ac1305986dfb2c6`, on `codex/firelens-release-candidate`.
The exact final commit/tree and checks are retained in the existing campaign's
`ui-central-redesign` directory. The preceding `ui-rebuild` evidence is preserved
as history; its visual acceptance does not override the owner's rejection.

## What changed

- The answer is its own white panel. The backend's original first plain sentence
  receives the Newsreader headline treatment; remaining prose uses Inter. No facts
  are extracted, rewritten, hidden or recomputed from that prose. Linked Markdown,
  quotations and mixed-authority sections retain their existing rendering.
- The record and follow-up panel is separate. Primary and secondary records share
  one compact row component with exact identity, status, distance, size and source
  URL. No internal result ID is shown when the published name already identifies
  the row. Backend record order and sampling remain unchanged.
- Routine explanation uses a quiet disclosure; material limitations and partial
  coverage stay visible. Feedback fits alongside routine notes. All supplied
  follow-up questions remain available and fill the single header composer.
- The 210px desktop sidebar and 851px/539px result/map columns match the reference
  at 1672px. The map/source rail keeps normal page scrolling. A deliberate View map
  action scrolls to the existing rail on mobile and focuses it.
- Source publication time, FireLens fetch time, record freshness and selected
  record scope remain separate. Additional contributing URLs use a disclosure.
  No unresolved selection silently substitutes another record's source.

The selected written contract governs departures from the illustration: existing
Newsreader headline, real Leaflet/OSM attribution, no invented wildfire photographs,
counts, names, dates, weather, avatar, settings or saved/notification controls.
The complete accepted answer and source timestamps make some panels taller than
its illustrative content. No clipping or fabricated facts reduce that height.

## Verification and repairs

Product Design image-to-code/design QA compares the source and rendered candidate
in the same input at 1672x941, DPR1. Focused 850x800 central crops and the responsive
matrix supplement the whole view. The previous single-card, whole-paragraph serif
layout is removed, along with its unequal primary/secondary record styles.

Independent High review found three P2 regressions: hidden partial-roster coverage,
locale formatting that could round tiny areas, and a map action label mismatch.
They were fixed with focused coverage/precision/access-name tests. A separate
mobile check reproduced a mounted map remaining at y1543 in an 844px viewport
after View map. The explicit navigation owner now scrolls/focuses it. The existing
browser journey checks full map viewport visibility and focus at mobile/tablet sizes.

Frontend unit tests: **198 passed**. The existing built-stack suite covers 32
journeys across 1536x1024, 1440x900, 1366x768, 1024x768, 768x1024, 390x844 and
320x844, plus active empty/partial cases at 1024/1280/1440. Exact final results are
in the campaign packet. This includes selected-record/list/map/follow-up/source
coherence, Home reset, general/reviewed/mixed modes, unavailable recovery, local
lazy assets and zero axe violations in the 1536/390 selected-answer checks.
The mocked browser suite has **41 passes and one existing skip**; its 640px zoom
proxy is not a native browser-zoom assessment. Its expected unmocked background
proxy errors are not deployment network evidence.

Two UI assertions follow the authorized layout change: readable width measures
answer prose rather than the entire panel; source/update visibility checks the
separate labelled line instead of its former dot-separated sentence. No factual,
source, authority, ranking, safety, retry or frozen backend expectation changed.

| Measurement | dbe924d | Central revision |
| --- | ---: | ---: |
| CSS bytes | 81,058 | 85,347 |
| CSS source lines | 2,312 | 2,194 |
| Repeated selector occurrences, same parser including responsive rules | 122 | 136 |
| Initial JS raw bytes | 543,733 | 553,441 |
| Initial JS gzip bytes, Node gzipSync | 158,738 | 160,990 |
| Production TSX files | 36 | 36 |
| UI-added provider/retrieval calls | 0 | 0 |

JS gzip increases **1.42%**, within +5%; no new dependency. Map/charts remain lazy.
The new two-panel and shared-row structure removes obsolete owners, but this is
not a claim that CSS bytes or repeated selectors decreased. There is no measured
live-provider p50/p95 or time-to-publish comparison in this UI fixture lane.

Skills used: Product Design image-to-code/design QA, repository map/UI-audit,
fix/simplify/eval/release workflow, React review checklist. The existing Engineering
OS, Vitest and Playwright remain the verification system; no duplicate launcher.

## Original revision evidence and release boundary

The README screenshot is a local built frontend with synthetic upstream records;
map tiles are intentionally blocked in the automated matrix. The separate visual
comparison permits public OSM tile asset GETs; its incident data remains synthetic.
No normal/management credential was read and no OpenRouter, provider, qualification,
management or official-feed request was added. The original ledger and reservations
are preserved. External preflight/qualification still follows the existing protocol.

The candidate's clean `make verify` result, High recheck, exact hashes and terminal
verdict are in `ui-central-redesign`. At that revision, native 200% zoom, human
screen-reader assessment, production latency and preview checks had not run.
Later native zoom and current 37de779 preview results are recorded below;
no production action is included.
Local UI completion does not declare external qualification or release GO.

## Historical b887cb4 observation — 2026-09-05

The local revision above was subsequently frozen at application
`b887cb44a6a958bca67f77b41469ae7b608ce06f`, tree
`079a1852e1a890a763cde1956521c3c6665f8054`. Exact-commit `make verify`
passed, including 198 frontend tests, and the separate synthetic built-stack
matrix passed 32/32. Independent High recheck closed the three P2 findings and
mobile/tablet map navigation gate. The preceding not-run statements describe
the revision's original observation time, not the later campaign state.

[The historical b887cb4 preview](https://firelens-dzd57ibwa-yusenrong46-9212s-projects.vercel.app), deployment
`dpl_AWAaYmmCR1CWkiREsrb9dSKNEzcJ`, matched the exact candidate readiness.
Desktop 1672×941 and mobile 390×844 asset and UI checks used synthetic API
responses. They do not establish real-provider answers or complete preview
qualification. See the [System Card](../system-card/FIRELENS_SYSTEM_CARD.md)
for current evidence, including the later 37de779 preview and local native zoom.
This historical b887cb4 observation includes no human usability result.

## Native browser zoom observation — edd3de9

A later local check used Chromium's native tabs zoom API at 200%, confirmed by
getZoom=2, DPR 1→2 and a 1280→640 CSS-pixel layout viewport with unchanged
outer window and visual viewport scale 1. The earlier 640px proxy stays separate.
Question submission, fixture results, Bear Creek source selection, map focus and
keyboard controls remained reachable without horizontal overflow. The 420px map
plus its heading exceeds the 436px-high zoomed viewport; ordinary vertical scroll
reaches its lower attribution and source controls. Whole-map fit is not claimed.

Campaign `native-zoom-edd3de9` binds screenshots, current built assets and clean
application edd3de94d3512674d716fa9691924cf71e18dc02. Neutral map tiles and API
records are synthetic. Compositor screenshots capture native zoom without CSS
zoom or pinch emulation. This closes the scoped native-zoom execution gap;
human screen-reader, participant and production acceptance remain unestablished.

## Qualified-runtime preview — 37de779

[The 37de779 preview](https://firelens-kt3ob5vr8-yusenrong46-9212s-projects.vercel.app), deployment
`dpl_69Mrs37s9vkJw7T9xkW9mxqtYCE4`, reports the exact build identity. Desktop
1672×941 and mobile 390×844 checks passed source selection, map navigation,
cache-disabled refresh, a simulated stale-chunk one-reload guard and synthetic
outage/retry recovery. Assets came from the deployment; API answers and neutral
map tiles were fixtures. The stale-tab check injects the existing preload-error
event and does not claim an actual old-build tab crossed a deployment.

These UI results accompany independently accepted backend scope (12 fresh and
nine retained cases), not paid model calls from the preview. Documentation-only
successors require recorded runtime/configuration/asset equivalence and retain
their own deployment identity in the campaign. Production approval is separate.
