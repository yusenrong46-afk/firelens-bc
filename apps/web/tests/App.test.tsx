import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";
import { App } from "../src/app/App";
import { wrapAppFetch } from "./fetchStub";

const answer = {
  status: "answer",
  response_mode: "grounded",
  trace_id: "trace-123",
  answer: "Keep water and food in a grab-and-go bag.",
  suggested_questions: ["How often should I review my emergency plan?"],
  claims: [
    {
      claim_id: "C1",
      text: "Keep water and food in a grab-and-go bag.",
      evidence_status: "verified_corpus",
      supports: [{ evidence_id: "E1", quote: "Food & water" }],
      publication: {
        kind: "source_linked_explanation",
        review_status: "source_linked",
        renderer_id: "firelens.explanation_renderer.v1",
        support_provenance: "validated_grounded_explanation",
      },
    },
  ],
  evidence: [
    {
      evidence_id: "E1",
      title: "Wildfire Preparedness Guide",
      publisher: "PreparedBC",
      canonical_url: "https://example.test/guide.pdf",
      locator: "PDF page 5",
      temporal_class: "stable_guidance",
      review_provenance: "human_verified_repair",
      primary_text: "Grab-and-Go Bag: Food & water",
      context_text: "Grab-and-Go Bag: Food & water and emergency supplies.",
    },
  ],
  limitations: ["Stable guidance only."],
  validation: {
    accepted: true,
    schema_valid: true,
    citation_ids_valid: true,
    quotes_exact: true,
    policy_valid: true,
    errors: [],
  },
};

