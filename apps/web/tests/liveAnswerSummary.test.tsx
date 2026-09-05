import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { LiveAnswerSummary } from "../src/features/ask/LiveAnswerSummary";
import type { AskResponse } from "../src/shared/api/api";

const response: AskResponse = {
  status: "answer",
  response_mode: "live",
  trace_id: "live-summary",
  presentation_shell: "analysis",
  provenance_class: "official_live",
  live_results: [{
    result_id: "incident:one",
    kind: "incident",
    authority: "Example Official Authority",
    source_url: "https://example.test/incident/one",
    source_updated_at: "2026-08-28T12:00:00Z",
    retrieved_at: "2026-08-28T12:05:00Z",
    freshness: "fresh",
    status: "Being Held",
    name: "Example Fire",
    geometry_relation: "unknown",
    geometry: { type: "Point", coordinates: [-119.5, 49.9] },
    fire_of_note: false,
  }],
  aggregate_freshness: "fresh",
};

describe("LiveAnswerSummary", () => {
  afterEach(cleanup);
  it("uses a neutral heading and only source-supplied provenance and update time", () => {
    render(<LiveAnswerSummary response={response} />);

    expect(screen.getByText(/1 official record found|1 wildfire found/i)).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Live answer summary" })).toHaveTextContent(/Example Official Authority/);
    expect(screen.getByRole("region", { name: "Live answer summary" })).toHaveTextContent(/Updated|Aug 28, 2026/i);
    expect(screen.queryByText(/12:05:00Z/)).not.toBeInTheDocument();
  });

  it("does not count an incident and its perimeter as two wildfires", () => {
    const incident = response.live_results![0]!;
    const paired: AskResponse = {
      ...response,
      roster_total: 4,
      live_results: [
        { ...incident, result_id: "incident:one", incident_number: "K10001" },
        { ...incident, result_id: "perimeter:one", kind: "perimeter", incident_number: "k10001" },
        { ...incident, result_id: "incident:two", incident_number: "K10002", name: "Second Fire" },
        { ...incident, result_id: "perimeter:two", kind: "perimeter", incident_number: "K10002", name: null },
      ],
    };

    render(<LiveAnswerSummary response={paired} placeName="Kelowna" radiusKm={50} />);

    expect(screen.getByRole("heading", { name: "2 wildfires found within 50 km of Kelowna" })).toBeInTheDocument();
    expect(screen.getByText(/4 official records: 2 incident records and 2 mapped perimeters/i)).toBeInTheDocument();
    expect(screen.queryByText(/4 active wildfires/i)).not.toBeInTheDocument();
  });

  it("does not invent wildfire identity from unrelated row IDs", () => {
    const incident = response.live_results![0]!;
    const unlinked: AskResponse = {
      ...response,
      roster_total: 2,
      live_results: [
        { ...incident, result_id: "incident:one", incident_number: null },
        { ...incident, result_id: "perimeter:one", kind: "perimeter", incident_number: null },
      ],
    };

    const view = render(<LiveAnswerSummary response={unlinked} placeName="Kelowna" />);

    expect(view.getByRole("heading", { name: "2 official records found near Kelowna" })).toBeInTheDocument();
    expect(view.container).toHaveTextContent("wildfire total is not inferred without incident identities");
    expect(view.container).not.toHaveTextContent("2 wildfires found");
  });

  it("labels evacuation-only results as evacuation records rather than wildfires", () => {
    const evacuation: AskResponse = {
      ...response,
      roster_total: 1,
      live_results: [{
        ...response.live_results![0]!,
        result_id: "evacuation:one",
        kind: "evacuation",
        incident_number: null,
        name: "Example Evacuation Order",
      }],
    };

    const view = render(
      <LiveAnswerSummary
        response={evacuation}
        placeName="Kamloops"
        onOpenMap={() => undefined}
      />,
    );

    expect(view.getByRole("heading", { name: "1 official evacuation record found near Kamloops" })).toBeInTheDocument();
    expect(view.getByRole("button", { name: /View all matching records on the map/i })).toBeInTheDocument();
    expect(view.container).not.toHaveTextContent(/active wildfire/i);
    expect(view.container).not.toHaveTextContent(/View all fires/i);
  });

  it("does not infer a wildfire total from a paginated partial roster", () => {
    const partial: AskResponse = {
      ...response,
      roster_total: 240,
      live_results: Array.from({ length: 10 }, (_, index) => ({
        ...response.live_results![0]!,
        result_id: `incident:${index}`,
        incident_number: `K${10000 + index}`,
      })),
    };

    render(<LiveAnswerSummary response={partial} placeName="Kelowna" />);

    expect(screen.getByRole("heading", { name: "240 official records found near Kelowna" })).toBeInTheDocument();
    expect(screen.getByText(/Showing 10 returned records; a wildfire total is not inferred from a partial roster/i)).toBeVisible();
    expect(screen.queryByText(/10 wildfires found/i)).not.toBeInTheDocument();
  });

  it.each([0.0004, 12.34567])("preserves the exact official size %s without rounding", (size) => {
    const view = render(<LiveAnswerSummary response={{ ...response, live_results: [{ ...response.live_results![0]!, size_hectares: size }] }} />);
    expect(view.getByText(`Size ${size} ha`)).toBeVisible();
  });

  it("includes the visible map action label in its accessible name", () => {
    const view = render(<LiveAnswerSummary response={response} onOpenMap={() => undefined} />);
    expect(view.getByRole("button", { name: /^View map — View all matching records on the map$/ })).toHaveTextContent("View map");
  });
});
