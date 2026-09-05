import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { OfficialSourcesCard } from "../src/app/OfficialSourcesCard";
import type { AskResponse, LiveResult } from "../src/shared/api/api";

const first: LiveResult = {
  result_id: "incident:first", name: "First Fire", kind: "incident", authority: "First Authority",
  source_url: "https://example.test/first", source_updated_at: "2026-08-24T12:00:00Z",
  retrieved_at: "2026-08-24T12:05:00Z", freshness: "stale", status: "Being Held",
  geometry_relation: "unknown", geometry: {}, fire_of_note: false,
};
const second: LiveResult = { ...first, result_id: "incident:second", name: "Second Fire", authority: "Second Authority", source_url: "https://example.test/second" };
const response: AskResponse = { status: "answer", response_mode: "live", trace_id: "source-test", presentation_shell: "spatial", provenance_class: "official_live", live_results: [second] };

describe("selected record source binding", () => {
  afterEach(cleanup);
  it("uses the retained selected map record after a narrower follow-up", () => {
    render(<OfficialSourcesCard response={response} selectedResultId={first.result_id} selectedRecord={first} />);
    expect(screen.getByText("For First Fire")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "First Authority" })).toHaveAttribute("href", first.source_url);
    expect(screen.getByText("Stale record")).toBeInTheDocument();
    expect(screen.getByText("Also used: Second Authority")).toBeInTheDocument();
  });
  it("does not silently substitute another source for an unresolved selection", () => {
    render(<OfficialSourcesCard response={response} selectedResultId="incident:missing" />);
    expect(screen.queryByText("For Second Fire")).not.toBeInTheDocument();
    expect(screen.queryByText("Current at retrieval")).not.toBeInTheDocument();
  });
  it("keeps unavailable layers explicit alongside returned records", () => {
    render(<OfficialSourcesCard response={{ ...response, unavailable_layers: ["evacuation"] }} />);
    expect(screen.getByText(/Unavailable layers: evacuation/)).toBeInTheDocument();
    expect(screen.getByText("Source updated")).toBeInTheDocument();
    expect(screen.getByText("FireLens fetched")).toBeInTheDocument();
  });
});
