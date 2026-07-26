import type { components } from "./api-schema";

export type AskResponse = components["schemas"]["AskResponse"];
export type ErrorEnvelope = components["schemas"]["ErrorEnvelope"];

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
  signal?: AbortSignal,
): Promise<AskResponse> {
  const response = await fetch("/api/v1/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
    signal,
  });
  const payload: unknown = await response.json();
  if (!response.ok) {
    throw new FireLensApiError(payload as ErrorEnvelope);
  }
  return payload as AskResponse;
}
