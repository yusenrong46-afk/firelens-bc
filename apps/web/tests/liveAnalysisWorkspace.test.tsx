import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { LiveResult } from "../src/shared/api/api";
import type { FireLensSession } from "../src/features/ask/useFireLensSession";
import { LiveAnalysisWorkspace } from "../src/features/near-me/LiveAnalysisWorkspace";

vi.mock("../src/features/near-me/LiveMap", () => ({
  LiveMap: ({ results, unavailableLayers }: { results: LiveResult[]; unavailableLayers?: string[] }) => (
    <div role="region" aria-label="Mock official map">
      <p data-testid="map-record-ids">{results.map((result) => result.result_id).join(",")}</p>
      <p data-testid="map-unavailable">{unavailableLayers?.join(",")}</p>
    </div>
  ),
}));

afterEach(() => cleanup());

function incident(index: number, fireCentre = index % 2 ? "Coastal Fire Centre" : "Kamloops Fire Centre"): LiveResult {
  return {
    result_id: `incident:${index}`,
    kind: "incident",
    authority: "BC Wildfire Service",
    source_url: `https://example.test/${index}`,
    source_updated_at: `2026-08-${String(10 + index).padStart(2, "0")}T12:00:00Z`,
    retrieved_at: "2026-08-29T12:01:00Z",
    freshness: "fresh",
    geometry_relation: "unknown",
    status: index % 2 ? "Being Held" : "Out of Control",
    fire_centre: fireCentre,
    size_hectares: index + 1,
    distance_km: index + 0.5,
    geometry: { type: "Point", coordinates: [-119.5, 49.9] },
  };
}

function session(results: LiveResult[], mapResults = results): FireLensSession {
  return {
    query: "",
    setQuery: vi.fn(),
    selected: 0,
    setSelected: vi.fn(),
    view: { kind: "answer", question: "distribution", response: { status: "answer", response_mode: "live", trace_id: "trace", answer: "records", claims: [], evidence: [], live_results: results, limitations: [], unavailable_layers: ["evacuations"] } },
    history: [],
    earlierTurns: [],
    locationLabel: "",
    setLocationLabel: vi.fn(),
    locationMessage: "",
    requiresLocation: false,
    response: { status: "answer", response_mode: "live", trace_id: "trace", answer: "records", claims: [], evidence: [], live_results: results, limitations: [], unavailable_layers: ["evacuations"] },
    mode: "live",
    claims: [],
    suggestions: [],
    visibleQuestion: "distribution",
    assistantText: "records",
    mapResults,
    mapMatchingResults: mapResults,
    mapProvinceResults: mapResults,
    mapLoading: false,
    mapMessage: undefined,
    mapAggregateFreshness: "fresh",
    mapUnavailableLayers: ["evacuations"],
    setMapVisible: vi.fn(),
    mapFocus: undefined,
    mapFocusResults: [],
    selectedLiveResultId: undefined,
    setSelectedLiveResultId: vi.fn(),
    askAboutResult: vi.fn(),
    submitQuestion: vi.fn(async () => undefined),
    clearHistory: vi.fn(),
    useApproximateLocation: vi.fn(),
    submitLocation: vi.fn(),
    submit: vi.fn(),
    clearManualLocation: vi.fn(),
  } as unknown as FireLensSession;
}

