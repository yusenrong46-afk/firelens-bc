# FireLens: AI engineer case study

## Problem and architecture

FireLens is an evidence-aware wildfire information application combining official
geospatial records, retrieval-grounded guidance, and evaluated conversational
workflows for B.C. residents. A fluent answer is insufficient: the application
must keep a recorded fire status distinct from preparedness advice and generated
background. It is not an emergency authority.

The request/context owner resolves the task, geography and selected record. A typed
plan chooses official records, reviewed retrieval or permitted background. The
retrieval layer ranks eligible source passages; publication checks control what
may be asserted and quoted. Deterministic code owns official facts. The response
contract carries evidence and limitations to React, where answer, Copy, Why and
history retain one response snapshot while map observations refresh separately.

## Two failures and a bounded intervention

Pet additions lost their preceding preparedness subject. A subsequent located fire
lookup inherited weather context because ordinary “there” was treated as a
reference. The repairs modify existing interpretation owners rather than adding
another orchestrator or changing models. A neighboring parser correction prevents
“I/we/you/they” from becoming a supposed contents container.

A frozen 24-case offline bank covers both failures, equivalent wordings and changed
meaning controls. Main `ed2a7af` and starting UI candidate `f103afd` scored 15/24;
the repaired implementation scored 24/24: nine paired wins, zero losses. Full pet
passage and document-hash checks protect qualifications. This is a narrow fixture
comparison, not a population accuracy estimate. Independent review added controls
for unrelated pet packing, demonstrating why passing an initial bank is insufficient.

## Reliability and tradeoffs

Preserve a 45-second request deadline, bounded retries, four-request provider
concurrency and explicit unavailable states. Evidence inspection and map refresh
should not dispatch inference. Source relevance is not proof of complete coverage;
quotations and distances still need source-bound checks. Costs with missing receipts
remain unknown. Measure provider work, latency, memory and package size before
making optimization claims; this repair does not claim faster inference.

## Ownership and remaining limits

The project owner directed requirements, constraints, investigation and review;
OpenAI Codex assisted implementation and testing. Browser testing, source inspection
and independent agent review are not wildfire/public-health expert approval.
The original 178-chunk corpus remains unchanged; source migration and broader
backend acceptance remain deferred. Release status belongs to the exact commit's
[release evidence](../product/map-first-release-v2.md), not an aggregated history.
