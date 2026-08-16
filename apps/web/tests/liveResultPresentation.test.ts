import { describe, expect, it } from "vitest";
import { isRenderableGeometry, geometryLatLngs } from "../src/features/near-me/liveResultPresentation";
import type { LiveResult } from "../src/shared/api/api";

const base: LiveResult = {
  result_id: "incident:test",
  kind: "incident",
  authority: "BC Wildfire Service",
  source_url: "https://example.test/incidents/test",
  source_updated_at: "2026-08-15T12:00:00Z",
  retrieved_at: "2026-08-15T12:05:00Z",
  freshness: "fresh",
  status: "Out of Control",
  geometry_relation: "nearby",
  geometry: { type: "Point", coordinates: [-123.12, 49.28] },
};

describe("isRenderableGeometry", () => {
  it("does not throw when a live record has no geometry", () => {
    const missingGeometry = { ...base };
    delete (missingGeometry as { geometry?: LiveResult["geometry"] }).geometry;
    expect(isRenderableGeometry(missingGeometry)).toBe(false);
  });

  it("walks perimeter coordinates for map fitting", () => {
    const perimeter: LiveResult = {
      ...base,
      result_id: "perimeter:1",
      kind: "perimeter",
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [-119.9, 49.8],
            [-119.8, 49.8],
            [-119.8, 49.9],
            [-119.9, 49.8],
          ],
        ],
      },
    };
    expect(geometryLatLngs(perimeter)).toEqual([
      [49.8, -119.9],
      [49.8, -119.8],
      [49.9, -119.8],
      [49.8, -119.9],
    ]);
  });
});
