import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { LiveAnswerSummary } from "../src/features/ask/LiveAnswerSummary";
import type { AskResponse } from "../src/shared/api/api";

const response: AskResponse = {
  status: "answer",
  response_mode: "live",
  trace_id: "live-summary",
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
  }],
  aggregate_freshness: "fresh",
};

describe("LiveAnswerSummary", () => {
  it("uses a neutral heading and only source-supplied provenance and update time", () => {
    render(<LiveAnswerSummary response={response} />);

    expect(screen.getByText("Official records returned")).toBeInTheDocument();
    expect(screen.getByText(/Example Official Authority/)).toBeInTheDocument();
    expect(screen.getByText(/2026-08-28T12:00:00Z/)).toBeInTheDocument();
    expect(screen.queryByText(/12:05:00Z/)).not.toBeInTheDocument();
  });
});
