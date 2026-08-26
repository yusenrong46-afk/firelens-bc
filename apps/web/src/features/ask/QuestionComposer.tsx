import { Info, PaperPlaneTilt } from "@phosphor-icons/react";
import type { FormEvent } from "react";

export function QuestionComposer({
  continuationPending = false,
  idle,
  loading,
  onQueryChange,
  onSubmit,
  query,
}: {
  continuationPending?: boolean;
  idle: boolean;
  loading: boolean;
  onQueryChange: (query: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  query: string;
}) {
  return (
    <form className={`composer ${idle ? "composer--idle" : ""}`} onSubmit={onSubmit}>
      <div className="composer-input">
        <input
          aria-label="Ask FireLens a question"
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
          placeholder={continuationPending
            ? "Ask a new question…"
            : "Ask about a fire, a B.C. place, or preparedness…"}
          maxLength={2000}
          disabled={loading}
        />
        <button type="submit" disabled={!query.trim() || loading} aria-label="Send question">
          <PaperPlaneTilt size={20} weight="fill" />
        </button>
      </div>
      {continuationPending ? (
        <p><Info size={16} /> Use the community field above to continue this task. Type here only to start a new question.</p>
      ) : (
        <p><Info size={16} /> Sources and status boundaries appear with each answer.</p>
      )}
    </form>
  );
}