function askCallOptions(fetchMock: ReturnType<typeof vi.fn>): RequestInit[] {
  return fetchMock.mock.calls
    .filter(([url]) => url === "/api/v1/ask")
    .map((call) => call[1] as RequestInit);
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("FireLens Source Lens", () => {
  it("explains the publication boundary without covering the product", async () => {
    render(<App />);
    const user = userEvent.setup();
    const trigger = screen.getByRole("button", { name: "How FireLens works" });
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    await user.click(trigger);
    const employerPanel = screen.getByRole("region", {
      name: "How FireLens works",
    });
    expect(employerPanel).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "How FireLens works" })).toHaveFocus();
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(employerPanel).toHaveAttribute("id", "how-firelens-works");
    expect(screen.getByText("Official records")).toBeInTheDocument();
    expect(screen.getByText(/not emergency advice/i)).toBeInTheDocument();
    expect(screen.getByLabelText("Ask FireLens a question")).toBeEnabled();
    await user.click(screen.getByLabelText("Ask FireLens a question"));
    expect(screen.getByLabelText("Ask FireLens a question")).toHaveFocus();
    await user.click(screen.getByRole("button", { name: "Close how FireLens works" }));
    expect(screen.queryByRole("region", { name: "How FireLens works" })).not.toBeInTheDocument();
    expect(trigger).toHaveAttribute("aria-expanded", "false");
  });

  it("exposes only the public same-origin OpenAPI contract", async () => {
    render(<App />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "How FireLens works" }));

    expect(screen.queryByRole("link", { name: /Repository/i })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /OpenAPI contract/i })).toHaveAttribute(
      "href",
      "/openapi.json",
    );
  });

  it("does not enter the analytical shell from question wording while loading", async () => {
    let resolveAsk!: (response: Response) => void;
    vi.stubGlobal("fetch", wrapAppFetch( vi.fn().mockImplementation(() => new Promise<Response>((resolve) => {
      resolveAsk = resolve;
    }))));
    const user = userEvent.setup();
    render(<App />);

    await user.type(
      screen.getByLabelText("Ask FireLens a question"),
      "Show wildfire distribution by status across B.C.",
    );
    await user.click(screen.getByLabelText("Send question"));

    expect(screen.getByText("Preparing your response…")).toBeInTheDocument();
    expect(document.querySelector("main.workspace--analysis")).not.toBeInTheDocument();

    resolveAsk(new Response(JSON.stringify({
      status: "answer",
      response_mode: "live",
      presentation_shell: "analysis",
      provenance_class: "official_live",
      trace_id: "trace-pending-analysis",
      answer: "Two official incident records are in this bounded result.",
      claims: [],
      evidence: [],
      limitations: [],
      live_results: [
        {
          result_id: "incident:pending-1",
          kind: "incident",
          authority: "BC Wildfire Service",
          source_url: "https://example.test/pending-1",
          source_updated_at: "2026-08-23T12:00:00Z",
          retrieved_at: "2026-08-23T12:01:00Z",
          freshness: "fresh",
          status: "Being Held",
          fire_centre: "Kamloops Fire Centre",
          geometry: { type: "Point", coordinates: [-119.5, 49.9] },
        },
        {
          result_id: "incident:pending-2",
          kind: "incident",
          authority: "BC Wildfire Service",
          source_url: "https://example.test/pending-2",
          source_updated_at: "2026-08-23T12:00:00Z",
          retrieved_at: "2026-08-23T12:01:00Z",
          freshness: "fresh",
          status: "Out of Control",
          fire_centre: "Coastal Fire Centre",
          geometry: { type: "Point", coordinates: [-123.1, 49.3] },
        },
      ],
    }), { status: 200 }));
    expect(await screen.findByRole("region", { name: "Analysis view" })).toBeInTheDocument();
  });

  it("switches multi-record analytical questions into summary and records views", async () => {
    const liveResults = [
      { result_id: "incident:1", fire_centre: "Kamloops Fire Centre", status: "Out of Control" },
      { result_id: "incident:2", fire_centre: "Kamloops Fire Centre", status: "Being Held" },
      { result_id: "incident:3", fire_centre: "Coastal Fire Centre", status: "Under Control" },
    ].map((item) => ({
      ...item,
      kind: "incident",
      authority: "BC Wildfire Service",
      source_url: `https://example.test/${item.result_id}`,
      source_updated_at: "2026-08-23T12:00:00Z",
      retrieved_at: "2026-08-23T12:01:00Z",
      freshness: "fresh",
      geometry: { type: "Point", coordinates: [-119.5, 49.9] },
    }));
    vi.stubGlobal("fetch", wrapAppFetch( vi.fn().mockResolvedValue(new Response(JSON.stringify({
      status: "answer",
      response_mode: "live",
      presentation_shell: "analysis",
      provenance_class: "official_live",
      roster_total: 3,
      sample_record_ids: ["incident:1", "incident:2", "incident:3"],
      trace_id: "trace-analysis",
      answer: "Three official incident records are in this bounded result.",
      suggested_questions: [],
      claims: answer.claims,
      evidence: answer.evidence,
      limitations: ["FireLens could not verify evacuation records for this request."],
      live_results: liveResults,
      aggregate_freshness: "fresh",
      validation: { accepted: true },
    }), { status: 200 }))));
    const { container } = render(<App />);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Ask FireLens a question"), "Show wildfire distribution by status across B.C.");
    await user.click(screen.getByLabelText("Send question"));

    expect(await screen.findByRole("region", { name: "Analysis view" })).toBeInTheDocument();
    const shortAnswer = screen.getByText(
      "Three official incident records are in this bounded result.",
    );
    const analysisRegion = screen.getByRole("region", { name: "Analysis view" });
    expect(shortAnswer.compareDocumentPosition(analysisRegion) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(analysisRegion.closest(".analysis-surface-slot")).toBeInTheDocument();
    expect(analysisRegion.closest(".conversation-scroll")).not.toBeInTheDocument();
    expect(document.querySelector(".conversation-scroll")).not.toHaveAttribute("aria-live");
    expect(screen.getByText("FireLens response ready.")).toBeInTheDocument();
    expect(screen.getByLabelText("Clear conversation history")).toHaveTextContent("New conversation");
    expect(screen.getByLabelText("Response feedback")).toBeInTheDocument();
    expect(screen.getByText("B.C. wildfire intelligence")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Official map/i })).toHaveAttribute(
      "href",
      "https://wildfiresituation.nrs.gov.bc.ca/map",
    );
    expect(screen.queryByRole("button", { name: "Show these on the map" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Open map" })).not.toBeInTheDocument();
    const analysisView = screen.getByRole("region", { name: "Analysis view" });
    expect(within(analysisView).getByLabelText("Analysis limitations")).toHaveTextContent("FireLens could not verify evacuation records for this request.");
    expect(within(analysisView).getByRole("heading", { name: "Analysis view" })).toHaveAttribute("data-surface-visually-hidden", "true");
    expect(screen.getByRole("tab", { name: "Summary" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Map" })).toHaveAttribute("aria-selected", "false");
    expect(screen.getByRole("tab", { name: "Records" })).toHaveAttribute("aria-selected", "false");
    expect(await screen.findByRole("heading", { name: "Incident records by fire centre" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Official wildfire records map" })).not.toBeInTheDocument();
    await user.click(screen.getByText("Method", { exact: true }));
    const technicalEvidence = screen.getByRole("button", { name: "Inspect answer evidence" });
    await user.click(technicalEvidence);
    const answerContext = screen.getByRole("complementary", { name: "Source for this statement" });
    expect(answerContext).toHaveFocus();
    expect(screen.queryByRole("group", { name: "Choose answer context" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Close answer context" }));
    expect(technicalEvidence).toHaveFocus();
    expect(technicalEvidence).toHaveAttribute("aria-expanded", "false");
    await user.click(screen.getByRole("tab", { name: "Records" }));
    expect(screen.getByRole("region", { name: "Incident records returned for this request" })).toHaveTextContent("3 of 3 records shown");
    expect(screen.queryByRole("region", { name: "Official wildfire records map" })).not.toBeInTheDocument();
    const accessibility = await axe(container);
    expect(accessibility.violations).toEqual([]);
  });

  it("keeps an operation-specific backend answer above multi-record analysis", async () => {
    const liveResults = [
      { result_id: "incident:freshness-1", source_updated_at: "2026-08-23T12:00:00Z" },
      { result_id: "incident:freshness-2", source_updated_at: "2026-08-22T18:00:00Z" },
    ].map((item) => ({
      ...item,
      kind: "incident",
      authority: "BC Wildfire Service",
      source_url: `https://example.test/${item.result_id}`,
      retrieved_at: "2026-08-23T12:01:00Z",
      freshness: "fresh",
      status: "Being Held",
      fire_centre: "Kamloops Fire Centre",
      geometry: { type: "Point", coordinates: [-119.5, 49.9] },
    }));
    const operationAnswer = "Source updates range from August 22 to August 23; both records were retrieved at 12:01 UTC.";
    vi.stubGlobal("fetch", wrapAppFetch( vi.fn().mockResolvedValue(new Response(JSON.stringify({
      status: "answer",
      response_mode: "live",
      presentation_shell: "analysis",
      provenance_class: "official_live",
      trace_id: "trace-analysis-operation-answer",
      answer: operationAnswer,
      suggested_questions: [],
      claims: [],
      evidence: [],
      limitations: [],
      live_results: liveResults,
      aggregate_freshness: "fresh",
      validation: { accepted: true },
    }), { status: 200 }))));

    render(<App />);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Ask FireLens a question"), "How fresh are these wildfire records?");
    await user.click(screen.getByLabelText("Send question"));

    expect(await screen.findByRole("region", { name: "Analysis view" })).toBeInTheDocument();
    expect(screen.getByText(operationAnswer)).toBeInTheDocument();
    expect(screen.queryByText(/This answer includes 2 fetched official incident records/i)).not.toBeInTheDocument();
  });

  it("keeps a deterministic records analysis but omits a useless map", async () => {
    const liveResults = [
      { result_id: "incident:no-map-1", fire_centre: "Coastal Fire Centre", status: "Being Held" },
      { result_id: "incident:no-map-2", fire_centre: "Kamloops Fire Centre", status: "Out of Control" },
    ].map((item) => ({
      ...item,
      kind: "incident",
      authority: "BC Wildfire Service",
      source_url: `https://example.test/${item.result_id}`,
      source_updated_at: "2026-08-23T12:00:00Z",
      retrieved_at: "2026-08-23T12:01:00Z",
      freshness: "fresh",
    }));
    vi.stubGlobal("fetch", wrapAppFetch( vi.fn().mockResolvedValue(new Response(JSON.stringify({
      status: "answer",
      response_mode: "live",
      presentation_shell: "analysis",
      provenance_class: "official_live",
      trace_id: "trace-analysis-no-map",
      answer: "Two official incident records are in this bounded result.",
      suggested_questions: [],
      claims: [],
      evidence: [],
      limitations: [
        "FireLens uses official records and is not a safety assessment.",
        "FireLens uses official records and is not a safety assessment.",
      ],
      live_results: liveResults,
      aggregate_freshness: "fresh",
      validation: { accepted: true },
    }), { status: 200 }))));

    render(<App />);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Ask FireLens a question"), "Compare the returned wildfire records");
    await user.click(screen.getByLabelText("Send question"));

    const analysisView = await screen.findByRole("region", { name: "Analysis view" });
    expect(within(analysisView).queryByRole("tab", { name: "Map" })).not.toBeInTheDocument();
    expect(within(analysisView).getByRole("tab", { name: "Summary" })).toBeInTheDocument();
    expect(within(analysisView).getByRole("tab", { name: "Records" })).toBeInTheDocument();
    const fireCentreTotals = within(analysisView).getByLabelText("Fire-centre record totals");
    expect(fireCentreTotals).toHaveTextContent("Coastal1");
    expect(fireCentreTotals).toHaveTextContent("Kamloops1");
    expect(within(analysisView).queryByLabelText("Analysis limitations")).not.toBeInTheDocument();
    expect(within(analysisView).getByText("Limits", { exact: true })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Show these on the map" })).not.toBeInTheDocument();
  });

  it("keeps mixed live-plus-guidance answers in chat without auto-opening a province map", async () => {
    const liveResults = [
      { result_id: "incident:mix-1", fire_centre: "Kamloops Fire Centre", status: "Out of Control" },
      { result_id: "incident:mix-2", fire_centre: "Coastal Fire Centre", status: "Being Held" },
    ].map((item) => ({
      ...item,
      kind: "incident",
      authority: "BC Wildfire Service",
      source_url: `https://example.test/${item.result_id}`,
      source_updated_at: "2026-08-23T12:00:00Z",
      retrieved_at: "2026-08-23T12:01:00Z",
      freshness: "fresh",
      geometry: { type: "Point", coordinates: [-119.5, 49.9] },
    }));
    vi.stubGlobal("fetch", wrapAppFetch(vi.fn().mockResolvedValue(new Response(JSON.stringify({
      status: "answer",
      response_mode: "mixed",
      presentation_shell: "chat",
      provenance_class: "mixed",
      roster_total: 2,
      sample_record_ids: ["incident:mix-1", "incident:mix-2"],
      trace_id: "trace-mixed-chat",
      answer: "Official records are listed below. Keep water and food in a grab-and-go bag.",
      answer_sections: [
        { kind: "current_records", heading: "Current official records", text: "Two official incident records are in this bounded result." },
        { kind: "reviewed_guidance", heading: "Reviewed preparedness guidance", text: "Keep water and food in a grab-and-go bag." },
      ],
      claims: answer.claims,
      evidence: answer.evidence,
      limitations: [],
      live_results: liveResults,
      aggregate_freshness: "fresh",
      validation: { accepted: true },
    }), { status: 200 }))));
    render(<App />);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Ask FireLens a question"), "Current wildfire records, and what should I pack?");
    await user.click(screen.getByLabelText("Send question"));

    expect(await screen.findByText("Current official records")).toBeInTheDocument();
    expect(screen.getByText("Reviewed preparedness guidance")).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Analysis view" })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Official wildfire records map" })).not.toBeInTheDocument();
    expect(document.querySelector("main.workspace--analysis")).not.toBeInTheDocument();
  });

  it("opens literal map requests as context and restores focus when closed", async () => {
    const liveResult = {
      result_id: "incident:map-request",
      kind: "incident",
      authority: "BC Wildfire Service",
      source_url: "https://example.test/incidents/map-request",
      source_updated_at: "2026-08-23T12:00:00Z",
      retrieved_at: "2026-08-23T12:01:00Z",
      freshness: "fresh",
      status: "Being Held",
      name: "Mountain Fire",
      geometry: { type: "Point", coordinates: [-119.5, 49.9] },
    };
    vi.stubGlobal("fetch", wrapAppFetch( vi.fn().mockImplementation((url: string) => Promise.resolve(
      new Response(JSON.stringify(String(url).startsWith("/api/v1/live/map") ? {
        generated_at: "2026-08-23T12:01:00Z",
        results: [liveResult],
        unavailable_layers: [],
        limitations: [],
      } : {
        status: "answer",
        response_mode: "live",
        presentation_shell: "spatial",
        provenance_class: "official_live",
        resolved_location: { latitude: 49.9, longitude: -119.5 },
        trace_id: "trace-explicit-map",
        answer: "Mountain Fire is Being Held.",
        claims: [],
        evidence: [],
        limitations: [],
        live_results: [liveResult],
      }), { status: 200 }),
    ))));
    const user = userEvent.setup();
    render(<App />);
    await user.type(screen.getByLabelText("Ask FireLens a question"), "Show Mountain Fire on the map");
    const sendButton = screen.getByLabelText("Send question");
    await user.click(sendButton);

    const mapContext = await screen.findByRole("complementary", { name: "Map" });
    expect(mapContext).toHaveFocus();
    await user.click(screen.getByRole("button", { name: "Close answer context" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Open map" })).toHaveFocus());
  });

  it("starts with a task-first question workspace and keeps the map optional", async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify({
      generated_at: "2026-08-23T12:00:00Z",
      results: [],
      unavailable_layers: [],
    }), { status: 200 })));
    vi.stubGlobal("fetch", wrapAppFetch( fetchMock));
    const user = userEvent.setup();
    render(<App />);
    expect(screen.getAllByRole("link", { name: /FireLens home/ }).length).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { name: "What do you want to know about wildfires in B.C.?" })).toBeInTheDocument();
    expect(await screen.findByText(/lists 12 fires in B\.C\./)).toBeInTheDocument();
    expect(screen.getByText(/3 evacuation orders and alerts/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Browse guided questions" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "How FireLens works" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "How it works" })).toBeInTheDocument();
    expect(screen.getByText(/FireLens provides information, not decisions/)).toBeInTheDocument();
    expect(screen.queryByText("Start with an example")).not.toBeInTheDocument();
    expect(screen.queryByText("0 of 6 turns in context")).not.toBeInTheDocument();
    expect(screen.queryByText("No earlier turns in context")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Skip to conversation" })).toHaveAttribute("href", "#conversation");
    expect(screen.queryByRole("region", { name: "Official wildfire records map" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Skip to official map" })).not.toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Explore live map" }));
    expect(await screen.findByRole("region", { name: "Official wildfire records map" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Skip to official map" })).toHaveAttribute("href", "#official-map");
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/live/map?layers=incidents,perimeters,evacuations",
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    ));
  });

  it("scrolls the assistant reply into view after an answer", async () => {
    const scrollIntoView = vi.fn();
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
      configurable: true,
      writable: true,
      value: scrollIntoView,
    });
    vi.stubGlobal("fetch", wrapAppFetch( vi.fn().mockResolvedValue(new Response(JSON.stringify(answer), { status: 200 }))));
    const user = userEvent.setup();
    render(<App />);
    await user.type(screen.getByLabelText("Ask FireLens a question"), "What belongs in a grab-and-go bag?");
    await user.click(screen.getByLabelText("Send question"));
    expect(
      await screen.findByLabelText("Question and answer"),
    ).toHaveTextContent("Keep water and food in a grab-and-go bag.");
    expect(scrollIntoView).toHaveBeenCalled();
  });

  it("warns when the browser is offline and recovers when connectivity returns", async () => {
    render(<App />);
    expect(screen.queryByText(/You're offline/)).not.toBeInTheDocument();
    window.dispatchEvent(new Event("offline"));
    expect(await screen.findByRole("status", { name: "Connection status" })).toHaveTextContent(/offline/i);
    window.dispatchEvent(new Event("online"));
    await waitFor(() => {
      expect(screen.queryByRole("status", { name: "Connection status" })).not.toBeInTheDocument();
    });
  });

  it("renders a capability response with API suggestions and no evidence", async () => {
    vi.stubGlobal("fetch", wrapAppFetch( vi.fn().mockResolvedValue(
      new Response(JSON.stringify({
        status: "answer",
        response_mode: "capability",
        trace_id: "trace-capability",
        answer: "I can help you explore reviewed wildfire preparedness guidance.",
        suggested_questions: ["How should I prepare a household emergency plan?"],
        claims: [],
        evidence: [],
        limitations: [],
      }), { status: 200 }),
    )));
    const user = userEvent.setup();
    render(<App />);
    await user.type(screen.getByLabelText("Ask FireLens a question"), "What can you help me with?");
    await user.click(screen.getByLabelText("Send question"));

    expect(await screen.findByText("FireLens topics")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "How should I prepare a household emergency plan?" })).toBeInTheDocument();
    expect(screen.queryByText("Retrieved passage")).not.toBeInTheDocument();
    expect(screen.queryByRole("complementary", { name: "Map" })).not.toBeInTheDocument();
    expect(screen.queryByRole("complementary", { name: "Sources" })).not.toBeInTheDocument();
    expect(screen.queryByRole("complementary", { name: "Source for this statement" })).not.toBeInTheDocument();
  });

  it("renders optional authority-labelled answer sections", async () => {
    vi.stubGlobal("fetch", wrapAppFetch( vi.fn().mockResolvedValue(
      new Response(JSON.stringify({
        status: "answer",
        response_mode: "mixed",
        trace_id: "trace-sections",
        answer: "Current records are available; general context follows.",
        answer_sections: [
          { kind: "current_records", heading: "Current official records", text: "The official record is available." },
          { kind: "general_background", heading: "General background", text: "This context is not a live official record." },
        ],
        claims: [{
          claim_id: "C1",
          text: "This context is not a live official record.",
          evidence_status: "general_background",
          supports: [],
          publication: {
            kind: "general_background",
            review_status: "generated_background",
            renderer_id: "none",
            support_provenance: "validated_background_generation",
          },
        }],
        evidence: [],
        limitations: ["General background — not verified against the FireLens corpus."],
        live_results: [{
          result_id: "incident:sections",
          kind: "incident",
          authority: "BC Wildfire Service",
          source_url: "https://example.test/incidents/sections",
          source_updated_at: "2026-08-13T18:55:00Z",
          retrieved_at: "2026-08-13T19:00:00Z",
          freshness: "fresh",
          status: "Being Held",
          name: "Section Fire",
          geometry_relation: "nearby",
          geometry: { type: "Point", coordinates: [-119.5, 49.89] },
        }],
        aggregate_freshness: "fresh",
        validation: { accepted: true },
      }), { status: 200 }),
    )));
    const user = userEvent.setup();
    render(<App />);
    await user.type(screen.getByLabelText("Ask FireLens a question"), "What is happening?");
    await user.click(screen.getByLabelText("Send question"));

    expect((await screen.findAllByText("Current official records")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Current official records").length).toBeGreaterThan(0);
    expect(screen.getAllByText("General background").length).toBeGreaterThan(0);
    expect(screen.queryByText("Current records are available; general context follows.")).not.toBeInTheDocument();
    const labelledAnswer = screen.getByLabelText("Authority-labelled answer");
    expect(within(labelledAnswer).getAllByText("The official record is available.")).toHaveLength(1);
    expect(within(labelledAnswer).getAllByText("This context is not a live official record.")).toHaveLength(1);
    expect(screen.getByText("Official records and general knowledge")).toBeInTheDocument();
    expect(screen.getByText("Each statement and its source")).toBeInTheDocument();
  });

  it("keeps reviewed-source conflicts visible beside live records", async () => {
    vi.stubGlobal("fetch", wrapAppFetch( vi.fn().mockResolvedValue(
      new Response(JSON.stringify({
        ...answer,
        response_mode: "mixed",
        trace_id: "trace-mixed-conflict",
        answer: "A current record is available, but the reviewed guidance conflicts.",
        answer_sections: [
          { kind: "current_records", heading: "Current official records", text: "Current official information: Section Fire is Being Held." },
          { kind: "conflicting_guidance", heading: "Sources disagree", text: "The reviewed sources disagree; inspect both before acting." },
        ],
        reason_code: "conflicting_evidence",
        live_results: [{
          result_id: "incident:conflict",
          kind: "incident",
          authority: "BC Wildfire Service",
          source_url: "https://example.test/incidents/conflict",
          source_updated_at: "2026-08-13T18:55:00Z",
          retrieved_at: "2026-08-13T19:00:00Z",
          freshness: "fresh",
          status: "Being Held",
          name: "Section Fire",
          geometry_relation: "nearby",
          geometry: { type: "Point", coordinates: [-119.5, 49.89] },
        }],
        aggregate_freshness: "fresh",
      }), { status: 200 }),
    )));
    const user = userEvent.setup();
    render(<App />);
    await user.type(screen.getByLabelText("Ask FireLens a question"), "Show this fire and explain the conflicting guidance.");
    await user.click(screen.getByLabelText("Send question"));

    expect(await screen.findByText("Official records; sources disagree")).toBeInTheDocument();
    expect(screen.getAllByText("Sources disagree").length).toBeGreaterThan(0);
    expect(screen.getByText("The reviewed sources disagree; inspect both before acting.")).toBeInTheDocument();
  });

  it("renders a verified answer and its local evidence", async () => {
    vi.stubGlobal("fetch", wrapAppFetch( vi.fn().mockResolvedValue(
      new Response(JSON.stringify(answer), { status: 200 }),
    )));
    const user = userEvent.setup();
    render(<App />);
    await user.type(screen.getByLabelText("Ask FireLens a question"), "What goes in a grab-and-go bag?");
    await user.click(screen.getByLabelText("Send question"));

    expect(await screen.findByText("Each statement and its source")).toBeInTheDocument();
    expect(screen.getByText("From reviewed guidance")).toBeInTheDocument();
    expect(screen.getAllByText("Keep water and food in a grab-and-go bag.").length).toBeGreaterThan(1);
    expect(screen.getAllByText("Food & water").some((node) => node.tagName === "MARK")).toBe(true);
    expect(screen.getAllByText("PreparedBC").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Human-verified source transcription").length).toBeGreaterThan(0);
    expect(screen.queryByRole("region", { name: "Official wildfire records map" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Show these on the map" })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Analysis view" })).not.toBeInTheDocument();
  });

  it("renders labelled background without an evidence interaction", async () => {
    const backgroundClaim = "Embers can travel ahead of a wildfire front.";
    vi.stubGlobal("fetch", wrapAppFetch( vi.fn().mockResolvedValue(
      new Response(JSON.stringify({
        status: "answer",
        response_mode: "background",
        presentation_shell: "chat",
        provenance_class: "general_knowledge",
        trace_id: "trace-background",
        answer: backgroundClaim,
        suggested_questions: [],
        claims: [{
          claim_id: "C1",
          text: backgroundClaim,
          evidence_status: "general_background",
          supports: [],
        }],
        evidence: [],
        limitations: ["General background — not verified against the FireLens corpus."],
      }), { status: 200 }),
    )));
    const user = userEvent.setup();
    render(<App />);
    await user.type(screen.getByLabelText("Ask FireLens a question"), "Why can embers be dangerous?");
    await user.click(screen.getByLabelText("Send question"));

    expect(await screen.findByText("General knowledge")).toBeInTheDocument();
    expect(screen.getByText(/General knowledge — not checked against FireLens sources|General model knowledge/)).toBeInTheDocument();
    expect(screen.queryByText("Official records. Not a safety assessment.")).not.toBeInTheDocument();
    expect(screen.queryByText("Each statement and its source")).not.toBeInTheDocument();
    expect(screen.queryByText("Important limits")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: backgroundClaim })).not.toBeInTheDocument();
    expect(screen.queryByText("Retrieved passage")).not.toBeInTheDocument();
  });

  it.each(["partial", "background", "live"] as const)(
    "shows and deduplicates limitations for a %s answer",
    async (responseMode) => {
      const limitation = `Visible ${responseMode} limitation.`;
      const fetchMock = vi.fn().mockImplementation((url: string) => {
        if (url.startsWith("/api/v1/live/map")) {
          return Promise.resolve(new Response(JSON.stringify({
            generated_at: "2026-08-13T19:00:00Z",
            results: [],
            unavailable_layers: [],
            layer_statuses: [],
            limitations: [],
          }), { status: 200 }));
        }
        return Promise.resolve(new Response(JSON.stringify({
          status: "answer",
          response_mode: responseMode,
          trace_id: `trace-limit-${responseMode}`,
          answer: `Answer in ${responseMode} mode.`,
          claims: [],
          evidence: [],
          limitations: [limitation, "", limitation],
          live_results: [],
        }), { status: 200 }));
      });
      vi.stubGlobal("fetch", wrapAppFetch( fetchMock));
      const user = userEvent.setup();
      render(<App />);

      await user.type(screen.getByLabelText("Ask FireLens a question"), `Test ${responseMode} limitations`);
      await user.click(screen.getByLabelText("Send question"));

      const limitations = await screen.findByLabelText("Answer limitations");
      expect(within(limitations).getAllByText(limitation)).toHaveLength(1);
      expect(within(limitations).getAllByRole("listitem")).toHaveLength(1);
      expect(screen.queryByLabelText("What FireLens established")).not.toBeInTheDocument();
      expect(screen.getAllByText(limitation)).toHaveLength(1);
      const conversation = screen.getByRole("region", { name: "Question and answer" });
      const answerText = within(conversation).getByText(`Answer in ${responseMode} mode.`);
      expect(limitations.compareDocumentPosition(answerText) & Node.DOCUMENT_POSITION_PRECEDING).toBeTruthy();
    },
  );

  it("keeps unsupported live requests useful with an official next link", async () => {
    vi.stubGlobal("fetch", wrapAppFetch( vi.fn().mockResolvedValue(
      new Response(JSON.stringify({
        status: "answer",
        response_mode: "scope_redirect",
        trace_id: "trace-related-service",
        answer: "FireLens is not connected to current air quality, so it cannot verify that value here.",
        claims: [],
        evidence: [],
        limitations: [],
        related_links: [{
          title: "Current B.C. AQHI",
          url: "https://weather.gc.ca/airquality/pages/provincial_summary/bc_e.html",
          description: "Environment Canada current AQHI observations and forecasts.",
        }],
        resolved_location: { latitude: 49.89, longitude: -119.5 },
      }), { status: 200 }),
    )));
    const user = userEvent.setup();
    render(<App />);
    await user.type(screen.getByLabelText("Ask FireLens a question"), "What is the current air quality in Kelowna?");
    await user.click(screen.getByLabelText("Send question"));

    expect(await screen.findByText("Official source elsewhere")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /Current B.C. AQHI/ })[0]).toHaveAttribute(
      "href",
      "https://weather.gc.ca/airquality/pages/provincial_summary/bc_e.html",
    );
    expect(screen.queryByRole("region", { name: "Official wildfire records map" })).not.toBeInTheDocument();
    expect(screen.queryByText("FireLens did not generate guidance")).not.toBeInTheDocument();
  });

  it("renders a typed abstention without evidence", async () => {
    vi.stubGlobal("fetch", wrapAppFetch( vi.fn().mockResolvedValue(
      new Response(JSON.stringify({
        status: "abstention",
        response_mode: "abstention",
        trace_id: "trace-live",
        answer: "This question requires current official information.",
        suggested_questions: [],
        claims: [],
        evidence: [],
        limitations: ["Static guidance cannot establish current status."],
        reason_code: "live_data_required",
      }), { status: 200 }),
    )));
    const user = userEvent.setup();
    render(<App />);
    await user.type(screen.getByLabelText("Ask FireLens a question"), "Is a fire active near me right now?");
    await user.click(screen.getByLabelText("Send question"));

    expect(await screen.findByText("FireLens did not generate guidance")).toBeInTheDocument();
    expect(screen.getAllByText("Current source unavailable").length).toBeGreaterThan(0);
    expect(screen.getByText("Static guidance cannot establish current status.")).toBeInTheDocument();
    expect(screen.queryByText(/live_data_required/)).not.toBeInTheDocument();
    expect(screen.queryByText("Each statement and its source")).not.toBeInTheDocument();
  });

  it("labels a personal-safety abstention and exposes its actual official handoff", async () => {
    const officialUrl = "https://www.emergencyinfobc.gov.bc.ca/";
    vi.stubGlobal("fetch", wrapAppFetch( vi.fn().mockResolvedValue(
      new Response(JSON.stringify({
        status: "abstention",
        response_mode: "abstention",
        trace_id: "trace-safety-boundary",
        answer: "FireLens cannot decide whether you should evacuate.",
        claims: [],
        evidence: [],
        limitations: ["Follow instructions from the issuing authority."],
        reason_code: "personalized_safety_decision",
        related_links: [{
          title: "EmergencyInfoBC current evacuation information",
          url: officialUrl,
          description: "Current evacuation notices from issuing authorities.",
        }],
      }), { status: 200 }),
    )));
    const user = userEvent.setup();
    render(<App />);
    await user.type(screen.getByLabelText("Ask FireLens a question"), "Should I evacuate now?");
    await user.click(screen.getByLabelText("Send question"));

    expect(await screen.findByText("Personal safety boundary")).toBeInTheDocument();
    expect(screen.getByText("FireLens cannot decide whether you should evacuate.")).toBeInTheDocument();
    expect(screen.getByText("EmergencyInfoBC current evacuation information")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Open official source/ })).toHaveAttribute("href", officialUrl);
    expect(screen.queryByText(/Use the official-current-information link/)).not.toBeInTheDocument();
  });

  it("renders official live records in the map panel", async () => {
    const liveResult = {
      result_id: "incident:7",
      kind: "incident",
      authority: "BC Wildfire Service",
      source_url: "https://example.test/incidents/7",
      source_updated_at: "2026-07-28T11:55:00Z",
      retrieved_at: "2026-07-28T12:00:00Z",
      freshness: "fresh",
      status: "Out of Control",
      name: "Test Fire",
      geometry_relation: "nearby",
      geometry: { type: "Point", coordinates: [-123.5, 49.5] },
    };
    vi.stubGlobal("fetch", wrapAppFetch( vi.fn().mockImplementation((url: string) => {
      if (String(url).startsWith("/api/v1/live/map")) {
        return Promise.resolve(new Response(JSON.stringify({
          generated_at: "2026-07-28T12:00:00Z",
          results: [liveResult],
          aggregate_freshness: "fresh",
          unavailable_layers: ["evacuation"],
          layer_statuses: [],
          limitations: [],
        }), { status: 200 }));
      }
      return Promise.resolve(new Response(JSON.stringify({
        status: "answer",
        response_mode: "live",
        trace_id: "trace-live-map",
        answer: "Current official information: Test Fire is Out of Control.",
        claims: [],
        evidence: [],
        limitations: ["No matching record is not a safety determination."],
        live_results: [liveResult],
        unavailable_layers: ["evacuation"],
      }), { status: 200 }));
    })));
    const user = userEvent.setup();
    const { container } = render(<App />);
    await user.type(screen.getByLabelText("Ask FireLens a question"), "Is there an active wildfire now?");
    await user.click(screen.getByLabelText("Send question"));
    await user.click(await screen.findByRole("button", { name: "Show these on the map" }));

    expect(await screen.findByText("Wildfires in B.C. right now")).toBeInTheDocument();
    expect(screen.getAllByText("Official records").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Test Fire").length).toBeGreaterThan(0);
    const matchingList = screen.getByRole("list", { name: "Matching this question" });
    const missingLayerWarning = screen.getByText(/Some official layers are unavailable: evacuation/);
    const map = screen.getByRole("region", { name: "Interactive map of official wildfire records" });
    expect(missingLayerWarning.compareDocumentPosition(matchingList) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(missingLayerWarning.compareDocumentPosition(map) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(map.compareDocumentPosition(matchingList) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getAllByText("Test Fire").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: /Test Fire Out of Control/ })).toHaveAccessibleName(/source updated/i);
    const accessibility = await axe(container);
    expect(accessibility.violations).toEqual([]);
  });

  it("derives map freshness from all displayed deduplicated records", async () => {
    const freshMatch = {
      result_id: "incident:fresh-match",
      kind: "incident",
      authority: "BC Wildfire Service",
      source_url: "https://example.test/incidents/fresh-match",
      source_updated_at: "2026-08-13T18:55:00Z",
      retrieved_at: "2026-08-13T19:00:00Z",
      freshness: "fresh",
      status: "Being Held",
      name: "Fresh Question Fire",
      geometry_relation: "nearby",
      geometry: { type: "Point", coordinates: [-119.5, 49.89] },
    };
    const staleProvinceRecord = {
      ...freshMatch,
      result_id: "incident:stale-province",
      source_url: "https://example.test/incidents/stale-province",
      freshness: "stale",
      name: "Stale Province Fire",
    };
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url.startsWith("/api/v1/live/map")) {
        return Promise.resolve(new Response(JSON.stringify({
          generated_at: "2026-08-13T19:00:00Z",
          results: [staleProvinceRecord],
          aggregate_freshness: "stale",
          unavailable_layers: [],
          layer_statuses: [],
          limitations: [],
        }), { status: 200 }));
      }
      return Promise.resolve(new Response(JSON.stringify({
        status: "answer",
        response_mode: "live",
        trace_id: "trace-combined-freshness",
        answer: "Fresh Question Fire is the matching official record.",
        claims: [],
        evidence: [],
        limitations: [],
        live_results: [freshMatch],
        aggregate_freshness: "fresh",
        unavailable_layers: [],
      }), { status: 200 }));
    });
    vi.stubGlobal("fetch", wrapAppFetch( fetchMock));
    const user = userEvent.setup();
    render(<App />);

    await user.type(screen.getByLabelText("Ask FireLens a question"), "Show the matching fire");
    await user.click(screen.getByLabelText("Send question"));

    expect((await screen.findAllByText("Fresh Question Fire is the matching official record.")).length).toBeGreaterThan(0);
    await user.click(await screen.findByRole("button", { name: "Show these on the map" }));
    expect(screen.getByRole("heading", { name: "Wildfires in B.C. right now", level: 1 })).toBeInTheDocument();
    expect(screen.queryByText("Stale Province Fire")).not.toBeInTheDocument();
    await user.click(screen.getByLabelText("Show all fires in B.C."));
    expect(await screen.findByRole("heading", { name: "Wildfires in B.C. (some records out of date)", level: 1 })).toBeInTheDocument();
    expect(screen.getByText(/cached copies because a refresh failed/)).toBeInTheDocument();
  });

  it("separates question matches from an interleaved, collapsible province roster", async () => {
    const matching = {
      result_id: "incident:match",
      kind: "incident",
      authority: "BC Wildfire Service",
      source_url: "https://example.test/incidents/match",
      source_updated_at: "2026-08-13T18:55:00Z",
      retrieved_at: "2026-08-13T19:00:00Z",
      freshness: "fresh",
      status: "Out of Control",
      name: "Question Fire",
      geometry_relation: "nearby",
      geometry: { type: "Point", coordinates: [-123.5, 49.5] },
    };
    const provinceResults = [
      { ...matching, result_id: "incident:province", name: "Province Fire" },
      { ...matching, result_id: "evacuation:province", kind: "evacuation", name: null, incident_number: "EA-7", status: "Alert" },
      { ...matching, result_id: "perimeter:province", kind: "perimeter", name: null, source_url: "https://services.arcgis.com/example/FeatureServer/0" },
    ];
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url.startsWith("/api/v1/live/map")) {
        return Promise.resolve(new Response(JSON.stringify({
          generated_at: "2026-08-13T19:00:00Z",
          results: provinceResults,
          aggregate_freshness: "fresh",
          unavailable_layers: [],
          layer_statuses: [],
          limitations: [],
        }), { status: 200 }));
      }
      return Promise.resolve(new Response(JSON.stringify({
        status: "answer",
        response_mode: "live",
        trace_id: "trace-partition",
        answer: "Question Fire is the matching official record.",
        claims: [],
        evidence: [],
        limitations: [],
        live_results: [matching],
        resolved_location: { latitude: 49.89, longitude: -119.5 },
        aggregate_freshness: "fresh",
        unavailable_layers: [],
      }), { status: 200 }));
    });
    vi.stubGlobal("fetch", wrapAppFetch( fetchMock));
    const user = userEvent.setup();
    render(<App />);

    await user.type(screen.getByLabelText("Ask FireLens a question"), "Where is Question Fire?");
    await user.click(screen.getByLabelText("Send question"));
    await user.click(await screen.findByRole("button", { name: "Show these on the map" }));

    expect(await screen.findByRole("heading", { name: "Matching this question", level: 2 })).toBeInTheDocument();
    const matchingList = screen.getByRole("list", { name: "Matching this question" });
    expect(within(matchingList).getByText("Question Fire")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Rest of B.C.", level: 2 })).not.toBeInTheDocument();
    await user.click(screen.getByLabelText("Show all fires in B.C."));
    expect(await screen.findByRole("heading", { name: "Rest of B.C.", level: 2 })).toBeInTheDocument();
    expect(screen.queryByText("Province Fire")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Show rest of B\.C\./ }));
    const provinceList = screen.getByRole("list", { name: "Rest of B.C." });
    const provinceNames = within(provinceList).getAllByRole("button").map((button) => button.querySelector("strong")?.textContent);
    expect(provinceNames).toEqual([
      "Province Fire",
      "Unnamed evacuation record EA-7",
      "Unnamed perimeter perimeter:province",
    ]);
    expect(within(provinceList).getByRole("link", { name: /Open GIS dataset/ })).toBeInTheDocument();
  });

  it("focuses the map from a named community without asking for location again", async () => {
    const mapResult = {
      result_id: "incident:far",
      kind: "incident",
      authority: "BC Wildfire Service",
      source_url: "https://example.test/incidents/far",
      source_updated_at: "2026-08-13T18:55:00Z",
      retrieved_at: "2026-08-13T19:00:00Z",
      freshness: "fresh",
      status: "Being Held",
      name: "Far Fire",
      geometry_relation: "unknown",
      geometry: { type: "Point", coordinates: [-125.0, 55.0] },
    };
    const nearbyResult = {
      ...mapResult,
      result_id: "incident:kelowna",
      name: "Kelowna Area Fire",
      status: "Out of Control",
      geometry: { type: "Point", coordinates: [-119.45, 49.9] },
    };
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url.startsWith("/api/v1/live/map")) {
        return Promise.resolve(new Response(JSON.stringify({
          generated_at: "2026-08-13T19:00:00Z",
          results: [mapResult],
          aggregate_freshness: "fresh",
          unavailable_layers: [],
          layer_statuses: [],
          limitations: [],
        }), { status: 200 }));
      }
      return Promise.resolve(new Response(JSON.stringify({
        status: "answer",
        response_mode: "live",
        trace_id: "trace-kelowna-map",
        answer: "Current official information: Kelowna Area Fire is Out of Control.",
        claims: [],
        evidence: [],
        limitations: [],
        live_results: [nearbyResult],
        aggregate_freshness: "fresh",
        unavailable_layers: [],
        resolved_location: { latitude: 49.89, longitude: -119.5 },
      }), { status: 200 }));
    });
    vi.stubGlobal("fetch", wrapAppFetch( fetchMock));
    const user = userEvent.setup();
    render(<App />);

    await user.type(screen.getByLabelText("Ask FireLens a question"), "Where are the fires in Kelowna?");
    await user.click(screen.getByLabelText("Send question"));
    await user.click(await screen.findByRole("button", { name: "Show these on the map" }));

    expect(await screen.findByText(/Approximate place marker near 49.89, -119.50/)).toBeInTheDocument();
    expect(screen.queryByText("One detail needed")).not.toBeInTheDocument();
    expect(screen.getAllByText("Kelowna Area Fire").length).toBeGreaterThan(0);
    const payload = JSON.parse(String(askCallOptions(fetchMock)[0]?.body));
    expect(payload.location).toBeUndefined();
  });

  it("asks for location only when a selected-fire distance task needs it", async () => {
    let askCount = 0;
    const mapResult = {
      result_id: "incident:7",
      kind: "incident",
      authority: "BC Wildfire Service",
      source_url: "https://example.test/incidents/7",
      source_updated_at: "2026-08-13T18:55:00Z",
      retrieved_at: "2026-08-13T19:00:00Z",
      freshness: "fresh",
      status: "Out of Control",
      name: "Mountain Fire",
      geometry_relation: "unknown",
      geometry: { type: "Point", coordinates: [-123.5, 49.5] },
    };
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url.startsWith("/api/v1/live/map")) {
        return Promise.resolve(new Response(JSON.stringify({
          generated_at: "2026-08-13T19:00:00Z",
          results: [mapResult],
          aggregate_freshness: "fresh",
          unavailable_layers: [],
          layer_statuses: [],
          limitations: [],
        }), { status: 200 }));
      }
      askCount += 1;
      if (askCount === 1) {
        return Promise.resolve(new Response(JSON.stringify({
          status: "answer",
          response_mode: "requires_input",
          trace_id: "trace-location",
          answer: "Share an approximate location or enter a BC community to continue.",
          claims: [],
          evidence: [],
          limitations: [],
          required_input: {
            kind: "location",
            prompt: "Use approximate location or enter a BC community.",
            continuation_question: "How far is this fire from me?",
          },
          selected_live_result_id: "incident:7",
        }), { status: 200 }));
      }
      return Promise.resolve(new Response(JSON.stringify({
        status: "answer",
        response_mode: "live",
        trace_id: "trace-distance",
        answer: "Mountain Fire is approximately 42.3 km away in a straight-line geodesic measurement.",
        claims: [],
        evidence: [],
        limitations: ["This is not driving distance or a safety assessment."],
        live_results: [{ ...mapResult, distance_km: 42.3, distance_basis: "incident_point" }],
        aggregate_freshness: "fresh",
        unavailable_layers: [],
        selected_live_result_id: "incident:7",
      }), { status: 200 }));
    });
    vi.stubGlobal("fetch", wrapAppFetch( fetchMock));
    const user = userEvent.setup();
    render(<App />);

    expect(screen.queryByLabelText("BC community for this question")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Explore live map" }));
    await user.click(await screen.findByRole("button", { name: /Mountain Fire.*Out of Control/ }));
    await user.type(screen.getByLabelText("Ask FireLens a question"), "How far is this fire from me?");
    await user.click(screen.getByLabelText("Send question"));

    expect(await screen.findByText("One detail needed")).toBeInTheDocument();
    expect(screen.getByLabelText("BC community for this question")).toHaveFocus();
    expect(screen.getByText("Use the community field above to continue this task. Type here only to start a new question.")).toBeInTheDocument();
    await user.type(screen.getByLabelText("BC community for this question"), "Vancouver");
    await user.click(screen.getByRole("button", { name: "Continue" }));
    expect((await screen.findAllByText(/approximately 42.3 km/)).length).toBeGreaterThan(0);

    const calls = askCallOptions(fetchMock);
    expect(JSON.parse(String(calls[0]?.body)).context.selected_live_result_id).toBe("incident:7");
    expect(JSON.parse(String(calls[1]?.body)).location).toEqual({ label: "Vancouver", radius_km: 50 });

    await user.type(screen.getByLabelText("Ask FireLens a question"), "What is a firebreak?");
    await user.click(screen.getByLabelText("Send question"));
    await waitFor(() => expect(askCallOptions(fetchMock)).toHaveLength(3));
    const laterPayload = JSON.parse(String(askCallOptions(fetchMock)[2]?.body));
    expect(laterPayload.location).toEqual({ label: "Vancouver", radius_km: 50 });
    expect(laterPayload.context?.selected_live_result_id).toBeUndefined();
  });

  it("retains the start-page community across later nearby live questions", async () => {
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url.startsWith("/api/v1/live/map")) {
        return Promise.resolve(new Response(JSON.stringify({
          generated_at: "2026-08-13T19:00:00Z",
          results: [],
          unavailable_layers: [],
          layer_statuses: [],
          limitations: [],
        }), { status: 200 }));
      }
      return Promise.resolve(new Response(JSON.stringify({
        ...answer,
        response_mode: "live",
        claims: [],
        evidence: [],
        answer: "Current official information: Kelowna-area records were returned.",
        live_results: [],
        aggregate_freshness: "fresh",
      }), { status: 200 }));
    });
    vi.stubGlobal("fetch", wrapAppFetch( fetchMock));
    const user = userEvent.setup();
    render(<App />);

    await user.type(screen.getByLabelText("BC community for a nearby lookup"), "Kelowna");
    await user.type(screen.getByLabelText("Ask FireLens a question"), "What official fires are near me?");
    await user.click(screen.getByLabelText("Send question"));
    expect(
      (await screen.findAllByText("Current official information: Kelowna-area records were returned.")).length,
    ).toBeGreaterThan(0);
    await user.type(screen.getByLabelText("Ask FireLens a question"), "Which official fires are still near me?");
    await user.click(screen.getByLabelText("Send question"));
    await waitFor(() => expect(askCallOptions(fetchMock)).toHaveLength(2));

    for (const call of askCallOptions(fetchMock)) {
      expect(JSON.parse(String(call.body)).location).toEqual({
        label: "Kelowna",
        radius_km: 50,
      });
    }
  });

  it("resumes a location continuation from the main composer", async () => {
    const fetchMock = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (url.startsWith("/api/v1/live/map")) {
        return Promise.resolve(new Response(JSON.stringify({
          generated_at: "2026-08-13T19:00:00Z",
          results: [],
          unavailable_layers: [],
          layer_statuses: [],
          limitations: [],
        }), { status: 200 }));
      }
      const payload = JSON.parse(String(init?.body ?? "{}")) as {
        question?: string;
        location?: { label?: string };
      };
      if (payload.location?.label === "Kelowna") {
        return Promise.resolve(new Response(JSON.stringify({
          status: "answer",
          response_mode: "live",
          trace_id: "trace-resumed",
          answer: "Current official information: Kelowna Area Fire is Being Held.",
          claims: [],
          evidence: [],
          limitations: [],
        }), { status: 200 }));
      }
      return Promise.resolve(new Response(JSON.stringify({
        status: "answer",
        response_mode: "requires_input",
        trace_id: "trace-location-composer",
        answer: "Share an approximate location or enter a BC community to continue.",
        claims: [],
        evidence: [],
        limitations: [],
        required_input: {
          kind: "location",
          prompt: "Use approximate location or enter a BC community.",
          continuation_question: "How close is the wildfire perimeter near me today?",
        },
      }), { status: 200 }));
    });
    vi.stubGlobal("fetch", wrapAppFetch( fetchMock));
    const user = userEvent.setup();
    render(<App />);
    await user.type(screen.getByLabelText("Ask FireLens a question"), "How close is the wildfire perimeter near me today?");
    await user.click(screen.getByLabelText("Send question"));
    expect(await screen.findByText("One detail needed")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Ask FireLens a question"), "Kelowna");
    await user.click(screen.getByLabelText("Send question"));
    expect(await screen.findByText(/Kelowna Area Fire/)).toBeInTheDocument();
    const resumed = JSON.parse(String(askCallOptions(fetchMock).at(-1)?.body));
    expect(resumed.question).toBe("How close is the wildfire perimeter near me today?");
    expect(resumed.location).toEqual({ label: "Kelowna", radius_km: 50 });
  });

  it("keeps a continuation location for later live questions and clears it with a new conversation", async () => {
    const fetchMock = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (url.startsWith("/api/v1/live/map")) {
        return Promise.resolve(new Response(JSON.stringify({
          generated_at: "2026-08-13T19:00:00Z",
          results: [],
          unavailable_layers: [],
          layer_statuses: [],
          limitations: [],
        }), { status: 200 }));
      }
      const payload = JSON.parse(String(init?.body ?? "{}")) as {
        location?: { label?: string; radius_km?: number };
      };
      if (!payload.location) {
        return Promise.resolve(new Response(JSON.stringify({
          status: "answer",
          response_mode: "requires_input",
          trace_id: "trace-needs-location",
          answer: "A community is needed to continue this live request.",
          claims: [],
          evidence: [],
          limitations: [],
          required_input: {
            kind: "location",
            prompt: "Use approximate location or enter a BC community.",
            continuation_question: "What official fires are near me?",
          },
        }), { status: 200 }));
      }
      return Promise.resolve(new Response(JSON.stringify({
        ...answer,
        response_mode: "live",
        trace_id: "trace-kelowna-live",
        answer: "Current official information: Kelowna-area records were returned.",
        claims: [],
        evidence: [],
        live_results: [],
        aggregate_freshness: "fresh",
      }), { status: 200 }));
    });
    vi.stubGlobal("fetch", wrapAppFetch( fetchMock));
    const user = userEvent.setup();
    render(<App />);

    await user.type(screen.getByLabelText("Ask FireLens a question"), "What official fires are near me?");
    await user.click(screen.getByLabelText("Send question"));
    expect(await screen.findByText("One detail needed")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Ask FireLens a question"), "Kelowna");
    await user.click(screen.getByLabelText("Send question"));
    await screen.findByText(/Kelowna-area records were returned/);

    await user.type(screen.getByLabelText("Ask FireLens a question"), "Which official fires are still near me?");
    await user.click(screen.getByLabelText("Send question"));
    await waitFor(() => expect(askCallOptions(fetchMock)).toHaveLength(3));
    const resumed = JSON.parse(String(askCallOptions(fetchMock)[1]?.body));
    const laterLiveQuestion = JSON.parse(String(askCallOptions(fetchMock)[2]?.body));
    expect(resumed.location).toEqual({ label: "Kelowna", radius_km: 50 });
    expect(laterLiveQuestion.location).toEqual({ label: "Kelowna", radius_km: 50 });

    await user.click(screen.getByLabelText("Clear conversation history"));
    await user.type(screen.getByLabelText("Ask FireLens a question"), "What official fires are near me?");
    await user.click(screen.getByLabelText("Send question"));
    await waitFor(() => expect(askCallOptions(fetchMock)).toHaveLength(4));
    const freshConversation = JSON.parse(String(askCallOptions(fetchMock)[3]?.body));
    expect(freshConversation.location).toBeUndefined();
  });

  it("does not treat a new question as a community label during location input", async () => {
    const fetchMock = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (url.startsWith("/api/v1/live/map")) {
        return Promise.resolve(new Response(JSON.stringify({
          generated_at: "2026-08-13T19:00:00Z",
          results: [],
          unavailable_layers: [],
          layer_statuses: [],
          limitations: [],
        }), { status: 200 }));
      }
      const payload = JSON.parse(String(init?.body ?? "{}")) as { question?: string };
      if (payload.question?.includes("grab-and-go")) {
        return Promise.resolve(new Response(JSON.stringify({
          status: "answer",
          response_mode: "grounded",
          trace_id: "trace-kit",
          answer: "Keep water and food in a grab-and-go bag.",
          claims: [],
          evidence: [],
          limitations: [],
        }), { status: 200 }));
      }
      return Promise.resolve(new Response(JSON.stringify({
        status: "answer",
        response_mode: "requires_input",
        trace_id: "trace-location-new-question",
        answer: "Share an approximate location or enter a BC community to continue.",
        claims: [],
        evidence: [],
        limitations: [],
        required_input: {
          kind: "location",
          prompt: "Use approximate location or enter a BC community.",
          continuation_question: "How close is the wildfire perimeter near me today?",
        },
      }), { status: 200 }));
    });
    vi.stubGlobal("fetch", wrapAppFetch( fetchMock));
    const user = userEvent.setup();
    render(<App />);
    await user.type(screen.getByLabelText("Ask FireLens a question"), "How close is the wildfire perimeter near me today?");
    await user.click(screen.getByLabelText("Send question"));
    expect(await screen.findByText("One detail needed")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Ask FireLens a question"), "What belongs in a grab-and-go bag?");
    await user.click(screen.getByLabelText("Send question"));
    expect(await screen.findByText("Keep water and food in a grab-and-go bag.")).toBeInTheDocument();
    const followUp = JSON.parse(String(askCallOptions(fetchMock).at(-1)?.body));
    expect(followUp.question).toBe("What belongs in a grab-and-go bag?");
    expect(followUp.location).toBeUndefined();
  });

  it("sends completed turns with a follow-up question", async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(
      new Response(JSON.stringify(answer), { status: 200 }),
    ));
    vi.stubGlobal("fetch", wrapAppFetch( fetchMock));
    const user = userEvent.setup();
    render(<App />);

    await user.type(screen.getByLabelText("Ask FireLens a question"), "What should I pack?");
    await user.click(screen.getByLabelText("Send question"));
    await waitFor(() => expect(screen.getByLabelText("Ask FireLens a question")).not.toBeDisabled());
    await user.type(screen.getByLabelText("Ask FireLens a question"), "Why does that matter?");
    await user.click(screen.getByLabelText("Send question"));
    await waitFor(() => expect(askCallOptions(fetchMock)).toHaveLength(2));
    expect(screen.getByText("2 of 6 prior turns in context")).toBeInTheDocument();

    const calls = askCallOptions(fetchMock);
    const firstPayload = JSON.parse(String(calls[0]?.body));
    const secondPayload = JSON.parse(String(calls[1]?.body));
    expect(firstPayload.history).toEqual([]);
    expect(secondPayload.history).toEqual([
      { role: "user", content: "What should I pack?" },
      { role: "assistant", content: answer.answer },
    ]);
  });

  it("sends the shown list for ordinal follow-ups, keeps it through a focused answer, and retains the server selection", async () => {
    const liveResults = [
      { result_id: "incident:first", name: "First Fire", status: "Out of Control" },
      { result_id: "incident:second", name: "Second Fire", status: "Being Held" },
      { result_id: "incident:third", name: "Third Fire", status: "Under Control" },
    ].map((item) => ({
      ...item,
      kind: "incident",
      authority: "BC Wildfire Service",
      source_url: `https://example.test/${item.result_id}`,
      source_updated_at: "2026-08-23T12:00:00Z",
      retrieved_at: "2026-08-23T12:01:00Z",
      freshness: "fresh",
      geometry: { type: "Point", coordinates: [-119.5, 49.9] },
    }));
    let askCount = 0;
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url.startsWith("/api/v1/live/map")) {
        return Promise.resolve(new Response(JSON.stringify({ results: [], unavailable_layers: [] }), { status: 200 }));
      }
      askCount += 1;
      // The server answers a position or a deictic follow-up with the one
      // record it is about, as the real service does.
      const selected = askCount > 1 ? "incident:second" : undefined;
      return Promise.resolve(new Response(JSON.stringify({
        status: "answer",
        response_mode: "live",
        trace_id: `trace-ordinal-${askCount}`,
        answer: `PB0${25 + askCount} answer`,
        suggested_questions: [],
        claims: [],
        evidence: [],
        limitations: [],
        live_results: selected ? liveResults.filter((item) => item.result_id === selected) : liveResults,
        aggregate_freshness: "fresh",
        ...(selected ? { selected_live_result_id: selected } : {}),
        validation: { accepted: true },
      }), { status: 200 }));
    });
    vi.stubGlobal("fetch", wrapAppFetch( fetchMock));
    const user = userEvent.setup();
    render(<App />);

    await user.type(screen.getByLabelText("Ask FireLens a question"), "Show current wildfire records");
    await user.click(screen.getByLabelText("Send question"));
    expect(await screen.findByText("PB026 answer")).toBeInTheDocument();

    await user.type(screen.getByLabelText("Ask FireLens a question"), "Tell me more about the second one.");
    await user.click(screen.getByLabelText("Send question"));
    expect(await screen.findByText("PB027 answer")).toBeInTheDocument();
    await waitFor(() => expect(askCallOptions(fetchMock)).toHaveLength(2));
    const rosterIds = ["incident:first", "incident:second", "incident:third"];
    const secondPayload = JSON.parse(String(askCallOptions(fetchMock)[1]?.body));
    expect(secondPayload.context?.visible_live_result_ids).toEqual(rosterIds);
    expect(secondPayload.context?.selected_live_result_id).toBeUndefined();

    await user.type(screen.getByLabelText("Ask FireLens a question"), "How far is that one from Kamloops?");
    await user.click(screen.getByLabelText("Send question"));
    expect(await screen.findByText("PB028 answer")).toBeInTheDocument();
    await waitFor(() => expect(askCallOptions(fetchMock)).toHaveLength(3));
    const thirdPayload = JSON.parse(String(askCallOptions(fetchMock)[2]?.body));
    expect(thirdPayload.context?.selected_live_result_id).toBe("incident:second");
    // The focused answer about one record did not shrink the list being counted through.
    expect(thirdPayload.context?.visible_live_result_ids).toEqual(rosterIds);
  });

  it("uses the server-bounded assistant history representation", async () => {
    const longAnswer = "A".repeat(7_000);
    const boundedHistory = `${"A".repeat(5_997)}...`;
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(
      new Response(JSON.stringify({
        ...answer,
        answer: longAnswer,
        history_text: boundedHistory,
      }), { status: 200 }),
    ));
    vi.stubGlobal("fetch", wrapAppFetch( fetchMock));
    const user = userEvent.setup();
    render(<App />);

    await user.type(screen.getByLabelText("Ask FireLens a question"), "Question one");
    await user.click(screen.getByLabelText("Send question"));
    await screen.findByText(longAnswer);
    await user.type(screen.getByLabelText("Ask FireLens a question"), "Question two");
    await user.click(screen.getByLabelText("Send question"));
    await waitFor(() => expect(askCallOptions(fetchMock)).toHaveLength(2));

    const secondPayload = JSON.parse(askCallOptions(fetchMock)[1]!.body as string);
    expect(secondPayload.history[1]).toEqual({
      role: "assistant",
      content: boundedHistory,
    });
  });

  it("bounds request history at six turns", async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(
      new Response(JSON.stringify(answer), { status: 200 }),
    ));
    vi.stubGlobal("fetch", wrapAppFetch( fetchMock));
    const user = userEvent.setup();
    render(<App />);

    for (const question of ["Question one", "Question two", "Question three", "Question four"]) {
      await user.type(screen.getByLabelText("Ask FireLens a question"), question);
      await user.click(screen.getByLabelText("Send question"));
      await screen.findAllByText(question);
      await waitFor(() => expect(screen.getByLabelText("Ask FireLens a question")).not.toBeDisabled());
    }

    const fourthPayload = JSON.parse(String(askCallOptions(fetchMock)[3]?.body));
    expect(fourthPayload.history).toHaveLength(6);
    expect(fourthPayload.history[0]).toEqual({ role: "user", content: "Question one" });
    expect(fourthPayload.history[5]).toEqual({ role: "assistant", content: answer.answer });
  });

  it("clears local context before the next request", async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(
      new Response(JSON.stringify(answer), { status: 200 }),
    ));
    vi.stubGlobal("fetch", wrapAppFetch( fetchMock));
    const user = userEvent.setup();
    render(<App />);

    await user.type(screen.getByLabelText("Ask FireLens a question"), "First question");
    await user.click(screen.getByLabelText("Send question"));
    await waitFor(() => expect(screen.getByLabelText("Ask FireLens a question")).not.toBeDisabled());
    await user.click(screen.getByLabelText("Clear conversation history"));
    expect(screen.queryByText("0 of 6 turns in context")).not.toBeInTheDocument();
    expect(screen.queryByText("No earlier turns in context")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "What do you want to know about wildfires in B.C.?" })).toBeInTheDocument();

    await user.type(screen.getByLabelText("Ask FireLens a question"), "Fresh question");
    await user.click(screen.getByLabelText("Send question"));
    await waitFor(() => expect(askCallOptions(fetchMock)).toHaveLength(2));
    const payload = JSON.parse(String(askCallOptions(fetchMock)[1]?.body));
    expect(payload.history).toEqual([]);
  });

  it("keeps mixed reviewed sources labelled when live records are also present", async () => {
    vi.stubGlobal("fetch", wrapAppFetch( vi.fn().mockImplementation((url: string) => {
      if (String(url).startsWith("/api/v1/live/map")) {
        return Promise.resolve(new Response(JSON.stringify({
          generated_at: "2026-08-15T18:00:00Z",
          results: [],
          unavailable_layers: [],
          layer_statuses: [],
          limitations: [],
        }), { status: 200 }));
      }
      return Promise.resolve(new Response(JSON.stringify({
        ...answer,
        response_mode: "mixed",
        answer: "Surface Test Fire is active; keep grab-and-go guidance ready.",
        live_results: [{
          result_id: "incident:surface-7",
          kind: "incident",
          authority: "BC Wildfire Service",
          source_url: "https://example.test/incidents/surface-7",
          source_updated_at: "2026-08-06T11:55:00Z",
          retrieved_at: "2026-08-06T12:00:00Z",
          freshness: "fresh",
          status: "Out of Control",
          name: "Surface Test Fire",
          geometry: { type: "Point", coordinates: [-123.12, 49.28] },
        }],
      }), { status: 200 }));
    })));
    const user = userEvent.setup();
    render(<App />);
    await user.type(screen.getByLabelText("Ask FireLens a question"), "surface:mixed");
    await user.click(screen.getByLabelText("Send question"));
    expect(await screen.findByText("Preparedness sources")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /Wildfire Preparedness Guide/ }).length).toBeGreaterThan(0);
    expect(
      screen.getByRole("article", { name: "Supported claim 1: Explanation linked to a source" }),
    ).toBeInTheDocument();
  });

  it("uses the stale map title when the answer records are stale and the province map is empty", async () => {
    vi.stubGlobal("fetch", wrapAppFetch( vi.fn().mockImplementation((url: string) => {
      if (String(url).startsWith("/api/v1/live/map")) {
        return Promise.resolve(new Response(JSON.stringify({
          generated_at: "2026-08-15T18:00:00Z",
          results: [],
          unavailable_layers: [],
          layer_statuses: [],
          limitations: [],
        }), { status: 200 }));
      }
      return Promise.resolve(new Response(JSON.stringify({
        status: "answer",
        response_mode: "live",
        trace_id: "stale-heading",
        answer: "Cached official information (refresh failed): Surface Test Fire.",
        claims: [],
        evidence: [],
        limitations: ["A refresh failed; this cached record is visibly stale."],
        aggregate_freshness: "stale",
        live_results: [{
          result_id: "incident:surface-stale",
          kind: "incident",
          authority: "BC Wildfire Service",
          source_url: "https://example.test/incidents/surface-stale",
          source_updated_at: "2026-07-28T11:55:00Z",
          retrieved_at: "2026-07-28T12:00:00Z",
          freshness: "stale",
          status: "Out of Control",
          name: "Surface Test Fire",
          geometry: { type: "Point", coordinates: [-123.12, 49.28] },
        }],
      }), { status: 200 }));
    })));
    const user = userEvent.setup();
    render(<App />);
    await user.type(screen.getByLabelText("Ask FireLens a question"), "surface:live-stale");
    await user.click(screen.getByLabelText("Send question"));
    await user.click(await screen.findByRole("button", { name: "Show these on the map" }));
    expect(await screen.findByRole("heading", {
      name: "Wildfires in B.C. (cached records)",
    })).toBeInTheDocument();
  });

  it("bounds a large matching roster and exposes every record on request", async () => {
    const liveResults = Array.from({ length: 20 }, (_, index) => ({
      result_id: `incident:surface-${String(index + 1).padStart(2, "0")}`,
      kind: "incident" as const,
      authority: "BC Wildfire Service",
      source_url: `https://example.test/incidents/surface-${index + 1}`,
      source_updated_at: "2026-08-06T11:55:00Z",
      retrieved_at: "2026-08-06T12:00:00Z",
      freshness: "fresh" as const,
      status: "Out of Control",
      name: `Surface Test Fire ${String(index + 1).padStart(2, "0")}`,
      geometry: { type: "Point" as const, coordinates: [-123.12 + index * 0.1, 49.28] },
    }));
    vi.stubGlobal("fetch", wrapAppFetch( vi.fn().mockImplementation((url: string) => {
      if (String(url).startsWith("/api/v1/live/map")) {
        return Promise.resolve(new Response(JSON.stringify({
          generated_at: "2026-08-15T18:00:00Z",
          results: [],
          unavailable_layers: [],
          layer_statuses: [],
          limitations: [],
        }), { status: 200 }));
      }
      return Promise.resolve(new Response(JSON.stringify({
        status: "answer",
        response_mode: "live",
        presentation_shell: "analysis",
        provenance_class: "official_live",
        roster_total: 20,
        sample_record_ids: liveResults.slice(0, 8).map((item) => item.result_id),
        trace_id: "twenty-records",
        answer: "Current official information: matching fires are listed.",
        claims: [],
        evidence: [],
        limitations: ["No matching record is not a safety determination."],
        aggregate_freshness: "fresh",
        live_results: liveResults,
      }), { status: 200 }));
    })));
    const user = userEvent.setup();
    render(<App />);
    await user.type(screen.getByLabelText("Ask FireLens a question"), "surface:live-fresh");
    await user.click(screen.getByLabelText("Send question"));
    await user.click(await screen.findByRole("tab", { name: "Map" }));
    const matching = await screen.findByRole("list", { name: "Matching this question" });
    expect(within(matching).getAllByRole("listitem")).toHaveLength(12);
    await user.click(screen.getByRole("button", { name: "Show all 20 matching records" }));
    expect(within(matching).getAllByRole("listitem")).toHaveLength(20);
  });

  it("keeps the approximate-location status visible after opt-in", async () => {
    Object.defineProperty(navigator, "geolocation", {
      configurable: true,
      value: {
        getCurrentPosition(success: (position: GeolocationPosition) => void) {
          success({
            coords: { latitude: 49.282729, longitude: -123.120738, accuracy: 100 },
          } as GeolocationPosition);
        },
      },
    });
    vi.stubGlobal("fetch", wrapAppFetch( vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      if (String(url).startsWith("/api/v1/live/map")) {
        return Promise.resolve(new Response(JSON.stringify({
          generated_at: "2026-08-15T18:00:00Z",
          results: [],
          unavailable_layers: [],
          layer_statuses: [],
          limitations: [],
        }), { status: 200 }));
      }
      const payload = JSON.parse(String(init?.body ?? "{}")) as { question?: string };
      if (payload.question === "surface:requires-location") {
        return Promise.resolve(new Response(JSON.stringify({
          status: "requires_input",
          response_mode: "requires_input",
          trace_id: "needs-location",
          answer: null,
          claims: [],
          evidence: [],
          limitations: [],
          required_input: {
            kind: "location",
            prompt: "Use approximate location or enter a BC community.",
            continuation_question: "surface:live-fresh",
          },
        }), { status: 200 }));
      }
      return Promise.resolve(new Response(JSON.stringify({
        status: "answer",
        response_mode: "live",
        trace_id: "after-location",
        answer: "Current official information: Surface Test Fire is Out of Control.",
        claims: [],
        evidence: [],
        limitations: [],
        aggregate_freshness: "fresh",
        live_results: [{
          result_id: "incident:surface-7",
          kind: "incident",
          authority: "BC Wildfire Service",
          source_url: "https://example.test/incidents/surface-7",
          source_updated_at: "2026-08-06T11:55:00Z",
          retrieved_at: "2026-08-06T12:00:00Z",
          freshness: "fresh",
          status: "Out of Control",
          name: "Surface Test Fire",
          geometry: { type: "Point", coordinates: [-123.12, 49.28] },
        }],
      }), { status: 200 }));
    })));
    const user = userEvent.setup();
    render(<App />);
    await user.type(screen.getByLabelText("Ask FireLens a question"), "surface:requires-location");
    await user.click(screen.getByLabelText("Send question"));
    await screen.findByText("One detail needed");
    await user.click(screen.getByRole("button", { name: "Use approximate location" }));
    expect(await screen.findByText("Approximate location ready for this conversation.")).toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: "Show these on the map" }));
    expect(await screen.findByText("Wildfires in B.C. right now")).toBeInTheDocument();
    expect(screen.getByText("Approximate location ready for this conversation.")).toBeInTheDocument();
  });

  it("offers retry only for a retryable provider failure", async () => {
    vi.stubGlobal("fetch", wrapAppFetch( vi.fn().mockResolvedValue(
      new Response(JSON.stringify({
        trace_id: "trace-error",
        error_kind: "rate_limit",
        message: "The required OpenRouter service is unavailable.",
        retryable: true,
      }), { status: 503 }),
    )));
    const user = userEvent.setup();
    render(<App />);
    await user.type(screen.getByLabelText("Ask FireLens a question"), "How should I prepare for wildfire?");
    await user.click(screen.getByLabelText("Send question"));
    expect(await screen.findByText(/You can retry this question\./)).toBeInTheDocument();
    expect(screen.getByRole("status", { name: "We couldn't complete this question" })).toBeInTheDocument();
    expect(screen.getByText("No wildfire status was shown or inferred.")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Retry this question" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Official BC Wildfire Service map" })).toHaveAttribute(
      "href",
      "https://wildfiresituation.nrs.gov.bc.ca/map",
    );
    expect(screen.queryByText("Each statement and its source")).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Official wildfire records map" })).not.toBeInTheDocument();
  });

  it("explains when retrying an unchanged structured request is unlikely to help", async () => {
    vi.stubGlobal("fetch", wrapAppFetch( vi.fn().mockResolvedValue(new Response(JSON.stringify({
      trace_id: "trace-not-retryable",
      error_kind: "invalid_request",
      message: "This request could not be processed as written.",
      retryable: false,
    }), { status: 400 }))));
    const user = userEvent.setup();
    render(<App />);

    await user.type(screen.getByLabelText("Ask FireLens a question"), "invalid request");
    await user.click(screen.getByLabelText("Send question"));

    expect(await screen.findByText(/Retrying this unchanged question is unlikely to help\./)).toBeInTheDocument();
    expect(screen.getByRole("alert", { name: "We couldn't complete this question" })).toBeInTheDocument();
    expect(screen.getByText("No wildfire status was shown or inferred.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry this question" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Official BC Wildfire Service map" })).toHaveAttribute(
      "href",
      "https://wildfiresituation.nrs.gov.bc.ca/map",
    );
  });

  it.each([
    {
      label: "transport",
      fetchResult: () => Promise.reject(new TypeError("fetch failed")),
      message: "FireLens could not reach the service. Check your connection, then retry this question.",
    },
    {
      label: "body read",
      fetchResult: () => {
        const response = new Response("unused", { status: 200 });
        vi.spyOn(response, "text").mockRejectedValueOnce(new TypeError("stream closed"));
        return Promise.resolve(response);
      },
      message: "FireLens reached the service but could not finish reading its response. Retry this question; if the problem continues, use the official BC Wildfire Service.",
    },
    {
      label: "invalid JSON",
      fetchResult: () => Promise.resolve(new Response("<html>bad gateway</html>", { status: 502 })),
      message: "The service reply could not be used as an answer. Retry this question; if the problem continues, use the official BC Wildfire Service.",
    },
  ])("shows truthful retry guidance for a $label failure without retrying automatically", async ({ fetchResult, message }) => {
    const fetchMock = vi.fn().mockImplementation(fetchResult);
    vi.stubGlobal("fetch", wrapAppFetch( fetchMock));
    const user = userEvent.setup();
    render(<App />);

    await user.type(screen.getByLabelText("Ask FireLens a question"), "Are there evacuation orders near Kelowna?");
    await user.click(screen.getByLabelText("Send question"));

    expect(await screen.findByText(message)).toBeInTheDocument();
    expect(screen.getByText("We couldn't complete this question")).toBeInTheDocument();
    expect(screen.getByText("No wildfire status was shown or inferred.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry this question" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Official BC Wildfire Service map" })).toHaveAttribute(
      "href",
      "https://wildfiresituation.nrs.gov.bc.ca/map",
    );
    expect(screen.queryByText("Each statement and its source")).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Official wildfire records map" })).not.toBeInTheDocument();
    expect(screen.queryByText(/invalid service response/i)).not.toBeInTheDocument();
    expect(askCallOptions(fetchMock)).toHaveLength(1);
  });

  it("has no automated accessibility violations in a retryable service failure", async () => {
    vi.stubGlobal("fetch", wrapAppFetch( vi.fn().mockResolvedValue(new Response("<html>bad gateway</html>", { status: 502 }))));
    const user = userEvent.setup();
    const { container } = render(<App />);
    await user.type(screen.getByLabelText("Ask FireLens a question"), "Where is Mountain Fire near Kelowna?");
    await user.click(screen.getByLabelText("Send question"));
    expect(await screen.findByRole("button", { name: "Retry this question" })).toBeInTheDocument();
    const result = await axe(container);
    expect(result.violations).toEqual([]);
  });

  it("keeps a named Mountain Fire answer first with the map closed", async () => {
    vi.stubGlobal("fetch", wrapAppFetch( vi.fn().mockResolvedValue(new Response(JSON.stringify({
      status: "answer",
      response_mode: "live",
      trace_id: "trace-mountain-kelowna",
      answer: "Current official information: Mountain Fire is Being Held.",
      claims: [],
      evidence: [],
      limitations: [],
      live_results: [{
        result_id: "incident:mountain",
        kind: "incident",
        authority: "BC Wildfire Service",
        source_url: "https://example.test/incidents/mountain",
        source_updated_at: "2026-08-23T12:00:00Z",
        retrieved_at: "2026-08-23T12:01:00Z",
        freshness: "fresh",
        status: "Being Held",
        name: "Mountain Fire",
        geometry: { type: "Point", coordinates: [-119.5, 49.9] },
      }],
      aggregate_freshness: "fresh",
    }), { status: 200 }))));
    const user = userEvent.setup();
    render(<App />);
    await user.type(screen.getByLabelText("Ask FireLens a question"), "Where is Mountain Fire near Kelowna?");
    await user.click(screen.getByLabelText("Send question"));

    const answerLead = await screen.findByText(/Mountain Fire is Being Held/);
    const liveSummary = screen.getByLabelText("Live answer summary");
    expect(answerLead.compareDocumentPosition(liveSummary) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getByRole("button", { name: "Show these on the map" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Official wildfire records map" })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Analysis view" })).not.toBeInTheDocument();
  });

  it("has no automated accessibility violations in the idle state", async () => {
    const { container } = render(<App />);
    const result = await axe(container);
    expect(result.violations).toEqual([]);
  });

  it("has no automated accessibility violations in the evidence state", async () => {
    vi.stubGlobal("fetch", wrapAppFetch( vi.fn().mockResolvedValue(
      new Response(JSON.stringify(answer), { status: 200 }),
    )));
    const user = userEvent.setup();
    const { container } = render(<App />);
    await user.type(screen.getByLabelText("Ask FireLens a question"), "What should I pack?");
    await user.click(screen.getByLabelText("Send question"));
    await screen.findByText("Each statement and its source");
    const result = await axe(container);
    expect(result.violations).toEqual([]);
  });
});
