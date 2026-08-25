import { describe, expect, it } from "vitest";
import type { LiveResult } from "../src/shared/api/api";
import { buildLiveAnalysis } from "../src/features/near-me/liveAnalysis";

function incident(overrides: {
  result_id?: string;
  status?: string;
  fire_centre?: string | null;
} = {}): LiveResult {
  return {
    result_id: "incident:base",
    kind: "incident",
    authority: "BC Wildfire Service",
    source_url: "https://example.test/incident/base",
    source_updated_at: "2026-08-23T12:00:00Z",
    retrieved_at: "2026-08-23T12:01:00Z",
    freshness: "fresh",
    geometry_relation: "unknown",
    status: "Being Held",
    fire_centre: "Kamloops Fire Centre",
    geometry: { type: "Point", coordinates: [-119.5, 49.9] },
    ...overrides,
  };
}

describe("live analytical summaries", () => {
  it("groups incident fields deterministically and sorts ties by label", () => {
    const analysis = buildLiveAnalysis([
      incident({ result_id: "incident:1", status: "Out of Control" }),
      incident({ result_id: "incident:2", status: "Being Held" }),
      incident({ result_id: "incident:3", fire_centre: "Coastal Fire Centre", status: "Under Control" }),
    ]);
    expect(analysis.total).toBe(3);
    expect(analysis.byFireCentre).toEqual([
      { label: "Kamloops Fire Centre", count: 2, share: 2 / 3 },
      { label: "Coastal Fire Centre", count: 1, share: 1 / 3 },
    ]);
    expect(analysis.byStatus.map(({ label }) => label)).toEqual([
      "Being Held",
      "Out of Control",
      "Under Control",
    ]);
    expect(analysis.highestFireCentre?.label).toBe("Kamloops Fire Centre");
    expect(analysis.byStatus.reduce((total, row) => total + row.count, 0)).toBe(analysis.total);
  });

  it("excludes non-incident records and labels missing group values", () => {
    const analysis = buildLiveAnalysis([
      incident({ result_id: "incident:1", fire_centre: null }),
      { ...incident({ result_id: "evacuation:1" }), kind: "evacuation" },
    ]);
    expect(analysis.total).toBe(1);
    expect(analysis.byFireCentre).toEqual([{ label: "Not reported", count: 1, share: 1 }]);
    expect(analysis.byStatus).toEqual([{ label: "Being Held", count: 1, share: 1 }]);
  });

  it("keeps partially missing official grouping fields visible and reconciled", () => {
    const analysis = buildLiveAnalysis([
      incident({ result_id: "incident:1", fire_centre: "Kamloops Fire Centre" }),
      incident({ result_id: "incident:2", fire_centre: null }),
    ]);

    expect(analysis.byFireCentre).toEqual([
      { label: "Kamloops Fire Centre", count: 1, share: 0.5 },
      { label: "Not reported", count: 1, share: 0.5 },
    ]);
    expect(analysis.byFireCentre.reduce((total, row) => total + row.count, 0)).toBe(
      analysis.total,
    );
  });

  it("never presents the missing-value bucket as a fire centre", () => {
    const analysis = buildLiveAnalysis([
      incident({ result_id: "incident:1", fire_centre: null }),
      incident({ result_id: "incident:2", fire_centre: " " }),
      incident({ result_id: "incident:3", fire_centre: "Coastal Fire Centre" }),
    ]);

    expect(analysis.byFireCentre[0]).toEqual({
      label: "Not reported",
      count: 2,
      share: 2 / 3,
    });
    expect(analysis.highestFireCentre?.label).toBe("Coastal Fire Centre");
    expect(buildLiveAnalysis([
      incident({ result_id: "incident:4", fire_centre: null }),
    ]).highestFireCentre).toBeUndefined();
  });
});
