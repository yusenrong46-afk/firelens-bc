import { Check, Flag, ThumbsUp } from "@phosphor-icons/react";
import { useState } from "react";

import { FeedbackCategory, submitFeedback } from "../../shared/api/api";

const ISSUE_CATEGORIES: { value: FeedbackCategory; label: string }[] = [
  { value: "incorrect_or_unsupported", label: "Incorrect or unsupported" },
  { value: "missing_information", label: "Missing information" },
  { value: "stale_or_wrong_live_data", label: "Stale or wrong live data" },
  { value: "confusing", label: "Confusing" },
  { value: "safety_concern", label: "Safety concern" },
  { value: "accessibility_issue", label: "Accessibility issue" },
];

export function FeedbackControls({ traceId }: { traceId: string }) {
  const [status, setStatus] = useState<"idle" | "sending" | "sent" | "error">("idle");
  const [showIssues, setShowIssues] = useState(false);

  async function send(category: FeedbackCategory) {
    setStatus("sending");
    try {
      await submitFeedback(traceId, category);
      setStatus("sent");
      setShowIssues(false);
    } catch {
      setStatus("error");
    }
  }

  if (status === "sent") {
    return <p className="feedback-status" role="status"><Check size={15} /> Feedback received</p>;
  }

  return (
    <div className="feedback-controls" aria-label="Response feedback">
      <span>Was this useful?</span>
      <button type="button" disabled={status === "sending"} onClick={() => void send("helpful")}>
        <ThumbsUp size={15} /> Helpful
      </button>
      <button type="button" disabled={status === "sending"} onClick={() => setShowIssues(!showIssues)} aria-expanded={showIssues}>
        <Flag size={15} /> Report an issue
      </button>
      {showIssues && (
        <div className="feedback-issues">
          {ISSUE_CATEGORIES.map((category) => (
            <button key={category.value} type="button" disabled={status === "sending"} onClick={() => void send(category.value)}>
              {category.label}
            </button>
          ))}
        </div>
      )}
      {status === "error" && <p className="feedback-error" role="status">Feedback could not be sent. Try again.</p>}
    </div>
  );
}