describe("LiveAnalysisWorkspace", () => {
  it("exposes semantic tabs with roving keyboard focus and a chart/table switch", async () => {
    const user = userEvent.setup();
    render(<LiveAnalysisWorkspace session={session(Array.from({ length: 13 }, (_, index) => incident(index)))} answerIdentity="one" />);
    const summary = screen.getByRole("tab", { name: "Summary" });
    const map = screen.getByRole("tab", { name: "Map" });
    const records = screen.getByRole("tab", { name: "Records" });
    const analysisTabs = [summary, map, records];
    const controlledAnalysisPanels = analysisTabs.map((tab) => {
      const panelId = tab.getAttribute("aria-controls");
      expect(panelId).toBeTruthy();
      const panel = document.getElementById(panelId!);
      expect(panel).toHaveAttribute("role", "tabpanel");
      return panel as HTMLDivElement;
    });
    expect(controlledAnalysisPanels.filter((panel) => !panel.hidden)).toHaveLength(1);
    expect(summary).toHaveAttribute("aria-selected", "true");
    expect(summary).toHaveAttribute("tabindex", "0");
    expect(map).toHaveAttribute("tabindex", "-1");

    summary.focus();
    const right = new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true, cancelable: true });
    fireEvent(summary, right);
    expect(right.defaultPrevented).toBe(true);
    await waitFor(() => expect(map).toHaveFocus());
    expect(map).toHaveAttribute("aria-selected", "true");
    expect(controlledAnalysisPanels.filter((panel) => !panel.hidden)).toHaveLength(1);
    await user.keyboard("{End}");
    await waitFor(() => expect(records).toHaveFocus());
    expect(records).toHaveAttribute("aria-selected", "true");
    await user.keyboard("{Home}");
    await waitFor(() => expect(summary).toHaveFocus());

    await user.click(summary);
    const charts = screen.getByRole("tab", { name: "Charts" });
    const table = screen.getByRole("tab", { name: "Table" });
    const chartPanels = [charts, table].map((tab) => {
      const panelId = tab.getAttribute("aria-controls");
      expect(panelId).toBeTruthy();
      const panel = document.getElementById(panelId!);
      expect(panel).toHaveAttribute("role", "tabpanel");
      return panel as HTMLDivElement;
    });
    expect(chartPanels.filter((panel) => !panel.hidden)).toHaveLength(1);
    expect(charts).toHaveAttribute("aria-selected", "true");
    expect(screen.queryByRole("group", { name: "Filter incident records" })).not.toBeInTheDocument();
    const snapshot = screen.getByRole("region", { name: "Current snapshot by fire centre" });
    expect(within(snapshot).getAllByRole("row")).toHaveLength(3);
    expect(within(snapshot).getByRole("row", { name: /1 Kamloops Fire Centre 7 54%/ })).toBeInTheDocument();
    expect(within(snapshot).getByRole("row", { name: /2 Coastal Fire Centre 6 46%/ })).toBeInTheDocument();
    expect(snapshot).not.toHaveTextContent(/change since last update|historical/i);
    charts.focus();
    await user.keyboard("{ArrowRight}");
    await waitFor(() => expect(table).toHaveFocus());
    expect(table).toHaveAttribute("aria-selected", "true");
    expect(chartPanels.filter((panel) => !panel.hidden)).toHaveLength(1);
    expect(screen.getAllByText("54%").length).toBeGreaterThan(0);
  });

  it("filters and sorts records, exposes details, and resets controls for a new answer", async () => {
    const user = userEvent.setup();
    const results = Array.from({ length: 13 }, (_, index) => incident(index));
    const view = render(<LiveAnalysisWorkspace session={session(results)} answerIdentity="one" />);
    await user.click(screen.getByRole("tab", { name: "Records" }));
    const centre = screen.getAllByLabelText("Fire centre").find((element) => element.tagName === "SELECT")!;
    expect(screen.getByRole("option", { name: "Largest first" })).toBeInTheDocument();
    await user.selectOptions(centre, "Coastal Fire Centre");
    expect(screen.getByText("6 of 13 records shown")).toBeInTheDocument();
    await user.click(screen.getAllByText("Record details")[0]!);
    expect(screen.getByText("Size 2 hectares")).toBeInTheDocument();

    view.rerender(<LiveAnalysisWorkspace session={session(results)} answerIdentity="two" />);
    await waitFor(() => expect(screen.getByRole("tab", { name: "Summary" })).toHaveAttribute("aria-selected", "true"));
    await user.click(screen.getByRole("tab", { name: "Records" }));
    expect(screen.getAllByLabelText("Fire centre").find((element) => element.tagName === "SELECT")).toHaveValue("");
  });

  it("opens every new analytical answer on Summary", () => {
    render(<LiveAnalysisWorkspace session={session(Array.from({ length: 13 }, (_, index) => incident(index)))} answerIdentity="one" />);
    expect(screen.getByRole("tab", { name: "Summary" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Map" })).toHaveAttribute("aria-selected", "false");
  });

  it("applies incident filters to map records without hiding non-incident layers or warnings", async () => {
    const user = userEvent.setup();
    const incidents = Array.from({ length: 13 }, (_, index) => incident(index));
    const evacuation: LiveResult = { ...incident(99), result_id: "evacuation:1", kind: "evacuation", status: "Order" };
    render(<LiveAnalysisWorkspace session={session(incidents, [...incidents, evacuation])} answerIdentity="one" />);
    await user.click(screen.getByRole("tab", { name: "Records" }));
    const centre = screen.getAllByLabelText("Fire centre").find((element) => element.tagName === "SELECT")!;
    await user.selectOptions(centre, "Coastal Fire Centre");
    await user.click(screen.getByRole("tab", { name: "Map" }));
    await waitFor(() => expect(screen.getByTestId("map-record-ids")).toHaveTextContent("evacuation:1"));
    expect(screen.getByTestId("map-record-ids")).toHaveTextContent("incident:1");
    expect(screen.getByTestId("map-record-ids")).not.toHaveTextContent("incident:0");
    expect(screen.getByTestId("map-unavailable")).toHaveTextContent("evacuations");
  });
});
