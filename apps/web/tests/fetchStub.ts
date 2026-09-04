import { vi } from "vitest";

export function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status });
}

export function wrapAppFetch(
  impl: (input: RequestInfo | URL, init?: RequestInit) => unknown,
) {
  return vi.fn().mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input);
    if (path.startsWith("/api/v1/health/ready")) {
      return Promise.resolve(jsonResponse({ status: "ready", release_version: "1.6.4" }));
    }
    if (path.startsWith("/api/v1/live/summary")) {
      return Promise.resolve(jsonResponse({
        incident_record_count: 12,
        evacuation_record_count: 3,
        retrieved_at: "2026-08-23T12:01:00Z",
        freshness: "fresh",
        limitation: "Counts come from the latest official adapter fetch.",
      }));
    }
    if (path.startsWith("/api/v1/product-events")) {
      return Promise.resolve(new Response(null, { status: 204 }));
    }
    return impl(input, init);
  });
}
