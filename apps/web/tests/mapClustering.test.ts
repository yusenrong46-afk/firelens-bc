import { describe, expect, it } from "vitest";
import {
  clusterPointResults,
  excludeQuestionMatches,
  isQuestionMatch,
} from "../src/features/near-me/mapClustering";
import { filterMapResults } from "../src/features/near-me/MapLayerFilters";
import type { LiveResult } from "../src/shared/api/api";

function point(id: string, lat: number, lng: number, status = "Being Held"): LiveResult {
  return {
    result_id: id,
    kind: "incident",
    authority: "BC Wildfire Service",
    source_url: `https://example.test/${id}`,
    source_updated_at: "2026-08-13T19:00:00Z",
    retrieved_at: "2026-08-13T19:05:00Z",
    freshness: "fresh",
    status,
    name: id,
    geometry_relation: "nearby",
    geometry: { type: "Point", coordinates: [lng, lat] },
    fire_of_note: false,
  };
}

describe("map clustering and filters", () => {
  it("keeps individual markers at higher zoom", () => {
    const results = Array.from({ length: 40 }, (_, index) => point(`incident:${index}`, 49.8, -119.5 + index * 0.01));
    const clustered = clusterPointResults(results, 9);
    expect(clustered.every((item) => item.type === "record")).toBe(true);
    expect(clustered).toHaveLength(40);
  });

  it("buckets nearby points when zoom is low and count is high", () => {
    const results = Array.from({ length: 40 }, (_, index) => point(`incident:${index}`, 49.88, -119.49));
    const clustered = clusterPointResults(results, 5);
    expect(clustered.some((item) => item.type === "cluster")).toBe(true);
  });

  it("filters layers and incident statuses client-side", () => {
    const results = [
      point("incident:1", 49.8, -119.5, "Out of Control"),
      point("incident:2", 49.9, -119.4, "Being Held"),
      { ...point("evacuation:1", 49.9, -119.4, "Order"), kind: "evacuation" as const },
    ];
    expect(filterMapResults(results, new Set(["evacuation"]), "all", new Set()).map((item) => item.result_id)).toEqual([
      "incident:1",
      "incident:2",
    ]);
    expect(filterMapResults(results, new Set(), "selected", new Set(["Being Held"])).map((item) => item.result_id)).toEqual([
      "incident:2",
      "evacuation:1",
    ]);
    expect(filterMapResults(results, new Set(), "selected", new Set(["Out of Control"])).map((item) => item.result_id)).toEqual([
      "incident:1",
      "evacuation:1",
    ]);
  });

  it("keeps statuses that are present in the returned data instead of a fixed set", () => {
    const results = [point("incident:1", 49.8, -119.5, "Patrol Required")];
    expect(filterMapResults(results, new Set(), "all", new Set())).toHaveLength(1);
    expect(filterMapResults(results, new Set(), "selected", new Set(["Patrol Required"]))).toHaveLength(1);
    expect(filterMapResults(results, new Set(), "selected", new Set())).toHaveLength(0);
  });

  it("keeps original question matches separate when filters hide them", () => {
    const matchingIds = new Set(["incident:matching-polygon", "incident:matching-point"]);
    const matchingPolygon = {
      ...point("incident:matching-polygon", 49.8, -119.5, "Out of Control"),
      geometry: {
        type: "Polygon",
        coordinates: [[[-119.6, 49.7], [-119.4, 49.7], [-119.4, 49.9], [-119.6, 49.7]]],
      },
    };
    const contextualPolygon = {
      ...point("incident:context-polygon", 49.8, -119.4, "Being Held"),
      geometry: {
        type: "Polygon",
        coordinates: [[[-119.5, 49.7], [-119.3, 49.7], [-119.3, 49.9], [-119.5, 49.7]]],
      },
    };
    const matchingPoint = point("incident:matching-point", 49.88, -119.49, "Out of Control");
    const contextualPoints = Array.from(
      { length: 30 },
      (_, index) => point(`incident:context-point-${index}`, 49.88, -119.49, "Being Held"),
    );
    const allResults = [matchingPolygon, contextualPolygon, matchingPoint, ...contextualPoints];
    const filtered = filterMapResults(allResults, new Set(), "selected", new Set(["Being Held"]));

    expect(filtered.map((result) => result.result_id)).not.toContain("incident:matching-polygon");
    expect(isQuestionMatch([contextualPolygon.result_id], matchingIds)).toBe(false);
    const clusters = clusterPointResults(filtered, 5).filter((item) => item.type === "cluster");
    expect(clusters).not.toHaveLength(0);
    expect(clusters.every((cluster) => isQuestionMatch(cluster.ids, matchingIds) === false)).toBe(true);
    expect(excludeQuestionMatches([matchingPolygon, contextualPolygon], matchingIds)).toEqual([contextualPolygon]);
  });
});
