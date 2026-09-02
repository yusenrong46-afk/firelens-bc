import { ArrowSquareOut, Crosshair, UserCircle, WarningCircle } from "@phosphor-icons/react";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { FeedbackControls } from "../feedback/FeedbackControls";
import { emitProductEvent } from "../../shared/telemetry";
import { resultDisplayName } from "../near-me/liveResultPresentation";
import { AnswerBody } from "./AnswerBody";
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

export function ConversationPanel({ session, analytical = false, analysisSlot, onOpenEvidence, onOpenMap,
  contextOpen = false, contextSurface = "evidence" }: {
  session: FireLensSession;
  analytical?: boolean;
  analysisSlot?: ReactNode;
  onOpenEvidence?: () => void;
  onOpenMap?: () => void;
  contextOpen?: boolean;
  contextSurface?: "evidence" | "map";
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
              onLocationChange={(value) => { setLocationLabel(value); clearManualLocation(); }}
              onUseApproximateLocation={useApproximateLocation}
              onSelectQuestion={fillComposer}
            />
            <QuestionComposer idle loading={false} query={query} onQueryChange={setQuery} onSubmit={submit} inputRef={composerRef} />
          </>
        )}

        {view.kind !== "idle" && <div className={`assistant-message assistant-message--${view.kind}`} ref={(node) => revealAssistantMessage(node, true)}>
          <img src="/assets/firelens-mark.png" alt="" />
          <div>
            <span className="assistant-name">FireLens BC</span>
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
              <AnswerBody response={response} assistantText={assistantText} analytical={analytical} onSelectLiveResult={setSelectedLiveResultId} />
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
                <button type="button" aria-controls="answer-context" aria-expanded={contextOpen && contextSurface === "map"} onClick={onOpenMap}>View official map context</button>
              </div>
            )}
            {(response?.related_links ?? []).length > 0 && (
              <div className="related-service-links authority-handoff-cards" aria-label="Official authority handoffs">
                {(response?.related_links ?? []).map((item) => (
                  <article key={item.url} className="authority-handoff-card">
                    <p className="authority-handoff-card__topic">{item.title}</p>
                    <p className="authority-handoff-card__authority">{handoffAuthority(item.title)}</p>
                    <p>{item.description}</p>
                    <p className="authority-handoff-card__why">FireLens does not ingest this live source, so it hands off to the official owner.</p>
                    <a href={item.url} target="_blank" rel="noreferrer" onClick={() => emitProductEvent("authority_handoff_opened")}>
                      <span>Open official source</span>
                      <ArrowSquareOut size={18} aria-hidden="true" />
                    </a>
                  </article>
                ))}
              </div>
            )}
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

      {view.kind !== "idle" && (
        <QuestionComposer continuationPending={requiresLocation} idle={false} loading={view.kind === "loading"} query={query}
          onQueryChange={setQuery} onSubmit={submit} inputRef={composerRef} />
      )}
    </section>
  );
}

function handoffAuthority(title: string): string {
  const lowered = title.toLocaleLowerCase();
  if (lowered.includes("drivebc")) return "DriveBC";
  if (lowered.includes("aqhi") || lowered.includes("air quality")) return "Environment and Climate Change Canada";
  if (lowered.includes("emergencyinfo")) return "EmergencyInfoBC";
  if (lowered.includes("bc wildfire") || lowered.includes("bcws")) return "BC Wildfire Service";
  return "Official authority";
}
