import { describe, expect, it } from "vitest";
import { isRenderableGeometry, geometryLatLngs, MAP_GEOMETRY_LEGEND, mapGeometryLegendFor, mapPopupGeometryMeaning, resultKindLabel } from "../src/features/near-me/liveResultPresentation";
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
  fire_of_note: false,
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

  it("describes points and polygons without kind/domain mislabelling", () => {
    expect(MAP_GEOMETRY_LEGEND.points).toMatch(/representative source point/i);
    expect(MAP_GEOMETRY_LEGEND.points).toMatch(/not perimeter geometry/i);
    expect(MAP_GEOMETRY_LEGEND.points).not.toMatch(/evacuation locations, not perimeters/i);
    expect(MAP_GEOMETRY_LEGEND.polygons).toMatch(/wildfire perimeters or evacuation areas/i);
    expect(MAP_GEOMETRY_LEGEND.polygons).toMatch(/record label/i);
    expect(MAP_GEOMETRY_LEGEND.polygons).toMatch(/not the active flame front/i);
    expect(MAP_GEOMETRY_LEGEND.polygons).not.toMatch(/^Polygons mark official perimeters/i);

    const evacuationPolygon: LiveResult = {
      ...base,
      result_id: "evacuation:1",
      kind: "evacuation",
      geometry: {
        type: "Polygon",
        coordinates: [[[-119.9, 49.8], [-119.8, 49.8], [-119.8, 49.9], [-119.9, 49.8]]],
      },
    };
    const perimeterPoint: LiveResult = {
      ...base,
      result_id: "perimeter:point",
      kind: "perimeter",
      geometry: { type: "Point", coordinates: [-119.5, 49.9] },
    };
    expect(mapGeometryLegendFor(evacuationPolygon)).toBe(MAP_GEOMETRY_LEGEND.polygons);
    expect(mapGeometryLegendFor(evacuationPolygon)).toMatch(/evacuation areas/i);
    expect(mapGeometryLegendFor(perimeterPoint)).toBe(MAP_GEOMETRY_LEGEND.points);
    expect(mapGeometryLegendFor(perimeterPoint)).toMatch(/not perimeter geometry/i);
    expect(mapPopupGeometryMeaning(evacuationPolygon)).toMatch(/evacuation area outline/i);
    expect(mapPopupGeometryMeaning(evacuationPolygon)).toMatch(/not a wildfire perimeter/i);
    expect(mapPopupGeometryMeaning(perimeterPoint)).toMatch(/not perimeter geometry/i);
    const perimeterPolygon: LiveResult = {
      ...evacuationPolygon,
      result_id: "perimeter:poly",
      kind: "perimeter",
    };
    expect(mapPopupGeometryMeaning(perimeterPolygon)).toMatch(/wildfire perimeter outline/i);
    expect(mapPopupGeometryMeaning(perimeterPolygon)).toMatch(/not the active flame front/i);
    expect(mapPopupGeometryMeaning(base)).toMatch(/incident point/i);
    expect(resultKindLabel("perimeter")).toBe("Wildfire perimeter");
    expect(resultKindLabel("evacuation")).toBe("Evacuation area");
  });
});
