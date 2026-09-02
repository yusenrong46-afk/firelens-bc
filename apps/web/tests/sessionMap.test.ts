import { describe, expect, it } from "vitest";
import { deriveSessionMapView } from "../src/features/ask/sessionMap";
import type { AskResponse, LiveResult } from "../src/shared/api/api";

function result(id: string, kind: LiveResult["kind"] = "incident"): LiveResult {
  return {
    result_id: id,
    kind,
    authority: "BC Wildfire Service",
    source_url: "https://example.invalid/layer",
    source_updated_at: "2026-09-01T00:00:00Z",
    retrieved_at: "2026-09-01T01:00:00Z",
    freshness: "fresh",
    status: "Being Held",
    geometry: { type: "Point", coordinates: [-119, 49] },
    geometry_relation: "unknown",
  };
}

function response(ids: string[]): AskResponse {
  return {
    status: "answer",
    response_mode: "live",
    trace_id: "trace",
    answer: "records",
    claims: [],
    evidence: [],
    live_results: ids.map((id) => result(id)),
    limitations: [],
    requested_layers: ["incident"],
    presentation_shell: "analysis",
    provenance_class: "official_live",
  };
}

describe("deriveSessionMapView", () => {
  it("keeps map primary IDs equal to authorized response IDs", () => {
    const view = deriveSessionMapView(
      response(["incident:1", "incident:2"]),
      [result("incident:1"), result("incident:9"), result("evacuation:3", "evacuation")],
      [],
      false,
    );
    expect(view.mapResults.map((item) => item.result_id).sort()).toEqual(["incident:1", "incident:2"]);
    expect(view.mapProvinceResults).toEqual([]);
    expect(new Set(view.mapResults.map((item) => item.result_id)))
      .toEqual(new Set(view.mapMatchingResults.map((item) => item.result_id)));
  });

  it("stores extra context IDs separately only when the user enables context layers", () => {
    const view = deriveSessionMapView(
      response(["incident:1"]),
      [result("incident:1"), result("incident:9")],
      [],
      true,
    );
    expect(view.mapMatchingResults.map((item) => item.result_id)).toEqual(["incident:1"]);
    expect(view.mapProvinceResults.map((item) => item.result_id)).toEqual(["incident:9"]);
  });
});
