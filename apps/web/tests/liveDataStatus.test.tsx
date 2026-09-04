import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { LiveDataStatus, liveDataTone } from "../src/app/LiveDataStatus";
import type { LiveCurrentSummary } from "../src/shared/api/api";

const reachable: LiveCurrentSummary = {
  incident_record_count: 12,
  evacuation_record_count: 3,
  source_status: "fresh",
  retrieved_at: "2026-09-03T22:00:00Z",
  freshness: "fresh",
  limitation: "Counts come from the latest official adapter fetch.",
};

const bothLayersDown: LiveCurrentSummary = {
  incident_record_count: null,
  evacuation_record_count: null,
  source_status: "partial",
  retrieved_at: "2026-09-03T22:00:00Z",
  freshness: null,
  limitation: "FireLens could not reach the official incident, evacuation records. That is not an all-clear and is not a zero count.",
};

const oneLayerDown: LiveCurrentSummary = {
  incident_record_count: 12,
  evacuation_record_count: null,
  source_status: "partial",
  retrieved_at: "2026-09-03T22:00:00Z",
  freshness: "mixed",
  limitation: "FireLens could not reach the official evacuation records.",
};

describe("liveDataTone", () => {
  it("never treats a 503-ready process as live", () => {
    expect(liveDataTone(reachable, "not_ready")).toBe("unavailable");
  });

  it("never treats a retrieved-but-empty official fetch as live", () => {
    expect(liveDataTone(bothLayersDown, "ready")).toBe("unavailable");
    expect(liveDataTone(undefined, "ready")).toBe("unavailable");
  });

  it("marks a partial official fetch as delayed, not live", () => {
    expect(liveDataTone(oneLayerDown, "ready")).toBe("delayed");
  });

  it("keeps a complete fresh fetch live", () => {
    expect(liveDataTone(reachable, "ready")).toBe("live");
  });
});

describe("LiveDataStatus", () => {
  it("does not show a green live badge when official layers failed", () => {
    render(<LiveDataStatus liveSummary={bothLayersDown} readiness="ready" />);
    expect(screen.getByRole("status")).toHaveTextContent("Live data unavailable");
    expect(screen.getByRole("status")).toHaveClass("live-data-status--unavailable");
    expect(screen.queryByText("Updated just now")).not.toBeInTheDocument();
  });
});
