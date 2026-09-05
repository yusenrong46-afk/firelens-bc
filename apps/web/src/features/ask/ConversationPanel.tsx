import { Crosshair, MapTrifold, Sparkle, WarningCircle } from "@phosphor-icons/react";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { FeedbackControls } from "../feedback/FeedbackControls";
import { resultDisplayName } from "../near-me/liveResultPresentation";
import { AnswerBody } from "./AnswerBody";
import { LiveAnswerSummary } from "./LiveAnswerSummary";
import { AuthorityHandoffCards } from "./AuthorityHandoffCards";
import { abstentionPresentation } from "./abstentionPresentation";
import { AskStartPanel } from "./AskStartPanel";
import { getAnswerSections } from "./answerSections";
import {
  ConversationToolbar,
  revealAssistantMessage,
  ServiceFailureState,
  SuggestedQuestions,
} from "./ConversationPresentation";
import { ConversationEvidenceDetails } from "./ConversationEvidenceDetails";
import { ResponseModeBadge } from "./responseModeBadge";
import { announcementForState, type ConversationState } from "./conversationAnnouncements";
import type { FireLensSession } from "./useFireLensSession";
import "./conversationAccessibility.css";

export function ConversationPanel({
  session,
  analytical = false,
  analysisSlot,
  onOpenEvidence,
  onOpenMap,
  contextOpen = false,
  contextSurface = "evidence",
  contextChips,
}: {
  session: FireLensSession;
  analytical?: boolean;
  analysisSlot?: ReactNode;
  onOpenEvidence?: () => void;
  onOpenMap?: () => void;
  contextOpen?: boolean;
  contextSurface?: "evidence" | "map";
  contextChips?: ReactNode;
}) {
  const {
    assistantText,
    liveSummary,
    claims,
    clearHistory,
    clearManualLocation,
    earlierTurns,
    locationLabel,
    locationMessage,
    mode,
    response,
    requiresLocation,
    setLocationLabel,
    setQuery,
    setSelected,
    submitLocation,
    submitQuestion,
    suggestions,
    useApproximateLocation,
    view,
    visibleQuestion,
    selectedLiveResultId,
    setSelectedLiveResultId,
    mapResults,
    activeLocation,
  } = session;
  const answerSections = getAnswerSections(response);
  const hasLiveResults = !analytical && view.kind === "answer"
    && (mode === "live" || mode === "mixed") && (response?.live_results?.length ?? 0) > 0;
  const visibleLimitations = Array.from(
    new Set((response?.limitations ?? []).map((item) => item.trim()).filter(Boolean)),
  );
  const allClaimsQuoteOnly = claims.length > 0
    && claims.every((claim) => claim.publication?.kind === "official_quote_only");
  const selectedRecord = [...mapResults, ...(response?.live_results ?? [])].find(
    (item) => item.result_id === selectedLiveResultId,
  );
  const previousState = useRef<ConversationState>(view.kind);
  const [announcement, setAnnouncement] = useState("");
  const [selectionAnnouncement, setSelectionAnnouncement] = useState("");
  const assistantRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    revealAssistantMessage(assistantRef.current, view.kind !== "idle");
  }, [response, view.kind]);

  const askSuggestedQuestion = useCallback((question: string) => {
    const place = locationLabel.trim();
    const normalized = (place ? question.replaceAll("{place}", place) : question).trim();
    if (!normalized) return;
    setQuery("");
    setSelectionAnnouncement(`Asking: ${normalized}`);
    void submitQuestion(normalized);
  }, [locationLabel, setQuery, submitQuestion]);

  useEffect(() => {
    const priorState = previousState.current;
    if (priorState === view.kind) return;
    previousState.current = view.kind;
    setAnnouncement(announcementForState(view.kind, priorState));
  }, [view.kind]);

  const followUpComposer = view.kind !== "idle" ? (
    <div className="pc-composer-stack pc-composer-stack--follow-up">
      {contextChips}
    </div>
  ) : null;

  return (
    <section className={`conversation-panel ${analytical ? "conversation-panel--analytical" : ""} ${view.kind === "idle" ? "conversation-panel--idle" : ""}`} id="conversation" aria-label="Question and answer" tabIndex={-1}>
      <div className="conversation-scroll">
        <span
          className="response-announcement"
          data-surface-visually-hidden="true"
          role="status"
          aria-live="polite"
          aria-atomic="true"
        >
          {announcement}
        </span>
        <span className="response-announcement" role="status" aria-live="polite" aria-atomic="true">{selectionAnnouncement}</span>
        {earlierTurns.length > 0 && (
          <details className="history-group" aria-label="Earlier conversation">
            <summary>Earlier conversation</summary>
            {earlierTurns.map((turn, index) => (
              <div className={`history-turn history-turn--${turn.role}`} key={`${turn.role}-${index}-${turn.content}`}>
                <strong>{turn.role === "user" ? "You" : "FireLens"}</strong>
                <p>{turn.content}</p>
              </div>
            ))}
          </details>
        )}

        {view.kind === "idle" && (
          <>
            <AskStartPanel
              locationLabel={locationLabel}
              currentState={liveSummary ? assistantText : undefined}
              composer={(
                <div className="pc-composer-stack">
                  {contextChips}
                </div>
              )}
              onLocationChange={(value) => { setLocationLabel(value); clearManualLocation(); }}
              onUseApproximateLocation={useApproximateLocation}
              onSelectQuestion={askSuggestedQuestion}
            />
          </>
        )}

        {view.kind !== "idle" && <div className={`assistant-message assistant-message--${view.kind}`} ref={assistantRef}>
          <div className="answer-panel">
            <div className="answer-panel__header">
            <span className="assistant-name"><Sparkle size={20} weight="fill" aria-hidden="true" /> Answer</span>
            {mode && (
              <ResponseModeBadge
                mode={mode}
                aggregateFreshness={response?.aggregate_freshness ?? undefined}
                answerSectionKinds={answerSections.map((section) => section.kind)}
                reasonCode={response?.reason_code ?? undefined}
                response={response}
              />
            )}
            </div>
            {view.kind === "answer" ? (
              <AnswerBody
                response={response}
                assistantText={assistantText}
                analytical={analytical}
                footer={!analytical && response?.trace_id ? <FeedbackControls traceId={response.trace_id} /> : undefined}
              />
            ) : view.kind === "unavailable" || view.kind === "error" ? (
              <ServiceFailureState
                message={assistantText}
                retryable={view.kind === "unavailable" || view.retryable === true}
                onRetry={() => void submitQuestion(visibleQuestion ?? "")}
              />
            ) : (
              <p>{assistantText}</p>
            )}
            <AuthorityHandoffCards links={response?.related_links ?? []} />
            {view.kind !== "answer" && !analytical && response?.trace_id && <FeedbackControls traceId={response.trace_id} />}
          </div>
        </div>}

        {analytical && response?.trace_id && (
          <div className="analysis-feedback"><FeedbackControls traceId={response.trace_id} /></div>
        )}

        {requiresLocation && (
          <form className="location-request" onSubmit={submitLocation}>
            <span className="panel-label">Continue this task</span>
            <strong>{response?.required_input?.prompt}</strong>
            <p>FireLens sends only a community label or coordinates rounded to two decimals for this request.</p>
            <div className="location-request__actions">
              <input
                aria-label="BC community for this question"
                autoFocus
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
          </form>
        )}
        {locationMessage && <p className="location-message" role="status" aria-live="polite" aria-atomic="true">{locationMessage}</p>}

        {view.kind === "answer" && mode !== "background" && claims.length > 0 && (
          <ConversationEvidenceDetails
            allClaimsQuoteOnly={allClaimsQuoteOnly}
            claims={claims}
            onReviewEvidence={(index) => {
              setSelected(index);
              onOpenEvidence?.();
            }}
            response={view.response}
          />
        )}

        {view.kind === "abstention" && (
          <div className="abstention-card">
            <WarningCircle size={22} />
            <div>
              <strong>FireLens did not generate guidance</strong>
              <p>{abstentionPresentation(view.response.reason_code).title}</p>
              {visibleLimitations.map((item) => <p key={item}>{item}</p>)}
            </div>
          </div>
        )}

        {view.kind !== "idle" && <div className="answer-results-panel">
          {hasLiveResults && response && <LiveAnswerSummary
            response={response}
            onSelectResult={setSelectedLiveResultId}
            onOpenMap={onOpenMap}
            placeName={activeLocation?.label ?? locationLabel}
            radiusKm={activeLocation?.radius_km}
            selectedResultId={selectedLiveResultId}
          />}
          {selectedRecord && (
            <div className="selected-fire-chip" aria-label="Selected official record">
              <span>Selected: {resultDisplayName(selectedRecord)}</span>
              <button type="button" onClick={() => setSelectedLiveResultId(undefined)}>Clear selection</button>
            </div>
          )}
          <SuggestedQuestions
            disabled={view.kind === "loading"}
            onSelect={askSuggestedQuestion}
            suggestions={suggestions}
            mapAction={!analytical && (mode === "live" || mode === "mixed") && onOpenMap ? (
              <button type="button" aria-controls="answer-context" aria-expanded={contextOpen && contextSurface === "map"} onClick={onOpenMap}>
                <MapTrifold size={18} aria-hidden="true" /> Show these on the map
              </button>
            ) : undefined}
          />
        </div>}
      </div>

      {analytical && analysisSlot && (
        <div className="analysis-surface-slot">{analysisSlot}</div>
      )}
      {followUpComposer}
      {view.kind !== "idle" && <ConversationToolbar priorTurnCount={earlierTurns.length} onClear={clearHistory} />}
    </section>
  );
}
