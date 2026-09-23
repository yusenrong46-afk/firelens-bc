import type { ReactNode } from "react";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { LiveMap } from "../src/features/near-me/LiveMap";
import type { LiveResult } from "../src/shared/api/api";

const map = vi.hoisted(() => ({
  fitBounds: vi.fn(),
  setView: vi.fn(),
  getZoom: () => 10,
  on: vi.fn(),
  off: vi.fn(),
}));

vi.mock("react-leaflet", () => ({
  MapContainer: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  CircleMarker: () => null,
  GeoJSON: () => null,
  Popup: () => null,
  TileLayer: ({ eventHandlers }: { eventHandlers: { tileerror: () => void } }) => (
    <button type="button" onClick={eventHandlers.tileerror}>Simulate tile failure</button>
  ),
  useMap: () => map,
}));

afterEach(cleanup);

const incident: LiveResult = {
  result_id: "incident:matching",
  kind: "incident",
  name: "Example fire",
  authority: "BC Wildfire Service",
  source_url: "https://example.test/fire",
  source_updated_at: "2026-09-15T10:00:00Z",
  retrieved_at: "2026-09-15T10:05:00Z",
  freshness: "fresh",
  status: "Being Held",
  geometry_relation: "nearby",
  geometry: { type: "Point", coordinates: [-119.5, 49.9] },
  fire_of_note: false,
};

const evacuation: LiveResult = {
  ...incident,
  result_id: "evacuation:province",
  name: "Example alert",
  kind: "evacuation",
  status: "Alert",
  authority: "Regional district",
  source_url: "https://example.test/alert",
};

describe("map presentation and retained scope", () => {
  it.each([true, false])("does not report empty layers while coverage is pending or failed (loading=%s)", (loading) => {
    render(<LiveMap results={[]} loading={loading} loadError={loading ? undefined : "The service did not respond."} />);
    const totals = screen.getByLabelText("Official record totals");
    expect(totals).toHaveTextContent("Displayed-record totals unavailable");
    expect(totals).not.toHaveTextContent(/0 fires|0 evacuation|0 perimeters/);
    expect(screen.queryByText(/No official map records were returned/)).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(loading ? "Loading province-wide records" : "Missing records are not an all-clear");
  });

  it("retains answer records and selection when province coverage fails", () => {
    const select = vi.fn();
    render(<LiveMap results={[incident]} matchingResults={[incident]} loadError="The service did not respond." onSelectResult={select} />);
    expect(screen.getByLabelText("Official record totals")).toHaveTextContent("1 retained official record displayed");
    fireEvent.click(within(screen.getByRole("list", { name: "Matching this question" })).getByRole("button", { name: /Example fire Being Held/ }));
    expect(select).toHaveBeenCalledWith(incident.result_id);
  });

  it("exposes compact-map scope, all layer toggles, and counts that follow local filters", () => {
    render(<LiveMap variant="compact" results={[incident, evacuation]} matchingResults={[incident]} />);

    expect(screen.getByRole("heading", { name: "Wildfires in B.C. right now" })).toBeInTheDocument();
    for (const name of ["Fires", "Evacuations", "Perimeters"]) {
      expect(screen.getByRole("button", { name })).toHaveAttribute("aria-pressed", "true");
    }
    expect(screen.getByLabelText("Official record totals")).toHaveTextContent("2 displayed official records");
    expect(screen.getByText(/1 matching record is shown/)).toHaveTextContent("1 other official record is also shown for B.C.");

    fireEvent.click(screen.getByRole("button", { name: "Fires" }));

    expect(screen.getByLabelText("Official record totals")).toHaveTextContent("1 displayed official record");
    expect(screen.getByText(/current filters hide every matching record/)).toHaveTextContent("Filters change only what is shown");
    expect(screen.getByRole("button", { name: "Fires" })).toHaveAttribute("aria-pressed", "false");
  });

  it("shows supplied context and expands without mutating selected record identity", () => {
    const expand = vi.fn();
    render(<LiveMap variant="compact" heading="Records near Kelowna" contextLabel="Within 50 km of Kelowna" results={[incident]} selectedResultId={incident.result_id} onExpand={expand} />);

    expect(screen.getByRole("heading", { name: "Records near Kelowna" })).toBeInTheDocument();
    expect(screen.getByText("Within 50 km of Kelowna")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Expand map" }));
    expect(expand).toHaveBeenCalledOnce();
    expect(map.fitBounds).toHaveBeenLastCalledWith([[49.9, -119.5]], expect.objectContaining({ animate: false }));
  });

  it("keeps failure warnings visible and opens the selectable list when tiles fail", () => {
    const select = vi.fn();
    render(<LiveMap variant="compact" results={[incident]} matchingResults={[incident]} aggregateFreshness="stale" unavailableLayers={["perimeter"]} partialLayers={["incident"]} geometryOmissions={[{ kind: "evacuation", count: 2 }]} onSelectResult={select} />);

    expect(screen.getByText(/official observations are stale/)).toBeInTheDocument();
    expect(screen.getByText(/Partial coverage for incident/)).toBeInTheDocument();
    expect(screen.getByText(/Some official layers are unavailable: perimeter/)).toBeInTheDocument();
    expect(screen.getByText(/2 evacuation records omitted/)).toHaveTextContent("A missing area is not an all-clear");
    expect(screen.getByLabelText("Official record totals")).toHaveTextContent("Perimeter records unavailable");
    expect(screen.getByLabelText("Official record totals")).not.toHaveTextContent("0 perimeters");

    fireEvent.click(screen.getByRole("button", { name: "Simulate tile failure" }));

    expect(screen.getByText(/Street-map tiles failed/)).toBeInTheDocument();
    expect(screen.getByText("View displayed records (1)").closest("details")).toHaveAttribute("open");
    const list = screen.getByRole("list", { name: "Matching this question" });
    fireEvent.click(within(list).getByRole("button", { name: /Example fire Being Held/ }));
    expect(select).toHaveBeenCalledWith(incident.result_id);
  });

  it("does not turn an empty or mixed-freshness map into an all-clear", () => {
    const { rerender } = render(<LiveMap variant="compact" results={[]} unavailableLayers={["incident"]} />);
    expect(screen.getByText(/No official map records were returned/)).toHaveTextContent("not an all-clear");
    expect(screen.getByLabelText("Official record totals")).toHaveTextContent("Fire records unavailable");

    rerender(<LiveMap variant="compact" results={[incident, { ...evacuation, freshness: "stale" }]} />);
    expect(screen.getByText(/official observations have mixed freshness/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /some records out of date/ })).toBeInTheDocument();
  });
});
