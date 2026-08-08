import {
  Check,
  ChatsCircle,
  Crosshair,
  Info,
  PaperPlaneTilt,
  Trash,
  UserCircle,
  WarningCircle,
} from "@phosphor-icons/react";
import type { ResponseMode } from "../../shared/api/api";
import { FeedbackControls } from "../feedback/FeedbackControls";
import type { AggregateFreshness, Claim } from "./responseModel";
import type { FireLensSession } from "./useFireLensSession";

function ResponseModeBadge({
  mode,
  aggregateFreshness,
}: {
  mode: ResponseMode;
  aggregateFreshness?: AggregateFreshness | undefined;
}) {
  const labels: Record<ResponseMode, string> = {
    grounded: "Reviewed sources",
    partial: "Partially supported",
    background: "General background",
    capability: "FireLens topics",
    scope_redirect: "Outside FireLens scope",
    abstention: "Official current information required",
    live: "Official live records",
    mixed: "Live records + reviewed guidance",
    conflict: "Conflicting reviewed sources",
  };
  if (mode === "live" && aggregateFreshness === "stale") labels.live = "Official cached records";
  else if (mode === "live" && aggregateFreshness === "mixed") labels.live = "Official records — mixed freshness";
  else if (mode === "mixed" && aggregateFreshness === "stale") labels.mixed = "Cached records + reviewed guidance";
  else if (mode === "mixed" && aggregateFreshness === "mixed") labels.mixed = "Mixed-freshness records + reviewed guidance";
  return <span className={`response-badge response-badge--${mode}`}>{labels[mode]}</span>;
}

function ClaimButton({
  claim,
  index,
  selected,
  onSelect,
}: {
  claim: Claim;
  index: number;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      className={`claim-card ${selected ? "claim-card--selected" : ""}`}
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
    >
      <span className="claim-number">{index + 1}</span>
      <span>{claim.text}</span>
      <span className="claim-check">{selected && <Check size={15} weight="bold" />}</span>
    </button>
  );
}

function BackgroundClaim({ claim, index }: { claim: Claim; index: number }) {
  return (
    <div className="claim-card claim-card--background">
      <span className="claim-number">{index + 1}</span>
      <span>{claim.text}</span>
      <Info size={18} aria-hidden="true" />
    </div>
  );
}

export function ConversationPanel({ session }: { session: FireLensSession }) {
  const {
    assistantText,
    citedMode,
    claims,
    clearHistory,
    clearManualLocation,
    earlierTurns,
    history,
    locationLabel,
    locationMessage,
    mode,
    query,
    response,
    selected,
    setLocationLabel,
    setQuery,
    setSelected,
    submit,
    submitQuestion,
    suggestions,
    useApproximateLocation,
    view,
    visibleQuestion,
  } = session;

  return (
    <section className="conversation-panel" aria-label="Question and answer">
      <div className="conversation-toolbar">
        <span><ChatsCircle size={16} /> {history.length} of 6 turns in context</span>
        {(history.length > 0 || view.kind !== "idle") && (
          <button type="button" onClick={clearHistory} aria-label="Clear conversation history">
            <Trash size={15} /> Clear
          </button>
        )}
      </div>
      <div className="conversation-scroll" aria-live="polite">
        {earlierTurns.length > 0 && (
          <div className="history-group" aria-label="Earlier conversation">
            <span className="panel-label">Earlier conversation</span>
            {earlierTurns.map((turn, index) => (
              <div className={`history-turn history-turn--${turn.role}`} key={`${turn.role}-${index}-${turn.content}`}>
                <strong>{turn.role === "user" ? "You" : "FireLens"}</strong>
                <p>{turn.content}</p>
              </div>
            ))}
          </div>
        )}
        {visibleQuestion && (
          <div className="question-block">
            <span className="panel-label">Your question</span>
            <div className="question-line">
              <div className="question-bubble"><p>{visibleQuestion}</p><small>Current request</small></div>
              <UserCircle size={38} weight="fill" />
            </div>
          </div>
        )}

        <div className={`assistant-message assistant-message--${view.kind}`}>
          <img src="/assets/firelens-mark.png" alt="" />
          <div>
            <span className="assistant-name">FireLens BC</span>
            {mode && <ResponseModeBadge mode={mode} aggregateFreshness={response?.aggregate_freshness ?? undefined} />}
            <p>{assistantText}</p>
            {response?.trace_id && <FeedbackControls traceId={response.trace_id} />}
            {(view.kind === "unavailable" || (view.kind === "error" && view.retryable)) && (
              <button className="retry-button" type="button" onClick={() => void submitQuestion(visibleQuestion ?? "")}>
                Retry this question
              </button>
            )}
          </div>
        </div>

        {view.kind === "answer" && claims.length > 0 && (
          <div className="claim-group">
            <span className="panel-label">
              {citedMode ? "Sources supporting this answer" : "General background in this answer"}
            </span>
            <div className="claim-list">
              {claims.map((claim, index) => citedMode ? (
                <ClaimButton key={claim.claim_id} claim={claim} index={index} selected={selected === index} onSelect={() => setSelected(index)} />
              ) : (
                <BackgroundClaim key={claim.claim_id} claim={claim} index={index} />
              ))}
            </div>
          </div>
        )}

        {view.kind === "abstention" && (
          <div className="abstention-card">
            <WarningCircle size={22} />
            <div>
              <strong>FireLens did not generate guidance</strong>
              <p>Reason: {view.response.reason_code || "insufficient evidence"}</p>
              {(view.response.limitations ?? []).map((item) => <p key={item}>{item}</p>)}
            </div>
          </div>
        )}

        {suggestions.length > 0 && (
          <div className="suggestion-group" aria-label="Suggested questions">
            <span className="panel-label">Try asking</span>
            <div>
              {suggestions.map((suggestion) => (
                <button type="button" key={suggestion} onClick={() => void submitQuestion(suggestion)} disabled={view.kind === "loading"}>
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      <form className="composer" onSubmit={submit}>
        <div className="composer-input">
          <input
            aria-label="Ask a preparedness question"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Ask a preparedness question…"
            maxLength={2000}
            disabled={view.kind === "loading"}
          />
          <button type="submit" disabled={!query.trim() || view.kind === "loading"} aria-label="Send question">
            <PaperPlaneTilt size={20} weight="fill" />
          </button>
        </div>
        <div className="location-row">
          <input
            aria-label="City or community for live questions"
            value={locationLabel}
            onChange={(event) => {
              setLocationLabel(event.target.value);
              clearManualLocation();
            }}
            placeholder="City or community for live questions (optional)"
            maxLength={120}
            disabled={view.kind === "loading"}
          />
          <button type="button" onClick={useApproximateLocation} disabled={view.kind === "loading"}>
            <Crosshair size={16} /> Use approximate location
          </button>
        </div>
        {locationMessage && <p className="location-message" role="status">{locationMessage}</p>}
        <p><Info size={16} /> For property-specific risk assessments or current fire conditions, consult the appropriate official service.</p>
      </form>
    </section>
  );
}
