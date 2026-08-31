import type { FireLensSession } from "./useFireLensSession";

export type ConversationState = FireLensSession["view"]["kind"];

export function announcementForState(
  state: ConversationState,
  previousState: ConversationState,
): string {
  if (state === "loading") return "FireLens is working on your question.";
  if (state === "answer") {
    return previousState === "unavailable" || previousState === "error"
      ? "FireLens recovered and an answer is ready."
      : "FireLens response ready.";
  }
  if (state === "abstention") return "FireLens completed the request but could not publish a supported answer.";
  if (state === "unavailable") return "FireLens is temporarily unavailable.";
  if (state === "error") return "FireLens could not complete this question.";
  return "";
}
