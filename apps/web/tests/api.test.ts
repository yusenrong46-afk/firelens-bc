import { afterEach, describe, expect, it, vi } from "vitest";

import {
  askFireLens,
  fetchNearbyOfficialRecords,
  fetchOfficialMap,
  submitFeedback,
} from "../src/shared/api/api";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("submitFeedback", () => {
  it("sends only the trace and allowlisted category", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ accepted: true }), { status: 202 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await submitFeedback("a".repeat(32), "safety_concern");

    expect(fetchMock).toHaveBeenCalledWith("/api/v1/feedback", expect.objectContaining({
      method: "POST",
      body: JSON.stringify({ trace_id: "a".repeat(32), category: "safety_concern" }),
    }));
  });
});

describe("V3 agent context", () => {
  it("sends bounded selected-map context with an Ask request", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({
        status: "answer",
        response_mode: "background",
        trace_id: "trace-context",
        answer: "General knowledge answer.",
        claims: [],
        evidence: [],
        limitations: [],
      }), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await askFireLens("What is happening with this fire?", [], undefined, undefined, {
      selected_live_result_id: "incident:7",
      visible_live_result_ids: ["incident:7", "perimeter:7"],
    });

    expect(fetchMock).toHaveBeenCalledWith("/api/v1/ask", expect.objectContaining({
      body: JSON.stringify({
        question: "What is happening with this fire?",
        history: [],
        location: undefined,
        context: {
          selected_live_result_id: "incident:7",
          visible_live_result_ids: ["incident:7", "perimeter:7"],
        },
      }),
    }));
  });

  it("loads all official map layers without a location", async () => {
    const payload = {
      generated_at: "2026-08-13T19:00:00Z",
      results: [],
      aggregate_freshness: null,
      unavailable_layers: [],
      layer_statuses: [],
      limitations: [],
    };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(JSON.stringify(payload), { status: 200 }),
    ));

    await expect(fetchOfficialMap()).resolves.toEqual(payload);
  });
});

describe("fetchNearbyOfficialRecords", () => {
  it("posts the bounded typed request and returns the official record page", async () => {
    const payload = {
      generated_at: "2026-08-08T19:00:00Z",
      requested_radius_km: 25,
      requested_layers: ["incident"],
      resolved_location: { latitude: 49.5, longitude: -123.5 },
      viewport: { west: -124, south: 49, east: -123, north: 50 },
      results: [],
      pagination: {
        page: 1,
        page_size: 100,
        total_results: 0,
        total_pages: 0,
        returned_results: 0,
        has_previous: false,
        has_next: false,
      },
      aggregate_freshness: null,
      unavailable_layers: [],
      limitations: ["No matching record is not a safety determination."],
      official_fallback_urls: ["https://wildfiresituation.nrs.gov.bc.ca/map"],
    };
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(payload), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await fetchNearbyOfficialRecords({
      location: { label: "Vancouver", radius_km: 25 },
      layers: ["incident"],
      page: 1,
      page_size: 100,
    });

    expect(result).toEqual(payload);
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/live/nearby", expect.objectContaining({
      method: "POST",
      body: JSON.stringify({
        location: { label: "Vancouver", radius_km: 25 },
        layers: ["incident"],
        page: 1,
        page_size: 100,
      }),
    }));
  });

  it("preserves the typed public error envelope", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(JSON.stringify({
        schema_version: "firelens_error.v1",
        trace_id: "trace-nearby",
        error_kind: "live_not_found",
        message: "The place label could not be resolved.",
        retryable: false,
      }), { status: 404 }),
    ));

    await expect(fetchNearbyOfficialRecords({
      location: { label: "Unknown place", radius_km: 25 },
      layers: ["incident"],
      page: 1,
      page_size: 100,
    })).rejects.toMatchObject({
      name: "FireLensApiError",
      message: "The place label could not be resolved.",
    });
  });
});
