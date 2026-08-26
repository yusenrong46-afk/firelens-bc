import type { AskResponse, ResponseMode } from "../shared/api/api";

const MAP_INTENT = /\b(?:map|mapped|where|location|located|near|nearby|across|distribution|geograph(?:y|ic|ical))\b/i;
const EXPLICIT_MAP_INTENT = /\b(?:map|mapped)\b/i;
const ANALYSIS_INTENT = /\b(?:breakdown|counts?|distribution|geograph(?:y|ic|ical)|how many|by\s+(?:fire centre|status))\b/i;

export function questionRequestsMap(question: string | undefined): boolean {
  return Boolean(question && MAP_INTENT.test(question));
}

export function questionExplicitlyRequestsMap(question: string | undefined): boolean {
  return Boolean(question && EXPLICIT_MAP_INTENT.test(question));
}

export function questionRequestsAnalysis(question: string | undefined): boolean {
  return Boolean(question && ANALYSIS_INTENT.test(question));
}

function hasSpatialLiveResult(response: AskResponse | undefined): boolean {
  return (response?.live_results ?? []).some((result) => {
    const geometry = result.geometry as { type?: string; coordinates?: unknown } | null | undefined;
    return Boolean(geometry?.type && geometry.coordinates != null);
  });
}

export function shouldOfferContextMap({
  mode,
  question,
  response,
}: {
  mode: ResponseMode | undefined;
  question: string | undefined;
  response: AskResponse | undefined;
}): boolean {
  if (mode !== "live" && mode !== "mixed") return false;
  return Boolean(
    response?.resolved_location
    || hasSpatialLiveResult(response)
    || questionRequestsMap(question),
  );
}

export function preferredContextSurface({
  mode,
  question,
}: {
  mode: ResponseMode | undefined;
  question: string | undefined;
}): "evidence" | "map" {
  if ((mode === "live" || mode === "mixed") && questionExplicitlyRequestsMap(question)) {
    return "map";
  }
  return "evidence";
}

export function shouldUseAnalyticalWorkspace({
  mode,
  question,
  response,
}: {
  mode: ResponseMode | undefined;
  question: string | undefined;
  response: AskResponse | undefined;
}): boolean {
  if (mode !== "live" && mode !== "mixed") return false;
  const incidentCount = (response?.live_results ?? []).filter(
    (result) => result.kind === "incident",
  ).length;
  return incidentCount > 1 && questionRequestsAnalysis(question);
}
