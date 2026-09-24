import { cleanup, render } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { GeoJSON as LeafletGeoJSON } from "leaflet";
import type { LiveResult } from "../src/shared/api/api";
import { StaticGeometry } from "../src/features/near-me/StaticGeometry";

const current = vi.hoisted(() => ({ layer: undefined as LeafletGeoJSON | undefined }));
vi.mock("react-leaflet", async () => {
  const { createElement, forwardRef, useImperativeHandle, useState } = await import("react");
  const { GeoJSON } = await import("leaflet");
  return {
    // The installed react-leaflet owner creates data once; subsequent props only update style.
    GeoJSON: forwardRef<LeafletGeoJSON, { data: GeoJSON.Feature; children?: import("react").ReactNode }>(({ data, children }, ref) => {
      const [layer] = useState(() => new GeoJSON(data)); current.layer = layer;
      useImperativeHandle(ref, () => layer, [layer]); return createElement("div", null, children);
    }),
    Popup: ({ children }: { children?: import("react").ReactNode }) => createElement("div", null, children),
  };
});
afterEach(cleanup);
const record = { result_id: "evacuation:1", kind: "evacuation", authority: "EmergencyInfoBC", source_url: "https://example.test", source_updated_at: "2026-09-16T00:00:00Z", retrieved_at: "2026-09-16T00:00:00Z", freshness: "fresh", status: "Order", geometry: { type: "Polygon", coordinates: [[[-120,49],[-119,49],[-119,50],[-120,49]]] }, geometry_relation: "unknown", fire_of_note: false } as LiveResult;

it("updates actual Leaflet boundary coordinates for a retained record ID", () => {
  const { rerender } = render(<StaticGeometry result={record} matching selected />);
  expect(current.layer?.getBounds().getWest()).toBe(-120);
  const next = { ...record, geometry: { type: "Polygon", coordinates: [[[-122,49],[-119,49],[-119,50],[-122,49]]] } };
  rerender(<StaticGeometry result={next} matching selected />);
  expect(current.layer?.getBounds().getWest()).toBe(-122);
  const layer = current.layer; const clear = vi.spyOn(layer!, "clearLayers");
  rerender(<StaticGeometry result={{ ...next, geometry: JSON.parse(JSON.stringify(next.geometry)) }} matching selected />);
  expect(current.layer).toBe(layer); expect(clear).not.toHaveBeenCalled();
});
