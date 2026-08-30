import { describe, expect, it } from "vitest";
import {
  preferredAnalyticalSurface,
  preferredContextSurface,
  questionExplicitlyRequestsMap,
  questionRequestsMap,
  shouldOfferContextMap,
  shouldUseAnalyticalWorkspace,
  workspaceLayout,
} from "../src/app/workspacePresentation";

const spatialResponse = {
  status: "answer" as const,
  response_mode: "live" as const,
  trace_id: "spatial",
  answer: "An official record is available.",
  suggested_questions: [],
  claims: [],
  evidence: [],
  limitations: [],
  live_results: [{
    result_id: "incident:1",
    kind: "incident" as const,
    authority: "BC Wildfire Service",
    source_url: "https://example.test/incident/1",
    source_updated_at: "2026-08-23T12:00:00Z",
    retrieved_at: "2026-08-23T12:01:00Z",
    freshness: "fresh" as const,
    geometry_relation: "nearby" as const,
    status: "Being Held",
    geometry: { type: "Point" as const, coordinates: [-119.5, 49.9] },
  }],
};

describe("task-first workspace presentation", () => {
  it("recognizes direct and distribution-style map questions", () => {
    expect(questionRequestsMap("Where is Mountain Fire near Kelowna?")).toBe(true);
    expect(questionRequestsMap("Show wildfire geographic distribution across B.C.")).toBe(true);
    expect(questionRequestsMap("What belongs in a grab-and-go bag?")).toBe(false);
  });

  it("distinguishes literal map asks from spatial analysis wording", () => {
    expect(questionExplicitlyRequestsMap("Show these incidents on a map")).toBe(true);
    expect(questionExplicitlyRequestsMap("Show the wildfire distribution across B.C.")).toBe(false);
  });

  it("offers a context map only for live or mixed spatial responses", () => {
    expect(shouldOfferContextMap({
      mode: "live",
      question: "What is the current status?",
      response: spatialResponse,
    })).toBe(true);
    expect(shouldOfferContextMap({
      mode: "grounded",
      question: "Where should I store my emergency kit?",
      response: { ...spatialResponse, response_mode: "grounded", live_results: [] },
    })).toBe(false);
    expect(shouldOfferContextMap({
      mode: "requires_input",
      question: "Where is Mountain Fire?",
      response: { ...spatialResponse, response_mode: "requires_input", live_results: [] },
    })).toBe(false);
    expect(shouldOfferContextMap({
      mode: "live",
      question: "What is the current status?",
      response: {
        ...spatialResponse,
        live_results: [{
          ...spatialResponse.live_results[0]!,
          geometry: { type: "Point", coordinates: [] },
        }],
      },
    })).toBe(false);
  });

  it("defaults answers to evidence and opens the map first only for explicit map analysis", () => {
    expect(preferredContextSurface({ mode: "live", question: "Status please" })).toBe("evidence");
    expect(preferredContextSurface({ mode: "live", question: "Where is Mountain Fire?" })).toBe("evidence");
    expect(preferredContextSurface({ mode: "mixed", question: "Show this on a map" })).toBe("map");
    expect(preferredContextSurface({ mode: "live", question: "Wildfire distribution across B.C." })).toBe("evidence");
    expect(preferredContextSurface({ mode: "mixed", question: "What should I prepare?" })).toBe("evidence");
  });

  it("opens a multi-record map only for a literal map request", () => {
    const multiRecordResponse = {
      ...spatialResponse,
      live_results: [
        spatialResponse.live_results[0]!,
        { ...spatialResponse.live_results[0]!, result_id: "incident:2" },
      ],
    };
    expect(preferredAnalyticalSurface({
      mode: "live",
      question: "Map wildfire distribution by status across B.C.",
      response: multiRecordResponse,
    })).toBe("map");
    expect(preferredAnalyticalSurface({
      mode: "live",
      question: "Show wildfire distribution by status across B.C.",
      response: multiRecordResponse,
    })).toBe("summary");
    expect(preferredAnalyticalSurface({
      mode: "live",
      question: "Where are the most active wildfires?",
      response: multiRecordResponse,
    })).toBe("summary");
  });

  it("uses the analytical workspace whenever a live answer returns multiple incidents", () => {
    const firstResult = spatialResponse.live_results[0]!;
    const multiRecordResponse = {
      ...spatialResponse,
      live_results: [
        firstResult,
        { ...firstResult, result_id: "incident:2", status: "Out of Control" },
      ],
    };
    expect(shouldUseAnalyticalWorkspace({
      mode: "live",
      response: multiRecordResponse,
    })).toBe(true);
    expect(shouldUseAnalyticalWorkspace({
      mode: "live",
      response: spatialResponse,
    })).toBe(false);
    expect(shouldUseAnalyticalWorkspace({
      mode: "live",
      response: { ...multiRecordResponse, selected_live_result_id: "incident:1" },
    })).toBe(false);
    expect(shouldUseAnalyticalWorkspace({
      mode: "grounded",
      response: { ...multiRecordResponse, response_mode: "grounded" },
    })).toBe(false);
  });

  it("locks named, analytical, and reviewed experiences without changing routing", () => {
    const namedQuestion = "Where is Mountain Fire near Kelowna?";
    expect(preferredContextSurface({ mode: "live", question: namedQuestion })).toBe("evidence");
    expect(shouldOfferContextMap({
      mode: "live",
      question: namedQuestion,
      response: spatialResponse,
    })).toBe(true);
    expect(shouldUseAnalyticalWorkspace({
      mode: "live",
      response: spatialResponse,
    })).toBe(false);

    const firstResult = spatialResponse.live_results[0]!;
    const distributionResponse = {
      ...spatialResponse,
      live_results: [
        firstResult,
        { ...firstResult, result_id: "incident:2", status: "Out of Control" },
        { ...firstResult, result_id: "incident:3", status: "Under Control" },
      ],
    };
    expect(shouldUseAnalyticalWorkspace({
      mode: "live",
      response: distributionResponse,
    })).toBe(true);
    expect(preferredContextSurface({
      mode: "live",
      question: "Show wildfire distribution by status across B.C.",
    })).toBe("evidence");

    expect(shouldOfferContextMap({
      mode: "grounded",
      question: "What belongs in a grab-and-go bag?",
      response: { ...spatialResponse, response_mode: "grounded", live_results: [] },
    })).toBe(false);
    expect(shouldUseAnalyticalWorkspace({
      mode: "grounded",
      response: { ...spatialResponse, response_mode: "grounded", live_results: [] },
    })).toBe(false);
    expect(preferredContextSurface({
      mode: "grounded",
      question: "What belongs in a grab-and-go bag?",
    })).toBe("evidence");
  });

  it("maps routed responses to one of the three presentation shells", () => {
    expect(workspaceLayout({ analytical: false, spatial: false })).toBe("chat");
    expect(workspaceLayout({ analytical: true, spatial: true })).toBe("analysis");
    expect(workspaceLayout({ analytical: false, spatial: true })).toBe("spatial");
  });
});
