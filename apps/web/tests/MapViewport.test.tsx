import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FitResults } from "../src/features/near-me/MapViewport";
import type { LiveResult } from "../src/shared/api/api";

const map = vi.hoisted(() => ({
  fitBounds: vi.fn(),
  setView: vi.fn(),
  invalidateSize: vi.fn(),
  getContainer: vi.fn(),
}));
vi.mock("react-leaflet", () => ({ useMap: () => map }));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("map container resizing", () => {
  it("refreshes Leaflet on expansion and shrinking without refitting or animating selection", () => {
    const container = document.createElement("div");
    map.getContainer.mockReturnValue(container);
    let resized: (() => void) | undefined;
    const observe = vi.fn();
    const disconnect = vi.fn();
    vi.stubGlobal("ResizeObserver", class {
      constructor(callback: () => void) { resized = callback; }
      observe = observe;
      disconnect = disconnect;
    });
    const selected: LiveResult = {
      result_id: "incident:selected",
      kind: "incident",
      authority: "BC Wildfire Service",
      source_url: "https://example.test/fire",
      source_updated_at: "2026-09-15T18:00:00Z",
      retrieved_at: "2026-09-15T18:05:00Z",
      status: "Being Held",
      freshness: "fresh",
      geometry_relation: "nearby",
      fire_of_note: false,
      geometry: { type: "Point", coordinates: [-119.5, 49.9] },
    };
    const { unmount } = render(<FitResults results={[selected]} focusResults={[selected]} selectedResultId={selected.result_id} />);
    expect(observe).toHaveBeenCalledWith(container);
    expect(map.fitBounds).toHaveBeenCalledOnce();

    resized?.(); // The compact rail expands without a browser resize event.
    resized?.(); // Back to answer shrinks the same map container.

    expect(map.invalidateSize).toHaveBeenCalledTimes(2);
    expect(map.invalidateSize).toHaveBeenLastCalledWith({ animate: false, pan: false });
    expect(map.fitBounds).toHaveBeenCalledOnce();
    expect(map.setView).not.toHaveBeenCalled();
    unmount();
    expect(disconnect).toHaveBeenCalledOnce();
  });
});
