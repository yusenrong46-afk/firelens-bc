import { Check, ThumbsUp } from "@phosphor-icons/react";
import { useEffect, useState } from "react";

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
  const issueListId = `feedback-categories-${traceId}`;

  useEffect(() => {
    setStatus("idle");
    setShowIssues(false);
  }, [traceId]);

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
    return (
      <div className="feedback-controls" aria-label="Response feedback">
        <p className="feedback-status" role="status"><Check size={15} /> Feedback received</p>
        <p className="feedback-disclosure">Sent: category and response ID. No written message.</p>
      </div>
    );
  }

  return (
    <div className="feedback-controls" aria-label="Response feedback" aria-busy={status === "sending"}>
      <span>Was this useful?</span>
      <button type="button" disabled={status === "sending"} onClick={() => void send("helpful")}>
        <ThumbsUp size={15} /> Helpful
      </button>
      <button
        type="button"
        disabled={status === "sending"}
        onClick={() => setShowIssues(!showIssues)}
        aria-expanded={showIssues}
        aria-controls={issueListId}
      >
        Choose an issue
      </button>
      {showIssues && (
        <div className="feedback-issues" id={issueListId} aria-label="Choose feedback category">
          {ISSUE_CATEGORIES.map((category) => (
            <button key={category.value} type="button" disabled={status === "sending"} onClick={() => void send(category.value)}>
              {category.label}
            </button>
          ))}
        </div>
      )}
      <p className="feedback-disclosure">
        Sends only the selected category and response ID—not a written message.
      </p>
      {status === "sending" && <p className="feedback-status" role="status">Sending feedback…</p>}
      {status === "error" && <p className="feedback-error" role="alert">Feedback could not be sent. Try again.</p>}
    </div>
  );
}
