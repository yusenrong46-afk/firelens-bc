import { describe, expect, it } from "vitest";
import { EMPTY_ROSTER, nextRoster, type Roster } from "../src/features/ask/roster";
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
    fire_of_note: false,
  };
}

function response(ids: string[], extra: Partial<AskResponse> = {}): AskResponse {
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
    ...extra,
  };
}

function roster(ids: string[]): Roster {
  return { results: ids.map((id) => result(id)), focus: undefined, unavailableLayers: [] };
}

describe("nextRoster", () => {
  it("adopts a new list and keeps the shown list through a focused answer about one of its records", () => {
    const shown = nextRoster(EMPTY_ROSTER, response(["incident:1", "incident:2", "incident:3"]));
    expect(shown.results.map((item) => item.result_id)).toEqual(["incident:1", "incident:2", "incident:3"]);

    const focused = nextRoster(shown, response(["incident:2"], { selected_live_result_id: "incident:2" }));
    expect(focused).toBe(shown);
  });

  it("keeps the list through an answer with no records, and replaces it with a different list", () => {
    const shown = roster(["incident:1", "incident:2"]);
    expect(nextRoster(shown, response([], { requested_layers: [] }))).toBe(shown);

    const replaced = nextRoster(shown, response(["evacuation:7"]));
    expect(replaced.results.map((item) => item.result_id)).toEqual(["evacuation:7"]);
  });

  it("follows a focused answer about a record that was not on the list", () => {
    const shown = roster(["incident:1", "incident:2"]);
    const elsewhere = nextRoster(shown, response(["incident:9"], { selected_live_result_id: "incident:9" }));
    expect(elsewhere.results.map((item) => item.result_id)).toEqual(["incident:9"]);
  });
});

describe("deriveSessionMapView", () => {
  it("keeps map primary IDs equal to the roster IDs", () => {
    const view = deriveSessionMapView(
      roster(["incident:1", "incident:2"]),
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
      roster(["incident:1"]),
      [result("incident:1"), result("incident:9")],
      [],
      true,
    );
    expect(view.mapMatchingResults.map((item) => item.result_id)).toEqual(["incident:1"]);
    expect(view.mapProvinceResults.map((item) => item.result_id)).toEqual(["incident:9"]);
  });
});

it("keeps partial province coverage out of a question-only roster", () => {
  const statuses = [{
    kind: "evacuation" as const,
    authority: "Province of BC",
    source_url: "https://example.test/evacuations",
    available: true,
    matching_result_count: 1,
    omitted_geometry_count: 2,
    omitted_status_count: 0,
  }];
  const province = [result("evacuation:valid", "evacuation")];
  const idle = deriveSessionMapView(undefined, province, [], false, statuses);
  expect(idle.mapGeometryOmissions).toEqual([{ kind: "evacuation", count: 2 }]);
  const questionRoster = { ...roster(["incident:1"]), unavailableLayers: ["evacuation"] };
  const focused = deriveSessionMapView(questionRoster, province, [], false, statuses);
  expect(focused.mapGeometryOmissions).toEqual([]);
  expect(focused.mapResults).toHaveLength(1);
  expect(focused.mapUnavailableLayers).toEqual(["evacuation"]);
  const withContext = deriveSessionMapView(questionRoster, province, [], true, statuses);
  expect(withContext.mapGeometryOmissions).toEqual(idle.mapGeometryOmissions);
  expect(withContext.mapUnavailableLayers).toEqual([]);
  expect(withContext.mapResults).toHaveLength(2);
});


it("replaces a previous roster with an empty partial lookup without losing its uncertainty", () => {
  const previous = roster(["evacuation:old"]);
  const next = nextRoster(previous, response([], { requested_layers: ["evacuation"], partial_layers: ["evacuation"] }));
  expect(next.results).toEqual([]);
  const map = deriveSessionMapView(next, [], []);
  expect(map.mapPartialLayers).toEqual(["evacuation"]);
  expect(map.mapUnavailableLayers).toEqual([]);
});
