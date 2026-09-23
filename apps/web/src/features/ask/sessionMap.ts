import type { LiveMapResponse, LiveResult } from "../../shared/api/api";
import type { Roster } from "./roster";

export type MapAggregateFreshness = "fresh" | "stale" | "mixed" | undefined;

export function displayedAggregateFreshness(results: LiveResult[], statuses: LiveMapResponse["layer_statuses"] = []): MapAggregateFreshness {
  const freshness = [...results.map((result) => result.freshness), ...statuses.filter((s) => s.available).map((s) => s.freshness)];
  if (freshness.length === 0) return undefined;
  if (freshness.every((value) => value === "stale")) return "stale";
  if (freshness.some((value) => value === "stale")) return "mixed";
  return freshness.every((value) => value === "fresh") ? "fresh" : undefined;
}

/** Invalid timestamps cannot outrank a known observation; answer wins a tie. */
function latestObservation(answer: LiveResult, mapped: LiveResult): LiveResult {
  const original = Date.parse(answer.retrieved_at);
  const update = Date.parse(mapped.retrieved_at);
  return Number.isFinite(update) && (!Number.isFinite(original) || update > original) ? mapped : answer;
}

export type SessionMapView = {
  mapResults: LiveResult[];
  mapMatchingResults: LiveResult[];
  mapProvinceResults: LiveResult[];
  mapHistoricalResults: LiveResult[];
  mapFocus: { latitude: number; longitude: number } | undefined;
  mapFocusResults: LiveResult[];
  mapAggregateFreshness: MapAggregateFreshness;
  mapUnavailableLayers: string[];
  mapPartialLayers: string[];
  mapGeometryOmissions: { kind: string; count: number }[];
};

export function deriveSessionMapView(
  roster: Roster | undefined,
  provinceResults: LiveResult[] | undefined,
  provinceUnavailable: string[] | undefined,
  contextLayersEnabled = false,
  provinceStatuses?: LiveMapResponse["layer_statuses"],
): SessionMapView {
  const showProvince = !roster || contextLayersEnabled;
  const hasProvince = showProvince && provinceResults !== undefined;
  const statuses = showProvince ? provinceStatuses ?? [] : [];
  const omissions = statuses.filter((status) => (status.omitted_geometry_count ?? 0) > 0)
    .map((status) => ({ kind: status.kind, count: status.omitted_geometry_count! }));
  const sourcePartial = statuses.filter((s) => (s.omitted_geometry_count ?? 0) + (s.omitted_status_count ?? 0) > 0).map((s) => s.kind);
  const answerRecords = roster?.results ?? [];
  const provinceById = new Map((provinceResults ?? []).map((result) => [result.result_id, result]));
  const newerCompleteLayer = (kind: string, observedAt: string | undefined) => {
    const layer = statuses.find((status) => status.kind === kind);
    const observation = layer?.retrieved_at ? Date.parse(layer.retrieved_at) : NaN;
    const answerTime = observedAt ? Date.parse(observedAt) : NaN;
    return hasProvince && layer?.available === true
      && layer.freshness === "fresh" && !layer.omitted_geometry_count && !layer.omitted_status_count
      && Number.isFinite(observation) && Number.isFinite(answerTime) && observation > answerTime;
  };
  const confirmedAbsent = (record: LiveResult) => !provinceById.has(record.result_id)
    && newerCompleteLayer(record.kind, record.retrieved_at);
  const mapHistoricalResults = answerRecords.filter(confirmedAbsent);
  const historicalIds = new Set(mapHistoricalResults.map((record) => record.result_id));
  const mapMatchingResults = answerRecords.filter((record) => !historicalIds.has(record.result_id))
    .map((record) => {
      const mapped = hasProvince ? provinceById.get(record.result_id) : undefined;
      return mapped ? latestObservation(record, mapped) : record;
    });
  const matchingIds = new Set(mapMatchingResults.map((record) => record.result_id));
  const mapProvinceResults = showProvince ? (provinceResults ?? []).filter((record) => !matchingIds.has(record.result_id)) : [];
  const mapResults = [...mapMatchingResults, ...mapProvinceResults];
  return {
    mapResults,
    mapMatchingResults,
    mapProvinceResults,
    mapHistoricalResults,
    mapFocus: roster?.focus,
    mapFocusResults: mapMatchingResults,
    mapAggregateFreshness: displayedAggregateFreshness(mapResults, statuses),
    mapUnavailableLayers: [...new Set([
      ...(hasProvince ? provinceUnavailable ?? [] : []),
      ...(roster?.unavailableLayers ?? []).filter((kind) => !newerCompleteLayer(kind, roster?.observedAt)),
    ])],
    mapGeometryOmissions: omissions,
    mapPartialLayers: [...new Set([
      ...(hasProvince ? sourcePartial : []),
      ...(roster?.partialLayers ?? []).filter((kind) => !newerCompleteLayer(kind, roster?.observedAt)),
    ])],
  };
}
