import type { AskResponse, ResponseMode } from "../../shared/api/api";

export type AnswerView = { kind: "answer"; question: string; response: AskResponse };
export type AbstentionView = { kind: "abstention"; question: string; response: AskResponse };
export type MessageView = {
  kind: "idle" | "loading" | "unavailable" | "error";
  question?: string;
  message?: string;
  retryable?: boolean;
};
export type ViewState = AnswerView | AbstentionView | MessageView;

export type Claim = NonNullable<AskResponse["claims"]>[number];
export type Evidence = NonNullable<AskResponse["evidence"]>[number];
export type AggregateFreshness = NonNullable<AskResponse["aggregate_freshness"]>;
export type Support = NonNullable<Claim["supports"]>[number];

export const INITIAL_SUGGESTIONS = [
  "What belongs in a grab-and-go bag?",
  "What is the difference between an evacuation alert and order?",
  "How can I reduce wildfire risk around my home?",
  "What should I know about wildfire smoke?",
  "What do wildfire stages of control mean?",
  "How do structure-protection sprinklers work?",
];

export function getResponseMode(response: AskResponse): ResponseMode {
  if (response.response_mode) return response.response_mode;
  if (response.status === "abstention") return "abstention";
  if ((response.claims ?? []).some((claim) => (claim.supports ?? []).length > 0)) {
    return "grounded";
  }
  return "background";
}

export function responseText(response: AskResponse): string {
  if (response.answer) return response.answer;
  const mode = getResponseMode(response);
  if (mode === "capability") return "I can help you explore the reviewed FireLens guidance.";
  if (mode === "scope_redirect") return "Use the related official service for current information.";
  return "FireLens could not produce an answer for this request.";
}
