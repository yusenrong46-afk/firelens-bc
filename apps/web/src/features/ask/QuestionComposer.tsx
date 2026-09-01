import { Info, PaperPlaneTilt } from "@phosphor-icons/react";
import type { FormEvent, RefObject } from "react";

export function QuestionComposer({
  continuationPending = false,
  idle,
  loading,
  onQueryChange,
  onSubmit,
  query,
  inputRef,
}: {
  continuationPending?: boolean;
  idle: boolean;
  loading: boolean;
  onQueryChange: (query: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  query: string;
  inputRef?: RefObject<HTMLInputElement | null>;
}) {
  return (
    <form className={`composer ${idle ? "composer--idle" : ""}`} onSubmit={onSubmit}>
      <div className="composer-input">
        <input
          ref={inputRef}
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
        <p className={idle ? "response-announcement" : undefined}><Info size={16} /> Sources and status boundaries appear with each answer.</p>
      )}
    </form>
  );
}
