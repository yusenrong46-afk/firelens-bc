import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MapRecordPopup } from "../src/features/near-me/MapRecordPopup";
import type { LiveResult } from "../src/shared/api/api";

const incident: LiveResult = {
  result_id: "incident:7",
  kind: "incident",
  authority: "BC Wildfire Service",
  source_url: "https://example.test/incidents/7",
  source_updated_at: "2026-08-13T19:00:00Z",
  retrieved_at: "2026-08-13T19:05:00Z",
  freshness: "fresh",
  status: "Out of Control",
  name: "Test Fire",
  geometry_relation: "nearby",
  geometry: { type: "Point", coordinates: [-119.5, 49.89] },
  fire_of_note: false,
};

describe("map record popup", () => {
  it("shows kind and geometry meaning for incident points and polygon records", () => {
    const { rerender } = render(<MapRecordPopup result={incident} />);
    expect(screen.getByText("Test Fire")).toBeInTheDocument();
    expect(screen.getByText("Wildfire incident")).toBeInTheDocument();
    expect(screen.getByText(/incident point/i)).toBeInTheDocument();
    expect(screen.getByText(/not perimeter geometry/i)).toBeInTheDocument();

    rerender(
      <MapRecordPopup
        result={{
          ...incident,
          result_id: "perimeter:1",
          kind: "perimeter",
          name: "Perimeter Fire",
          geometry: {
            type: "Polygon",
            coordinates: [[[-119.9, 49.8], [-119.8, 49.8], [-119.8, 49.9], [-119.9, 49.8]]],
          },
        }}
      />,
    );
    expect(screen.getByText("Wildfire perimeter")).toBeInTheDocument();
    expect(screen.getByText(/wildfire perimeter outline/i)).toBeInTheDocument();
    expect(screen.getByText(/not the active flame front/i)).toBeInTheDocument();

    rerender(
      <MapRecordPopup
        result={{
          ...incident,
          result_id: "evacuation:1",
          kind: "evacuation",
          name: "Alert Area",
          geometry: {
            type: "Polygon",
            coordinates: [[[-119.9, 49.8], [-119.8, 49.8], [-119.8, 49.9], [-119.9, 49.8]]],
          },
        }}
      />,
    );
    expect(screen.getByText("Evacuation area")).toBeInTheDocument();
    expect(screen.getByText(/evacuation area outline/i)).toBeInTheDocument();
    expect(screen.getByText(/not a wildfire perimeter/i)).toBeInTheDocument();
  });
});
