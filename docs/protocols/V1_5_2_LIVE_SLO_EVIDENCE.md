# FireLens V1.5-2 live SLO evidence protocol

Status: implemented measurement harness; thresholds unratified; no production SLO is proven.

This protocol separates observation from policy. The capture measures official-source behavior,
but it cannot decide an acceptable availability, freshness, or latency objective. Those thresholds
remain `null` in `data/evaluation/live_slo.v1.yaml` until the product owner ratifies them from real
evidence and official-source constraints.

## Fixed observation roster

Each repetition creates a fresh `LiveDataService` and measures both the first (`cold`) and immediate
second (`cached`) call for:

- each official incident, perimeter, and evacuation layer across BC; and
- all three layers near fixed coarse locations in the Lower Mainland, Okanagan, and Central BC.

The default is three repetitions and the hard maximum is ten. Every observation retains target,
phase, timestamps, requested layers, bounded coarse location, latency, returned-record count,
unavailable layers, aggregate freshness, and source-level update/retrieval observations for every
requested layer, including an available layer with no matching records. It never retains exception
text. Unexpected failures use only the content-free class `unexpected`.

The derived summaries report availability rate, p50/p95 latency, freshness coverage, stale-layer
observation count, and minimum/maximum authoritative layer-update age. Negative source age remains
visible as clock-skew evidence.

## Capture and verification

Run capture only from the exact candidate you intend to diagnose:

```bash
make capture-live-slo
make verify-live-slo
```

Capture refuses to overwrite an existing report. The report binds the protocol hash, harness hash,
Git commit, dirty-worktree state, and official source URLs. The verifier reconstructs the exact
layer/region/repetition/phase roster, raw record-group totals, freshness state, and every summary.

The current protocol is deliberately `qualification_eligible=false` and `diagnostic_only`. A dirty
worktree capture is useful for development diagnosis but is not release evidence. Even a clean
capture cannot establish a production SLO because it measures one local process rather than a
scheduled, multi-instance production window.

## Ratification still required

Before this can become a release gate, the owner must approve:

1. availability objective and observation window;
2. freshness objective per official layer, including clock-skew handling;
3. cold and cached p50/p95 targets by layer and region;
4. minimum sample count and schedule;
5. production deployment identity and multi-instance aggregation method; and
6. alert routing, retention, access, deletion, and incident-response ownership.

After ratification, introduce a new immutable protocol version. Do not edit v1 thresholds in place
or reinterpret an earlier diagnostic capture as qualifying evidence.
