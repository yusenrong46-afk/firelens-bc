import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchNearbyOfficialRecords } from "../src/api";

afterEach(() => {
  vi.unstubAllGlobals();
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
