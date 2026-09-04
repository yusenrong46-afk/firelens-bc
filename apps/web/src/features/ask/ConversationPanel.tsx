import { Crosshair, UserCircle, WarningCircle } from "@phosphor-icons/react";
import { useCallback, useEffect, useRef, useState, type ReactNode, type RefObject } from "react";
import { FeedbackControls } from "../feedback/FeedbackControls";
import { resultDisplayName } from "../near-me/liveResultPresentation";
import { AnswerBody } from "./AnswerBody";
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
import { QuestionComposer } from "./QuestionComposer";
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
  composerFocusRef?: RefObject<HTMLInputElement | null>;
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
    query,
    response,
    requiresLocation,
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
    selectedLiveResultId,
    setSelectedLiveResultId,
    mapResults,
    activeLocation,
  } = session;
  const answerSections = getAnswerSections(response);
  const visibleLimitations = Array.from(
    new Set((response?.limitations ?? []).map((item) => item.trim()).filter(Boolean)),
  );
  const allClaimsQuoteOnly = claims.length > 0
    && claims.every((claim) => claim.publication?.kind === "official_quote_only");
  const selectedRecord = [...mapResults, ...(response?.live_results ?? [])].find(
    (item) => item.result_id === selectedLiveResultId,
  );
  const previousState = useRef<ConversationState>(view.kind);
  const composerRef = useRef<HTMLInputElement>(null);
  const [announcement, setAnnouncement] = useState("");
  const [selectionAnnouncement, setSelectionAnnouncement] = useState("");

  const fillComposer = useCallback((question: string) => {
    const place = locationLabel.trim();
    const normalized = (place ? question.replaceAll("{place}", place) : question).trim();
    if (!normalized) return;
    setQuery(normalized);
    setSelectionAnnouncement(`Question added to the composer: ${normalized}`);
    requestAnimationFrame(() => composerRef.current?.focus());
  }, [locationLabel, setQuery]);

  useEffect(() => {
    const priorState = previousState.current;
    if (priorState === view.kind) return;
    previousState.current = view.kind;
    setAnnouncement(announcementForState(view.kind, priorState));
  }, [view.kind]);

  const followUpComposer = view.kind !== "idle" ? (
    <div className="pc-composer-stack pc-composer-stack--follow-up">
      {contextChips}
      <QuestionComposer
        continuationPending={requiresLocation}
        idle={false}
        loading={view.kind === "loading"}
        query={query}
        onQueryChange={setQuery}
        onSubmit={submit}
        inputRef={composerRef}
      />
    </div>
  ) : null;

  return (
    <section className={`conversation-panel ${analytical ? "conversation-panel--analytical" : ""} ${view.kind === "idle" ? "conversation-panel--idle" : ""}`} id="conversation" aria-label="Question and answer" tabIndex={-1}>
      {view.kind !== "idle" && (
        <ConversationToolbar priorTurnCount={earlierTurns.length} onClear={clearHistory} />
      )}
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

        {view.kind === "idle" && (
          <>
            <AskStartPanel
              locationLabel={locationLabel}
              currentState={liveSummary ? assistantText : undefined}
              composer={(
                <div className="pc-composer-stack">
                  <QuestionComposer idle loading={false} query={query} onQueryChange={setQuery} onSubmit={submit} inputRef={composerRef} />
                  {contextChips}
                </div>
              )}
              onLocationChange={(value) => { setLocationLabel(value); clearManualLocation(); }}
              onUseApproximateLocation={useApproximateLocation}
              onSelectQuestion={fillComposer}
            />
          </>
        )}

        {view.kind !== "idle" && <div className={`assistant-message assistant-message--${view.kind}`} ref={(node) => revealAssistantMessage(node, true)}>
          <img src="/assets/firelens-mark.png" alt="" />
          <div>
            <span className="assistant-name">FireLens</span>
            {mode && (
              <ResponseModeBadge
                mode={mode}
                aggregateFreshness={response?.aggregate_freshness ?? undefined}
                answerSectionKinds={answerSections.map((section) => section.kind)}
                reasonCode={response?.reason_code ?? undefined}
                response={response}
              />
            )}
            {selectedRecord && (
              <div className="selected-fire-chip" aria-label="Selected official record">
                <span>Selected: {resultDisplayName(selectedRecord)}</span>
                <button type="button" onClick={() => setSelectedLiveResultId(undefined)}>
                  Clear selection
                </button>
              </div>
            )}
            {view.kind === "answer" ? (
              <AnswerBody
                response={response}
                assistantText={assistantText}
                analytical={analytical}
                onSelectLiveResult={setSelectedLiveResultId}
                onOpenMap={onOpenMap}
                placeName={activeLocation?.label ?? locationLabel}
                radiusKm={activeLocation?.radius_km}
                selectedLiveResultId={selectedLiveResultId}
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
            {!analytical && (mode === "live" || mode === "mixed") && onOpenMap && (
              <div className="answer-context-actions">
                <button
                  type="button"
                  aria-controls="answer-context"
                  aria-expanded={contextOpen && contextSurface === "map"}
                  onClick={onOpenMap}
                >
                  Show these on the map
                </button>
              </div>
            )}
            <AuthorityHandoffCards links={response?.related_links ?? []} />
            {!analytical && response?.trace_id && <FeedbackControls traceId={response.trace_id} />}
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

        {view.kind !== "idle" && (
          <SuggestedQuestions
            disabled={view.kind === "loading"}
            onSelect={fillComposer}
            suggestions={suggestions}
          />
        )}
      </div>

      {analytical && analysisSlot && (
        <div className="analysis-surface-slot">{analysisSlot}</div>
      )}
      {followUpComposer}
    </section>
  );
}
