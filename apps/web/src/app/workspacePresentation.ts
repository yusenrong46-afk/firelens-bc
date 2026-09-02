import type { AskResponse, ResponseMode } from "../shared/api/api";
import { isRenderableGeometry } from "../features/near-me/liveResultPresentation";

export type WorkspaceLayout = "chat" | "analysis" | "spatial";

function hasSpatialLiveResult(response: AskResponse | undefined): boolean {
  return (response?.live_results ?? []).some(isRenderableGeometry);
}

export function shouldOfferContextMap({
  mode,
  response,
}: {
  mode: ResponseMode | undefined;
  question?: string | undefined;
  response: AskResponse | undefined;
}): boolean {
  if (response?.presentation_shell === "spatial" || response?.presentation_shell === "analysis") {
    return mode === "live" || mode === "mixed";
  }
  if (mode !== "live" && mode !== "mixed") return false;
  return Boolean(response?.resolved_location || hasSpatialLiveResult(response));
}

export function preferredContextSurface({
  mode,
  response,
}: {
  mode: ResponseMode | undefined;
  question?: string | undefined;
  response?: AskResponse | undefined;
}): "evidence" | "map" {
  if (response?.presentation_shell === "spatial") return "map";
  if ((mode === "live" || mode === "mixed") && response?.presentation_shell === "analysis") {
    return "evidence";
  }
  return "evidence";
}

export function questionExplicitlyRequestsMap(_question: string | undefined): boolean {
  return false;
}

export function shouldUseAnalyticalWorkspace({
  mode,
  response,
}: {
  mode: ResponseMode | undefined;
  response: AskResponse | undefined;
}): boolean {
  if (mode !== "live") return false;
  if (response?.selected_live_result_id) return false;
  return response?.presentation_shell === "analysis";
}

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
