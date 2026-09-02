import { describe, expect, it } from "vitest";
import type { LiveResult } from "../src/shared/api/api";
import {
  analyticalAnswerSummary,
  availableAnalysisSorts,
  buildLiveAnalysis,
  sortAnalysisResults,
} from "../src/features/near-me/liveAnalysis";

function incident(overrides: {
  result_id?: string;
  status?: string;
  fire_centre?: string | null;
  size_hectares?: number | null;
  distance_km?: number | null;
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
    size_hectares: 10,
    distance_km: 5,
    fire_of_note: false,
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
    expect(analysis.highestFireCentres.map(({ label }) => label)).toEqual(["Kamloops Fire Centre"]);
    expect(analysis.byStatus.reduce((total, row) => total + row.count, 0)).toBe(analysis.total);
  });

  it("does not turn a deterministic tie into a false single-centre leader", () => {
    const analysis = buildLiveAnalysis([
      incident({ result_id: "incident:1", fire_centre: "Kamloops Fire Centre" }),
      incident({ result_id: "incident:2", fire_centre: "Coastal Fire Centre" }),
    ]);

    expect(analysis.highestFireCentre).toBeUndefined();
    expect(analysis.highestFireCentres).toEqual([
      { label: "Coastal Fire Centre", count: 1, share: 0.5 },
      { label: "Kamloops Fire Centre", count: 1, share: 0.5 },
    ]);
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
    expect(buildLiveAnalysis([
      incident({ result_id: "incident:4", fire_centre: null }),
    ]).highestFireCentres).toEqual([]);
  });

  it("creates a concise deterministic lead instead of duplicating every chart row", () => {
    const summary = analyticalAnswerSummary([
      incident({ result_id: "incident:1", status: "Out of Control" }),
      incident({ result_id: "incident:2", status: "Out of Control" }),
      incident({
        result_id: "incident:3",
        fire_centre: "Coastal Fire Centre",
        status: "Being Held",
      }),
    ]);

    expect(summary).toBe(
      "This answer includes 3 fetched official incident records. "
      + "Kamloops Fire Centre has the highest fire-centre count (2). "
      + "Out of Control is the most common reported status (2).",
    );
  });
});

describe("snapshot-safe analysis controls", () => {
  it("offers numeric sorts only when at least 80 percent of incident records have values", () => {
    const complete = Array.from({ length: 5 }, (_, index) => incident({ result_id: `incident:${index}`, size_hectares: index, distance_km: index }));
    expect(availableAnalysisSorts(complete)).toEqual(["default", "newest", "largest", "nearest"]);
    const incomplete = complete.map((item, index) => index === 0 ? { ...item, size_hectares: null, distance_km: null } : item);
    expect(availableAnalysisSorts(incomplete)).toEqual(["default", "newest", "largest", "nearest"]);
    const belowFloor = incomplete.map((item, index) => index < 2 ? { ...item, size_hectares: null, distance_km: null } : item);
    expect(availableAnalysisSorts(belowFloor)).toEqual(["default", "newest"]);
  });

  it("sorts a snapshot deterministically and keeps missing numeric values last", () => {
    const results = [
      incident({ result_id: "incident:b", size_hectares: null, distance_km: null }),
      incident({ result_id: "incident:a", size_hectares: 4, distance_km: 2 }),
      incident({ result_id: "incident:c", size_hectares: 8, distance_km: 9 }),
    ];
    expect(sortAnalysisResults(results, "largest").map((item) => item.result_id)).toEqual(["incident:c", "incident:a", "incident:b"]);
    expect(sortAnalysisResults(results, "nearest").map((item) => item.result_id)).toEqual(["incident:a", "incident:c", "incident:b"]);
  });
});
