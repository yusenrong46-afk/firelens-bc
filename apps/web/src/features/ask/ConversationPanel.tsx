import { ArrowSquareOut, Crosshair, UserCircle, WarningCircle } from "@phosphor-icons/react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { FeedbackControls } from "../feedback/FeedbackControls";
import { resultDisplayName } from "../near-me/liveResultPresentation";
import { AnswerBody } from "./AnswerBody";
import { AskStartPanel } from "./AskStartPanel";
import { getAnswerSections } from "./answerSections";
import {
  ClaimEvidence,
  ConversationToolbar,
  NonSelectableClaim,
  PreparednessSources,
  revealAssistantMessage,
  ServiceFailureState,
  SuggestedQuestions,
} from "./ConversationPresentation";
import { getClaimSupportLabel, getClaimSupportState } from "./proofPresentation";
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
  const evidenceById = new Map((response?.evidence ?? []).map((item) => [item.evidence_id, item]));
  const presentableEvidence = !response ? [] : (response.evidence ?? []).flatMap((item) => {
    const linkedClaim = claims.find((claim) => claim.supports?.some((support) => support.evidence_id === item.evidence_id));
    if (!linkedClaim) return [];
    const state = getClaimSupportState(response, linkedClaim);
    if (!["supported", "structured_reviewed", "official_quote_only", "source_linked_explanation", "conflict"].includes(state)) {
      return [];
    }
    return [{ item, state }];
  });
  const visibleLimitations = Array.from(
    new Set((response?.limitations ?? []).map((item) => item.trim()).filter(Boolean)),
  );
  const selectedRecord = [...mapResults, ...(response?.live_results ?? [])].find(
    (item) => item.result_id === selectedLiveResultId,
  );
  const previousState = useRef<ConversationState>(view.kind);
  const [announcement, setAnnouncement] = useState("");

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
              onLocationChange={(value) => { setLocationLabel(value); clearManualLocation(); }}
              onUseApproximateLocation={useApproximateLocation}
              onAsk={(question) => void submitQuestion(question)}
            />
            <QuestionComposer idle loading={false} query={query} onQueryChange={setQuery} onSubmit={submit} />
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
              <div className="related-service-links" aria-label="Related official services">
                {(response?.related_links ?? []).map((item) => (
                  <a key={item.url} href={item.url} target="_blank" rel="noreferrer">
                    <span><strong>{item.title}</strong><small>{item.description}</small></span>
                    <ArrowSquareOut size={18} aria-hidden="true" />
                  </a>
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
          <div className="claim-group">
            <span className="panel-label">Answer evidence and support</span>
            <div className="claim-list">
              {claims.map((claim, index) => {
                const state = getClaimSupportState(view.response, claim);
                const supportLabel = getClaimSupportLabel(view.response, claim);
                const showSource = [
                  "supported",
                  "structured_reviewed",
                  "official_quote_only",
                  "source_linked_explanation",
                  "conflict",
                ].includes(state);
                const hasLinkedEvidence = claim.supports?.some((support) => evidenceById.has(support.evidence_id)) ?? false;
                const canReview = showSource || hasLinkedEvidence || state === "official_live_typed";
                return canReview ? (
                  <ClaimEvidence
                    key={claim.claim_id}
                    claim={claim}
                    index={index}
                    supportLabel={supportLabel}
                    evidence={showSource && claim.supports?.[0] ? evidenceById.get(claim.supports[0].evidence_id) : undefined}
                    showSource={showSource}
                    onReviewEvidence={() => {
                      setSelected(index);
                      onOpenEvidence?.();
                    }}
                  />
                ) : (
                  <NonSelectableClaim
                    key={claim.claim_id}
                    claim={claim}
                    index={index}
                    supportLabel={supportLabel}
                  />
                );
              })}
            </div>
          </div>
        )}

        {view.kind === "answer" && <PreparednessSources evidence={presentableEvidence} />}

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

        {view.kind !== "idle" && (
          <SuggestedQuestions
            disabled={view.kind === "loading"}
            onSelect={(question) => void submitQuestion(question)}
            suggestions={suggestions}
          />
        )}
      </div>

      {analytical && analysisSlot && (
        <div className="analysis-surface-slot">{analysisSlot}</div>
      )}

      {view.kind !== "idle" && (
        <QuestionComposer continuationPending={requiresLocation} idle={false} loading={view.kind === "loading"} query={query}
          onQueryChange={setQuery} onSubmit={submit} />
      )}
    </section>
  );
}
