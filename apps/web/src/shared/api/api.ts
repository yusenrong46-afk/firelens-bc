import type { components } from "./api-schema";

export type AskResponse = components["schemas"]["AskResponse"];
export type ConversationTurn = components["schemas"]["ConversationTurn"];
export type ResponseMode = components["schemas"]["ResponseMode"];
export type ErrorEnvelope = components["schemas"]["ErrorEnvelope"];
export type LocationInput = components["schemas"]["LocationInput"];
export type LiveResult = components["schemas"]["LiveResult"];
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
): Promise<AskResponse> {
  const response = await fetch("/api/v1/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, history: history.slice(-6), location }),
    signal: signal ?? null,
  });
  const payload: unknown = await response.json();
  if (!response.ok) {
    throw new FireLensApiError(payload as ErrorEnvelope);
  }
  return payload as AskResponse;
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
