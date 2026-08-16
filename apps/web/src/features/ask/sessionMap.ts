import type { AskResponse, LiveResult } from "../../shared/api/api";

export type MapAggregateFreshness = "fresh" | "stale" | "mixed" | undefined;

export function displayedAggregateFreshness(results: LiveResult[]): MapAggregateFreshness {
  if (results.length === 0) return undefined;
  if (results.every((result) => result.freshness === "stale")) return "stale";
  if (results.some((result) => result.freshness === "stale")) return "mixed";
  return "fresh";
}

export type SessionMapView = {
  mapResults: LiveResult[];
  mapMatchingResults: LiveResult[];
  mapProvinceResults: LiveResult[];
  mapFocus: { latitude: number; longitude: number } | undefined;
  mapFocusResults: LiveResult[];
  mapAggregateFreshness: MapAggregateFreshness;
  mapUnavailableLayers: string[];
};

export function deriveSessionMapView(
  response: AskResponse | undefined,
  provinceResults: LiveResult[] | undefined,
  provinceUnavailable: string[] | undefined,
): SessionMapView {
  const resultById = new Map<string, LiveResult>();
  for (const result of response?.live_results ?? []) resultById.set(result.result_id, result);
  for (const result of provinceResults ?? []) {
    if (!resultById.has(result.result_id)) resultById.set(result.result_id, result);
  }
  const mapResults = [...resultById.values()];
  const mapMatchingResults = response?.live_results ?? [];
  const matchingResultIds = new Set(mapMatchingResults.map((result) => result.result_id));
  return {
    mapResults,
    mapMatchingResults,
    mapProvinceResults: mapResults.filter((result) => !matchingResultIds.has(result.result_id)),
    mapFocus: response?.resolved_location ?? undefined,
    mapFocusResults: response?.live_results ?? [],
    mapAggregateFreshness: displayedAggregateFreshness(mapResults),
    mapUnavailableLayers: [
      ...new Set([...(provinceUnavailable ?? []), ...(response?.unavailable_layers ?? [])]),
    ],
  };
}
