import type { components } from "./api-schema";

export type AskResponse = components["schemas"]["AskResponse"];
export type AnswerSection = components["schemas"]["AnswerSection"];
export type AnswerSectionKind = components["schemas"]["AnswerSectionKind"];
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

type ResponseMetadata = {
  responseStatus?: number | undefined;
  requestId?: string | undefined;
  contentType?: string | undefined;
};

export type FireLensClientFailureKind = "transport" | "response_read" | "invalid_json";

export class FireLensClientError extends Error {
  readonly failureKind: FireLensClientFailureKind;
  readonly endpoint: string;
  readonly responseStatus: number | undefined;
  readonly requestId: string | undefined;
  readonly contentType: string | undefined;
  readonly cause: unknown;

  constructor(
    failureKind: FireLensClientFailureKind,
    endpoint: string,
    metadata: ResponseMetadata = {},
    cause?: unknown,
  ) {
    super(`FireLens ${failureKind.replaceAll("_", " ")} failure for ${endpoint}`);
    this.name = "FireLensClientError";
    this.failureKind = failureKind;
    this.endpoint = endpoint;
    this.responseStatus = metadata.responseStatus;
    this.requestId = metadata.requestId;
    this.contentType = metadata.contentType;
    this.cause = cause;
  }
}

export class FireLensApiError extends Error {
  readonly detail: ErrorEnvelope;
  readonly failureKind = "api" as const;
  readonly responseStatus: number | undefined;
  readonly requestId: string | undefined;
  readonly contentType: string | undefined;

  constructor(detail: ErrorEnvelope, metadata: ResponseMetadata = {}) {
    super(detail.message);
    this.name = "FireLensApiError";
    this.detail = detail;
    this.responseStatus = metadata.responseStatus;
    this.requestId = metadata.requestId ?? detail.trace_id;
    this.contentType = metadata.contentType;
  }
}

function isAbort(error: unknown, signal?: AbortSignal | null): boolean {
  return signal?.aborted === true || (error instanceof DOMException && error.name === "AbortError");
}

function responseMetadata(response: Response): ResponseMetadata {
  return {
    responseStatus: response.status,
    requestId: response.headers.get("x-request-id") ?? response.headers.get("x-trace-id") ?? undefined,
    contentType: response.headers.get("content-type") ?? undefined,
  };
}

async function fetchResponse(
  endpoint: string,
  init?: RequestInit,
): Promise<Response> {
  try {
    return await fetch(endpoint, init);
  } catch (error) {
    if (isAbort(error, init?.signal)) throw error;
    throw new FireLensClientError("transport", endpoint, {}, error);
  }
}

async function readJsonResponse(response: Response, endpoint: string): Promise<unknown> {
  const metadata = responseMetadata(response);
  let body: string;
  try {
    body = await response.text();
  } catch (error) {
    if (isAbort(error)) throw error;
    throw new FireLensClientError("response_read", endpoint, metadata, error);
  }
  try {
    return JSON.parse(body) as unknown;
  } catch (error) {
    throw new FireLensClientError("invalid_json", endpoint, metadata, error);
  }
}

function apiError(payload: unknown, response: Response): FireLensApiError {
  return new FireLensApiError(payload as ErrorEnvelope, responseMetadata(response));
}

export async function askFireLens(
  question: string,
  history: ConversationTurn[] = [],
  location?: LocationInput,
  signal?: AbortSignal,
  context?: MapContext,
): Promise<AskResponse> {
  const endpoint = "/api/v1/ask";
  const response = await fetchResponse(endpoint, {
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
  const payload = await readJsonResponse(response, endpoint);
  if (!response.ok) {
    throw apiError(payload, response);
  }
  return payload as AskResponse;
}

export async function fetchOfficialMap(signal?: AbortSignal): Promise<LiveMapResponse> {
  const endpoint = "/api/v1/live/map?layers=incidents,perimeters,evacuations";
  const response = await fetchResponse(endpoint, { signal: signal ?? null });
  // Clone so a test double may safely reuse its response for the following Ask call.
  // Real fetch responses are unique; this does not change production semantics.
  const payload = await readJsonResponse(response.clone(), endpoint);
  if (!response.ok) {
    throw apiError(payload, response);
  }
  return payload as LiveMapResponse;
}

export async function fetchNearbyOfficialRecords(
  request: NearMeRequest,
  signal?: AbortSignal,
): Promise<NearMeResponse> {
  const endpoint = "/api/v1/live/nearby";
  const response = await fetchResponse(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
    signal: signal ?? null,
  });
  const payload = await readJsonResponse(response, endpoint);
  if (!response.ok) {
    throw apiError(payload, response);
  }
  return payload as NearMeResponse;
}

export async function submitFeedback(
  traceId: string,
  category: FeedbackCategory,
  signal?: AbortSignal,
): Promise<void> {
  const endpoint = "/api/v1/feedback";
  const response = await fetchResponse(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ trace_id: traceId, category }),
    signal: signal ?? null,
  });
  if (!response.ok) {
    const payload = await readJsonResponse(response, endpoint);
    throw apiError(payload, response);
  }
}
