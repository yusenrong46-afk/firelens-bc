import type { AskResponse, ResponseMode } from "../shared/api/api";
import { isRenderableGeometry } from "../features/near-me/liveResultPresentation";

export type WorkspaceLayout = "chat" | "analysis" | "spatial";

const MAP_INTENT = /\b(?:map|mapped|where|location|located|near|nearby|across|distribution|geograph(?:y|ic|ical))\b/i;
const EXPLICIT_MAP_INTENT = /\b(?:map|mapped)\b/i;

export function questionRequestsMap(question: string | undefined): boolean {
  return Boolean(question && MAP_INTENT.test(question));
}

export function questionExplicitlyRequestsMap(question: string | undefined): boolean {
  return Boolean(question && EXPLICIT_MAP_INTENT.test(question));
}

function hasSpatialLiveResult(response: AskResponse | undefined): boolean {
  return (response?.live_results ?? []).some(isRenderableGeometry);
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
  response,
}: {
  mode: ResponseMode | undefined;
  response: AskResponse | undefined;
}): boolean {
  if (mode !== "live" && mode !== "mixed") return false;
  if (response?.selected_live_result_id) return false;
  const incidentCount = (response?.live_results ?? []).filter(
    (result) => result.kind === "incident",
  ).length;
  // The returned record shape is presentation authority. Question wording is
  // too brittle to decide whether a multi-record answer needs analytical tools.
  return incidentCount > 1;
}

/**
 * Select a presentation shell after response routing has completed. This is
 * deliberately presentation-only and cannot change the answer contract.
 */
export function workspaceLayout({
  analytical,
  spatial,
}: {
  analytical: boolean;
  spatial: boolean;
}): WorkspaceLayout {
  if (analytical) return "analysis";
  if (spatial) return "spatial";
  return "chat";
}
