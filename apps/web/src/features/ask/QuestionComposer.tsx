import { Info, PaperPlaneTilt } from "@phosphor-icons/react";
import type { FormEvent } from "react";

export function QuestionComposer({
  idle,
  loading,
  onQueryChange,
  onSubmit,
  query,
}: {
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
          placeholder="Ask about a fire, a B.C. place, or preparedness…"
          maxLength={2000}
          disabled={loading}
        />
        <button type="submit" disabled={!query.trim() || loading} aria-label="Send question">
          <PaperPlaneTilt size={20} weight="fill" />
        </button>
      </div>
      <p>
        <Info size={16} /> Live facts stay tied to official records. Reviewed guidance
        and general background are labelled separately.
      </p>
    </form>
  );
}
