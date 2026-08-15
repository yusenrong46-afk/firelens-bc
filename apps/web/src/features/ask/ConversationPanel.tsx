import {
  ArrowSquareOut,
  Check,
  ChatsCircle,
  Crosshair,
  Info,
  PaperPlaneTilt,
  Trash,
  UserCircle,
  WarningCircle,
} from "@phosphor-icons/react";
import type { AskResponse, ResponseMode } from "../../shared/api/api";
import { FeedbackControls } from "../feedback/FeedbackControls";
import { abstentionPresentation } from "./abstentionPresentation";
import { answerSectionAuthority, getAnswerSections } from "./answerSections";
import type { AggregateFreshness, Claim } from "./responseModel";
import type { FireLensSession } from "./useFireLensSession";

function ResponseModeBadge({
  mode,
  aggregateFreshness,
  answerSectionKinds = [],
  reasonCode,
}: {
  mode: ResponseMode;
  aggregateFreshness?: AggregateFreshness | undefined;
  answerSectionKinds?: string[] | undefined;
  reasonCode?: AskResponse["reason_code"] | undefined;
}) {
  const labels: Record<ResponseMode, string> = {
    grounded: "Reviewed sources",
    partial: "Partially supported",
    background: "General background",
    capability: "FireLens topics",
    scope_redirect: "Related official service",
    abstention: "Could not complete",
    live: "Official live records",
    mixed: "Live records + reviewed guidance",
    conflict: "Conflicting reviewed sources",
    requires_input: "One detail needed",
  };
  if (mode === "abstention") labels.abstention = abstentionPresentation(reasonCode).badge;
  if (mode === "mixed" && answerSectionKinds.includes("conflicting_guidance")) {
    labels.mixed = "Live records + conflicting sources";
  } else if (mode === "mixed" && answerSectionKinds.includes("general_background")) {
    labels.mixed = "Live records + general background";
  } else if (mode === "mixed" && answerSectionKinds.includes("official_handoff")) {
    labels.mixed = "Live records + official link";
  }
  if (mode === "live" && aggregateFreshness === "stale") labels.live = "Official cached records";
  else if (mode === "live" && aggregateFreshness === "mixed") labels.live = "Official records — mixed freshness";
  else if (mode === "mixed" && aggregateFreshness === "stale") labels.mixed = labels.mixed.replace("Live records", "Cached records");
  else if (mode === "mixed" && aggregateFreshness === "mixed") labels.mixed = labels.mixed.replace("Live records", "Mixed-freshness records");
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
    requiresLocation,
    selected,
    setLocationLabel,
    setQuery,
    setSelected,
    submit,
    submitLocation,
    submitQuestion,
    suggestions,
    useApproximateLocation,
    view,
    visibleQuestion,
  } = session;
  const answerSections = getAnswerSections(response);
  const visibleLimitations = Array.from(
    new Set((response?.limitations ?? []).map((item) => item.trim()).filter(Boolean)),
  );

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
            {mode && (
              <ResponseModeBadge
                mode={mode}
                aggregateFreshness={response?.aggregate_freshness ?? undefined}
                answerSectionKinds={answerSections.map((section) => section.kind)}
                reasonCode={response?.reason_code ?? undefined}
              />
            )}
            {answerSections.length > 0 ? (
              <div className="answer-sections" aria-label="Authority-labelled answer">
                {answerSections.map((section) => (
                  <section className="answer-section" key={section.kind}>
                    <span className="answer-section__authority">{answerSectionAuthority(section.kind)}</span>
                    <h2>{section.heading}</h2>
                    <p>{section.text}</p>
                  </section>
                ))}
              </div>
            ) : (
              <p>{assistantText}</p>
            )}
            {view.kind === "answer" && visibleLimitations.length > 0 && (
              <div className="answer-limitations" aria-label="Answer limitations" role="status">
                <WarningCircle size={19} aria-hidden="true" />
                <div>
                  <strong>Important limits</strong>
                  <ul>
                    {visibleLimitations.map((item) => <li key={item}>{item}</li>)}
                  </ul>
                </div>
              </div>
            )}
            {(response?.related_links ?? []).length > 0 && (
              <div className="related-service-links" aria-label="Related official services">
                {(response?.related_links ?? []).map((item) => (
                  <a key={item.url} href={item.url} target="_blank" rel="noreferrer">
                    <span><strong>{item.title}</strong><small>{item.description}</small></span>
                    <ArrowSquareOut size={18} aria-hidden="true" />
                  </a>
                ))}
              </div>
            )}
            {response?.trace_id && <FeedbackControls traceId={response.trace_id} />}
            {(view.kind === "unavailable" || (view.kind === "error" && view.retryable)) && (
              <button className="retry-button" type="button" onClick={() => void submitQuestion(visibleQuestion ?? "")}>
                Retry this question
              </button>
            )}
          </div>
        </div>

        {requiresLocation && (
          <form className="location-request" onSubmit={submitLocation}>
            <span className="panel-label">Continue this task</span>
            <strong>{response?.required_input?.prompt}</strong>
            <p>FireLens sends only a community label or coordinates rounded to two decimals for this request.</p>
            <div className="location-request__actions">
              <input
                aria-label="BC community for this question"
                value={locationLabel}
                onChange={(event) => {
                  setLocationLabel(event.target.value);
                  clearManualLocation();
                }}
                placeholder="Enter a BC community"
                maxLength={120}
                disabled={view.kind === "loading"}
              />
              <button type="submit" disabled={!locationLabel.trim() || view.kind === "loading"}>
                Continue
              </button>
              <button type="button" onClick={useApproximateLocation} disabled={view.kind === "loading"}>
                <Crosshair size={16} /> Use approximate location
              </button>
            </div>
            {locationMessage && <p className="location-message" role="status">{locationMessage}</p>}
          </form>
        )}

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
              {visibleLimitations.map((item) => <p key={item}>{item}</p>)}
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
            aria-label="Ask FireLens a question"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Ask about a mapped fire or anything else…"
            maxLength={2000}
            disabled={view.kind === "loading"}
          />
          <button type="submit" disabled={!query.trim() || view.kind === "loading"} aria-label="Send question">
            <PaperPlaneTilt size={20} weight="fill" />
          </button>
        </div>
        <p><Info size={16} /> Official current facts stay tied to their source. General knowledge is labelled separately.</p>
      </form>
    </section>
  );
}
