import type { LiveResult } from "../../shared/api/api";
import type { Roster } from "./roster";

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
  roster: Roster | undefined,
  provinceResults: LiveResult[] | undefined,
  provinceUnavailable: string[] | undefined,
  contextLayersEnabled = false,
): SessionMapView {
  const mapMatchingResults = roster?.results ?? [];
  if (!roster) {
    const idleResults = provinceResults ?? [];
    return {
      mapResults: idleResults,
      mapMatchingResults: [],
      mapProvinceResults: idleResults,
      mapFocus: undefined,
      mapFocusResults: [],
      mapAggregateFreshness: displayedAggregateFreshness(idleResults),
      mapUnavailableLayers: [...new Set(provinceUnavailable ?? [])],
    };
  }
  if (!contextLayersEnabled) {
    return {
      mapResults: mapMatchingResults,
      mapMatchingResults,
      mapProvinceResults: [],
      mapFocus: roster.focus,
      mapFocusResults: mapMatchingResults,
      mapAggregateFreshness: displayedAggregateFreshness(mapMatchingResults),
      mapUnavailableLayers: roster.unavailableLayers,
    };
  }
  const resultById = new Map<string, LiveResult>();
  for (const result of mapMatchingResults) resultById.set(result.result_id, result);
  for (const result of provinceResults ?? []) {
    if (!resultById.has(result.result_id)) resultById.set(result.result_id, result);
  }
  const mapResults = [...resultById.values()];
  const matchingResultIds = new Set(mapMatchingResults.map((result) => result.result_id));
  return {
    mapResults,
    mapMatchingResults,
    mapProvinceResults: mapResults.filter((result) => !matchingResultIds.has(result.result_id)),
    mapFocus: roster.focus,
    mapFocusResults: mapMatchingResults,
    mapAggregateFreshness: displayedAggregateFreshness(mapResults),
    mapUnavailableLayers: [...new Set([...(provinceUnavailable ?? []), ...roster.unavailableLayers])],
  };
}
