# 14 — Performance and Cost

## Enforced or configured bounds

| Boundary | Current default / limit | Owner |
| --- | ---: | --- |
| Public server deadline | 45 seconds | [`config.py`](../../src/firelens/config.py), Ask/live routes |
| Provider HTTP timeout | 30 seconds | `FireLensConfig` / `OpenRouterProvider` |
| Provider attempts | At most 3 | `FireLensConfig`, [`providers/openrouter.py`](../../src/firelens/providers/openrouter.py) |
| Provider concurrency | 4, adaptive minimum 1 | same |
| Planned tool calls | At most 4 | [`agent/budget.py`](../../src/firelens/agent/budget.py) |
| Tool rounds | 2 | same |
| Retrieval cycles | 2 | same |
| Grounded generation / outer write / rewrite | 1 each | same |
| Browser request deadline | 60 seconds | [`shared/api/api.ts`](../../apps/web/src/shared/api/api.ts) |

The plan and pure deterministic branches avoid unnecessary model calls. Pure accepted static responses use the static service generation path without an additional outer write; terminal capability/safety/clarification paths can use zero provider inference. Live records with results are rendered deterministically.

## Important implementation caveat

`RequestExecutionPolicy` declares planner, embedding, and reranking budgets, but the inspected public path does not consistently consume those counters at their actual provider boundaries. They are telemetry/intention fields, not reliable enforcement claims. Exact tool-call and provider-stage counting should be centralized before using these numbers for SLO or cost decisions.

## Measurement status

Astra's local adapter retains 30 validated HTTP samples per route after five
warmups, in three repetitions, using the existing ten-route workload. Every
sample records latency, HTTP status, response mode and fake-provider counters.
Invalid contracts and 4xx responses count as failures. Missing, empty,
incomplete or malformed historical comparisons cannot produce
`MEASURED_NO_ROUTE_REGRESSION`; they remain `NOT_COMPARABLE`. See the
[Astra packet](../reports/ASTRA_CONTINUATION.md) for paired results and limits.

The following numbers belong to the historical Sol campaign:

The clean pre-fix local fake-provider baseline ran 100 repetitions per route;
route p95 values ranged from 0.666 to 11.798 ms with zero generation calls. The
candidate's final local fake run is retained outside Git and uses the same
limitations: loopback fixtures, no external model/feed/network, and no fleet
latency authority. The web main bundle changed from 546.86 kB / 159.64 kB gzip
to 546.18 kB / 159.78 kB gzip; CSS changed from 79.46 kB / 14.62 kB gzip to
79.64 kB / 14.67 kB gzip. The main Vite chunk remains above 500 kB.

No throughput, real provider-call, token, or cost comparison is claimed. The
live repair was exercised with local `httpx.MockTransport`; it does not measure
network latency or cost.

Before optimization, capture a matched base/candidate workload with commit/tree, dataset/evaluator hashes, warm/cold state, concurrency, provider model IDs, token/cost receipts, and uncertainty. A zero-dollar fake-provider run proves only that the fake path made no billable call.
