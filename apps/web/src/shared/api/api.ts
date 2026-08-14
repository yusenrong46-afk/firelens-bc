import type { components } from "./api-schema";

export type AskResponse = components["schemas"]["AskResponse"];
export type ConversationTurn = components["schemas"]["ConversationTurn"];
export type ResponseMode = components["schemas"]["ResponseMode"];
export type ErrorEnvelope = components["schemas"]["ErrorEnvelope"];
export type LocationInput = components["schemas"]["LocationInput"];
export type MapContext = components["schemas"]["MapContext"];
export type LiveResult = components["schemas"]["LiveResult"];
export type LiveMapResponse = components["schemas"]["LiveMapResponse"];
export type NearMeRequest = components["schemas"]["NearMeRequest"];
export type NearMeResponse = components["schemas"]["NearMeResponse"];
export type FeedbackCategory = components["schemas"]["FeedbackRequest"]["category"];

export class FireLensApiError extends Error {
  readonly detail: ErrorEnvelope;

  constructor(detail: ErrorEnvelope) {
    super(detail.message);
    this.name = "FireLensApiError";
    this.detail = detail;
  }
}

export async function askFireLens(
  question: string,
  history: ConversationTurn[] = [],
  location?: LocationInput,
  signal?: AbortSignal,
  context?: MapContext,
): Promise<AskResponse> {
  const response = await fetch("/api/v1/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question,
      history: history.slice(-6),
      location,
      context: context ?? {},
    }),
    signal: signal ?? null,
  });
  const payload: unknown = await response.json();
  if (!response.ok) {
    throw new FireLensApiError(payload as ErrorEnvelope);
  }
  return payload as AskResponse;
}

export async function fetchOfficialMap(signal?: AbortSignal): Promise<LiveMapResponse> {
  const response = await fetch(
    "/api/v1/live/map?layers=incidents,perimeters,evacuations",
    { signal: signal ?? null },
  );
  // Clone so a test double may safely reuse its response for the following Ask call.
  // Real fetch responses are unique; this does not change production semantics.
  const payload: unknown = await response.clone().json();
  if (!response.ok) {
    throw new FireLensApiError(payload as ErrorEnvelope);
  }
  return payload as LiveMapResponse;
}

export async function fetchNearbyOfficialRecords(
  request: NearMeRequest,
  signal?: AbortSignal,
): Promise<NearMeResponse> {
  const response = await fetch("/api/v1/live/nearby", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
    signal: signal ?? null,
  });
  const payload: unknown = await response.json();
  if (!response.ok) {
    throw new FireLensApiError(payload as ErrorEnvelope);
  }
  return payload as NearMeResponse;
}

export async function submitFeedback(
  traceId: string,
  category: FeedbackCategory,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch("/api/v1/feedback", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ trace_id: traceId, category }),
    signal: signal ?? null,
  });
  if (!response.ok) {
    const payload: unknown = await response.json();
    throw new FireLensApiError(payload as ErrorEnvelope);
  }
}
