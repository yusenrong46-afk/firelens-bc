import { Check, Flag, ThumbsUp } from "@phosphor-icons/react";
import { useEffect, useState } from "react";

import { FeedbackCategory, submitFeedback } from "../../shared/api/api";
import { emitProductEvent } from "../../shared/telemetry";

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
  const feedbackHelpId = `feedback-help-${traceId}`;

  useEffect(() => {
    setStatus("idle");
    setShowIssues(false);
  }, [traceId]);

  async function send(category: FeedbackCategory) {
    setStatus("sending");
    try {
      await submitFeedback(traceId, category);
      emitProductEvent("feedback_submitted");
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
      <span
        id={feedbackHelpId}
        className="response-announcement"
        data-surface-visually-hidden="true"
      >
        Send anonymous feedback about this answer. Feedback does not change the answer.
      </span>
      <button
        type="button"
        disabled={status === "sending"}
        onClick={() => void send("helpful")}
        aria-describedby={feedbackHelpId}
      >
        <ThumbsUp size={15} /> Helpful
      </button>
      <button
        type="button"
        disabled={status === "sending"}
        onClick={() => setShowIssues(!showIssues)}
        aria-expanded={showIssues}
        aria-controls={issueListId}
        aria-describedby={feedbackHelpId}
      >
        <Flag size={15} /> Report
      </button>
      {showIssues && (
        <div className="feedback-issues" id={issueListId} role="group" aria-label="Report reason">
          {ISSUE_CATEGORIES.map((category) => (
            <button key={category.value} type="button" disabled={status === "sending"} onClick={() => void send(category.value)}>
              {category.label}
            </button>
          ))}
        </div>
      )}
      {status === "sending" && <p className="feedback-status" role="status">Sending feedback…</p>}
      {status === "error" && <p className="feedback-error" role="alert">Feedback could not be sent. Try again.</p>}
    </div>
  );
}
