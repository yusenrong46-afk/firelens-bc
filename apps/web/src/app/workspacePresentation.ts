import type { AskResponse, ResponseMode } from "../shared/api/api";

const MAP_INTENT = /\b(?:map|mapped|where|location|located|near|nearby|across|distribution|geograph(?:y|ic|ical))\b/i;
const MAP_FIRST_INTENT = /\b(?:map|mapped|across|distribution|geograph(?:y|ic|ical))\b/i;

export function questionRequestsMap(question: string | undefined): boolean {
  return Boolean(question && MAP_INTENT.test(question));
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
  if ((mode === "live" || mode === "mixed") && question && MAP_FIRST_INTENT.test(question)) {
    return "map";
  }
  return "evidence";
}
