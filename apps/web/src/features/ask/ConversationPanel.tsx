import { ArrowSquareOut, Crosshair, Info, UserCircle, WarningCircle } from "@phosphor-icons/react";
import type { ReactNode } from "react";
import { FeedbackControls } from "../feedback/FeedbackControls";
import { resultDisplayName } from "../near-me/liveResultPresentation";
import { AnswerBody } from "./AnswerBody";
import { getAnswerSections } from "./answerSections";
import {
  ClaimEvidence,
  ConversationToolbar,
  NonSelectableClaim,
  PreparednessSources,
  revealAssistantMessage,
  ServiceFailureState,
} from "./ConversationPresentation";
import { getClaimSupportLabel, getClaimSupportState } from "./proofPresentation";
import { QuestionComposer } from "./QuestionComposer";
import { ResponseModeBadge } from "./responseModeBadge";
import type { FireLensSession } from "./useFireLensSession";

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
    history,
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
  const suggestionGroup = suggestions.length > 0 && (
    <div className="suggestion-group" aria-label="Suggested questions">
      <span className="panel-label">Start with an example</span>
      <div>
        {suggestions.map((suggestion) => (
          <button type="button" key={suggestion} onClick={() => void submitQuestion(suggestion)} disabled={view.kind === "loading"}>
            {suggestion}
          </button>
        ))}
      </div>
    </div>
  );

  return (
    <section className={`conversation-panel ${analytical ? "conversation-panel--analytical" : ""}`} id="conversation" aria-label="Question and answer" tabIndex={-1}>
      {(history.length > 0 || view.kind !== "idle") && (
        <ConversationToolbar priorTurnCount={earlierTurns.length} onClear={clearHistory} />
      )}
      <div className="conversation-scroll">
        {view.kind !== "idle" && (
          <span className="response-announcement" role="status" aria-live="polite" aria-atomic="true">
            {view.kind === "loading" ? "FireLens is working." : "FireLens response ready."}
          </span>
        )}
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
          <div className="conversation-intro">
            <span className="panel-label">British Columbia wildfire information</span>
            <h1>Ask about a fire, a B.C. place, or preparedness.</h1>
            <p>FireLens shows what came from official live records, reviewed sources, or clearly labelled general background.</p>
          </div>
        )}
        {view.kind === "idle" && (
          <QuestionComposer idle loading={false} query={query}
            onQueryChange={setQuery} onSubmit={submit} />
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
              <AnswerBody response={response} assistantText={assistantText} analytical={analytical} />
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
            {response?.trace_id && <FeedbackControls traceId={response.trace_id} />}
          </div>
        </div>}

        {analytical && visibleLimitations.length > 0 && (
          <aside className="analysis-limitations" aria-label="Analysis limitations">
            <Info size={18} aria-hidden="true" />
            <span>{visibleLimitations.join(" ")}</span>
          </aside>
        )}
        {analytical && analysisSlot}
        {analytical && response?.trace_id && onOpenEvidence && (
          <div className="answer-context-actions analysis-context-actions">
            <button
              type="button"
              aria-controls="answer-context"
              aria-expanded={contextOpen && contextSurface === "evidence"}
              onClick={() => {
                setSelected(0);
                onOpenEvidence();
              }}
            >
              Open technical evidence
            </button>
          </div>
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
        {locationMessage && <p className="location-message" role="status">{locationMessage}</p>}

        {view.kind === "answer" && claims.length > 0 && (
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

        {suggestionGroup}
      </div>

      {view.kind !== "idle" && (
        <QuestionComposer continuationPending={requiresLocation} idle={false} loading={view.kind === "loading"} query={query}
          onQueryChange={setQuery} onSubmit={submit} />
      )}
    </section>
  );
}
