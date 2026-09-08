import type { AskResponse, LiveResult } from "../../shared/api/api";

// The roster is the list of official records the person is looking at. "The
// second one" counts through it, and the map keeps showing it while the
// conversation narrows to one record. A focused answer about a record already
// on the roster therefore keeps the roster; a new list replaces it; an answer
// with no records (a clarification, an aside) leaves it alone.
export type Roster = {
  results: LiveResult[];
  focus: { latitude: number; longitude: number } | undefined;
  unavailableLayers: string[];
  partialLayers?: string[];
};

export const EMPTY_ROSTER: Roster = { results: [], focus: undefined, unavailableLayers: [] };

export function nextRoster(previous: Roster, response: AskResponse): Roster {
  const results = response.live_results ?? [];
  if (results.length === 0 && !(response.requested_layers ?? []).length) return previous;
  const known = new Set(previous.results.map((result) => result.result_id));
  const focusedOnKnownRecord =
    Boolean(response.selected_live_result_id) && results.every((result) => known.has(result.result_id));
  if (focusedOnKnownRecord && results.length < previous.results.length && !(response.partial_layers ?? []).length) return previous;
  if (focusedOnKnownRecord && results.length < previous.results.length) return { ...previous, partialLayers: [...new Set([...(previous.partialLayers ?? []), ...(response.partial_layers ?? [])])] };
  return {
    results,
    focus: response.resolved_location ?? undefined,
    unavailableLayers: [...new Set(response.unavailable_layers ?? [])],
    partialLayers: [...new Set(response.partial_layers ?? [])],
  };
}
