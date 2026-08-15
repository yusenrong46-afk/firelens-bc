import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { axe } from "vitest-axe";
import { App } from "../src/app/App";

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
  it("shows capability suggestions before the first question", () => {
    render(<App />);
    expect(screen.getByRole("button", { name: "What belongs in a grab-and-go bag?" })).toBeInTheDocument();
    expect(screen.getByText("0 of 6 turns in context")).toBeInTheDocument();
  });

  it("renders a capability response with API suggestions and no evidence", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
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
    ));
    const user = userEvent.setup();
    render(<App />);
    await user.type(screen.getByLabelText("Ask FireLens a question"), "What can you help me with?");
    await user.click(screen.getByLabelText("Send question"));

    expect(await screen.findByText("FireLens topics")).toBeInTheDocument();
    expect(screen.getByText("Explore the FireLens collection")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "How should I prepare a household emergency plan?" })).toBeInTheDocument();
    expect(screen.queryByText("Retrieved passage")).not.toBeInTheDocument();
  });

  it("renders optional authority-labelled answer sections", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
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
    ));
    const user = userEvent.setup();
    render(<App />);
    await user.type(screen.getByLabelText("Ask FireLens a question"), "What is happening?");
    await user.click(screen.getByLabelText("Send question"));

    expect((await screen.findAllByText("Official current records")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Current official records").length).toBeGreaterThan(0);
    expect(screen.getAllByText("General background").length).toBeGreaterThan(0);
    expect(screen.getAllByText("This context is not a live official record.").length).toBeGreaterThan(0);
    expect(screen.getByText("Live records + general background")).toBeInTheDocument();
    expect(screen.getByText("General background in this answer")).toBeInTheDocument();
    expect(screen.queryByText("Sources supporting this answer")).not.toBeInTheDocument();
  });

  it("keeps reviewed-source conflicts visible beside live records", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(JSON.stringify({
        ...answer,
        response_mode: "mixed",
        trace_id: "trace-mixed-conflict",
        answer: "A current record is available, but the reviewed guidance conflicts.",
        answer_sections: [
          { kind: "current_records", heading: "Current official records", text: "Current official information: Section Fire is Being Held." },
          { kind: "conflicting_guidance", heading: "Conflicting reviewed sources", text: "The reviewed sources disagree; inspect both before acting." },
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
    ));
    const user = userEvent.setup();
    render(<App />);
    await user.type(screen.getByLabelText("Ask FireLens a question"), "Show this fire and explain the conflicting guidance.");
    await user.click(screen.getByLabelText("Send question"));

    expect(await screen.findByText("Live records + conflicting sources")).toBeInTheDocument();
    expect(screen.getAllByText("Conflicting reviewed sources").length).toBeGreaterThan(0);
    expect(screen.getByText("The reviewed sources disagree; inspect both before acting.")).toBeInTheDocument();
  });

  it("renders a verified answer and its local evidence", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(JSON.stringify(answer), { status: 200 }),
    ));
    const user = userEvent.setup();
    render(<App />);
    await user.type(screen.getByLabelText("Ask FireLens a question"), "What goes in a grab-and-go bag?");
    await user.click(screen.getByLabelText("Send question"));

    expect(await screen.findByText("Sources supporting this answer")).toBeInTheDocument();
    expect(screen.getByText("Reviewed sources")).toBeInTheDocument();
    expect(screen.getAllByText("Keep water and food in a grab-and-go bag.").length).toBeGreaterThan(1);
    expect(screen.getByText("Food & water").tagName).toBe("MARK");
    expect(screen.getByText("PreparedBC")).toBeInTheDocument();
    expect(screen.getByText("Human-verified source transcription")).toBeInTheDocument();
  });

  it("renders labelled background without an evidence interaction", async () => {
    const backgroundClaim = "Embers can travel ahead of a wildfire front.";
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(JSON.stringify({
        status: "answer",
        response_mode: "background",
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
    ));
    const user = userEvent.setup();
    render(<App />);
    await user.type(screen.getByLabelText("Ask FireLens a question"), "Why can embers be dangerous?");
    await user.click(screen.getByLabelText("Send question"));

    expect(await screen.findByText("General background")).toBeInTheDocument();
    expect(screen.getByText("General background — no corpus evidence attached")).toBeInTheDocument();
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
      vi.stubGlobal("fetch", fetchMock);
      const user = userEvent.setup();
      render(<App />);

      await user.type(screen.getByLabelText("Ask FireLens a question"), `Test ${responseMode} limitations`);
      await user.click(screen.getByLabelText("Send question"));

      const limitations = await screen.findByRole("status", { name: "Answer limitations" });
      expect(within(limitations).getAllByText(limitation)).toHaveLength(1);
      expect(within(limitations).getAllByRole("listitem")).toHaveLength(1);
    },
  );

  it("keeps unsupported live requests useful with an official next link", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
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
    ));
    const user = userEvent.setup();
    render(<App />);
    await user.type(screen.getByLabelText("Ask FireLens a question"), "What is the current air quality in Kelowna?");
    await user.click(screen.getByLabelText("Send question"));

    expect(await screen.findByText("Related official service")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Current B.C. AQHI/ })).toHaveAttribute(
      "href",
      "https://weather.gc.ca/airquality/pages/provincial_summary/bc_e.html",
    );
    expect(screen.getByText(/Map focused on the requested area near 49.89, -119.50/)).toBeInTheDocument();
    expect(screen.queryByText("FireLens did not generate guidance")).not.toBeInTheDocument();
  });

  it("renders a typed abstention without evidence", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
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
    ));
    const user = userEvent.setup();
    render(<App />);
    await user.type(screen.getByLabelText("Ask FireLens a question"), "Is a fire active near me right now?");
    await user.click(screen.getByLabelText("Send question"));

    expect(await screen.findByText("FireLens did not generate guidance")).toBeInTheDocument();
    expect(screen.getAllByText("Current source unavailable").length).toBeGreaterThan(0);
    expect(screen.getByText(/could not establish the requested current status/)).toBeInTheDocument();
    expect(screen.getByText(/live_data_required/)).toBeInTheDocument();
    expect(screen.queryByText("Sources supporting this answer")).not.toBeInTheDocument();
  });

  it("labels a personal-safety abstention and exposes its actual official handoff", async () => {
    const officialUrl = "https://www.emergencyinfobc.gov.bc.ca/";
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
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
    ));
    const user = userEvent.setup();
    render(<App />);
    await user.type(screen.getByLabelText("Ask FireLens a question"), "Should I evacuate now?");
    await user.click(screen.getByLabelText("Send question"));

    expect(await screen.findByText("Personal safety boundary")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Personal safety decision boundary", level: 2 })).toBeInTheDocument();
    expect(screen.getByText(/cannot decide whether you should stay, leave, evacuate, return/)).toBeInTheDocument();
    expect(screen.getByRole("link", {
      name: "Open EmergencyInfoBC current evacuation information from the answer context",
    })).toHaveAttribute("href", officialUrl);
    expect(screen.queryByText(/Use the official-current-information link/)).not.toBeInTheDocument();
  });

  it("renders official live records in the map panel", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(JSON.stringify({
        status: "answer",
        response_mode: "live",
        trace_id: "trace-live-map",
        answer: "Current official information: Test Fire is Out of Control.",
        claims: [],
        evidence: [],
        limitations: ["No matching record is not a safety determination."],
        live_results: [{
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
        }],
        unavailable_layers: ["evacuation"],
      }), { status: 200 }),
    ));
    const user = userEvent.setup();
    render(<App />);
    await user.type(screen.getByLabelText("Ask FireLens a question"), "Is there an active wildfire now?");
    await user.click(screen.getByLabelText("Send question"));

    expect(await screen.findByText("Current BC wildfire information")).toBeInTheDocument();
    expect(screen.getAllByText("Official live records").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Test Fire").length).toBeGreaterThan(0);
    const matchingList = screen.getByRole("list", { name: "Matching this question" });
    const missingLayerWarning = screen.getByText(/Some official layers are unavailable: evacuation/);
    const map = screen.getByRole("region", { name: "Interactive map of official wildfire records" });
    expect(missingLayerWarning.compareDocumentPosition(matchingList) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(missingLayerWarning.compareDocumentPosition(map) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getByText(/Source updated/)).toBeInTheDocument();
    expect(screen.getByText(/Retrieved/)).toBeInTheDocument();
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
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);

    await user.type(screen.getByLabelText("Ask FireLens a question"), "Show the matching fire");
    await user.click(screen.getByLabelText("Send question"));

    expect((await screen.findAllByText("Fresh Question Fire is the matching official record.")).length).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { name: "BC wildfire information — mixed freshness", level: 1 })).toBeInTheDocument();
    expect(screen.getByText(/Official records include stale cached data/)).toBeInTheDocument();
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
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);

    await user.type(screen.getByLabelText("Ask FireLens a question"), "Where is Question Fire?");
    await user.click(screen.getByLabelText("Send question"));

    expect(await screen.findByRole("heading", { name: "Matching this question", level: 2 })).toBeInTheDocument();
    const matchingList = screen.getByRole("list", { name: "Matching this question" });
    expect(within(matchingList).getByText("Question Fire")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Rest of B.C.", level: 2 })).toBeInTheDocument();
    expect(screen.queryByText("Province Fire")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Show rest of B\.C\./ }));
    const provinceList = screen.getByRole("list", { name: "Rest of B.C." });
    const provinceNames = within(provinceList).getAllByRole("button").map((button) => button.querySelector("strong")?.textContent);
    expect(provinceNames).toEqual(["Province Fire", "Evacuation area EA-7", "Wildfire perimeter"]);
    expect(within(provinceList).getByRole("link", { name: "Open GIS dataset for Wildfire perimeter, record perimeter:province" })).toBeInTheDocument();
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
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);

    await user.type(screen.getByLabelText("Ask FireLens a question"), "Where are the fires in Kelowna?");
    await user.click(screen.getByLabelText("Send question"));

    expect(await screen.findByText(/Map focused on the requested area near 49.89, -119.50/)).toBeInTheDocument();
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
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);

    expect(screen.queryByLabelText("BC community for this question")).not.toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: /Mountain Fire.*Out of Control/ }));
    await user.type(screen.getByLabelText("Ask FireLens a question"), "How far is this fire from me?");
    await user.click(screen.getByLabelText("Send question"));

    expect(await screen.findByText("One detail needed")).toBeInTheDocument();
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
    expect(laterPayload.location).toBeUndefined();
  });

  it("sends completed turns with a follow-up question", async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(
      new Response(JSON.stringify(answer), { status: 200 }),
    ));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);

    await user.type(screen.getByLabelText("Ask FireLens a question"), "What should I pack?");
    await user.click(screen.getByLabelText("Send question"));
    await screen.findByText("2 of 6 turns in context");
    await user.type(screen.getByLabelText("Ask FireLens a question"), "Why does that matter?");
    await user.click(screen.getByLabelText("Send question"));
    await waitFor(() => expect(askCallOptions(fetchMock)).toHaveLength(2));

    const calls = askCallOptions(fetchMock);
    const firstPayload = JSON.parse(String(calls[0]?.body));
    const secondPayload = JSON.parse(String(calls[1]?.body));
    expect(firstPayload.history).toEqual([]);
    expect(secondPayload.history).toEqual([
      { role: "user", content: "What should I pack?" },
      { role: "assistant", content: answer.answer },
    ]);
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
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);

    await user.type(screen.getByLabelText("Ask FireLens a question"), "Question one");
    await user.click(screen.getByLabelText("Send question"));
    await screen.findByText("2 of 6 turns in context");
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
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);

    for (const question of ["Question one", "Question two", "Question three", "Question four"]) {
      await user.type(screen.getByLabelText("Ask FireLens a question"), question);
      await user.click(screen.getByLabelText("Send question"));
      await screen.findByText(question);
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
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<App />);

    await user.type(screen.getByLabelText("Ask FireLens a question"), "First question");
    await user.click(screen.getByLabelText("Send question"));
    await screen.findByText("2 of 6 turns in context");
    await user.click(screen.getByLabelText("Clear conversation history"));
    expect(screen.getByText("0 of 6 turns in context")).toBeInTheDocument();

    await user.type(screen.getByLabelText("Ask FireLens a question"), "Fresh question");
    await user.click(screen.getByLabelText("Send question"));
    await waitFor(() => expect(askCallOptions(fetchMock)).toHaveLength(2));
    const payload = JSON.parse(String(askCallOptions(fetchMock)[1]?.body));
    expect(payload.history).toEqual([]);
  });

  it("offers retry only for a retryable provider failure", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(JSON.stringify({
        trace_id: "trace-error",
        error_kind: "rate_limit",
        message: "The required OpenRouter service is unavailable.",
        retryable: true,
      }), { status: 503 }),
    ));
    const user = userEvent.setup();
    render(<App />);
    await user.type(screen.getByLabelText("Ask FireLens a question"), "How should I prepare for wildfire?");
    await user.click(screen.getByLabelText("Send question"));
    expect(await screen.findByRole("button", { name: "Retry this question" })).toBeInTheDocument();
  });

  it("has no automated accessibility violations in the idle state", async () => {
    const { container } = render(<App />);
    const result = await axe(container);
    expect(result.violations).toEqual([]);
  });

  it("has no automated accessibility violations in the evidence state", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(JSON.stringify(answer), { status: 200 }),
    ));
    const user = userEvent.setup();
    const { container } = render(<App />);
    await user.type(screen.getByLabelText("Ask FireLens a question"), "What should I pack?");
    await user.click(screen.getByLabelText("Send question"));
    await screen.findByText("Sources supporting this answer");
    const result = await axe(container);
    expect(result.violations).toEqual([]);
  });
});
