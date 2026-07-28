import type { components } from "./api-schema";

export type AskResponse = components["schemas"]["AskResponse"];
export type ConversationTurn = components["schemas"]["ConversationTurn"];
export type ResponseMode = components["schemas"]["ResponseMode"];
export type ErrorEnvelope = components["schemas"]["ErrorEnvelope"];
export type LocationInput = components["schemas"]["LocationInput"];
export type LiveResult = components["schemas"]["LiveResult"];

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
    signal,
  });
  const payload: unknown = await response.json();
  if (!response.ok) {
    throw new FireLensApiError(payload as ErrorEnvelope);
  }
  return payload as AskResponse;
}
