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
import { FeedbackControls } from "../feedback/FeedbackControls";
import { resultDisplayName } from "../near-me/liveResultPresentation";
import { AnswerBody } from "./AnswerBody";
import { getAnswerSections } from "./answerSections";
import { getClaimSupportLabel, getClaimSupportState } from "./proofPresentation";
import type { Claim } from "./responseModel";
import { ResponseModeBadge } from "./responseModeBadge";
import type { FireLensSession } from "./useFireLensSession";

function revealAssistantMessage(node: HTMLElement | null, active: boolean) {
  if (!node || !active) return;
  node.scrollIntoView?.({ block: "start", inline: "nearest" });
  const scroller = node.closest(".conversation-scroll");
  if (!(scroller instanceof HTMLElement)) return;
  scroller.scrollTop += node.getBoundingClientRect().top - scroller.getBoundingClientRect().top;
}

function ClaimButton({
  claim,
  index,
  selected,
  supportLabel,
  onSelect,
}: {
  claim: Claim;
  index: number;
  selected: boolean;
  supportLabel: string;
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
      <small>{supportLabel}</small>
      <span className="claim-check">{selected && <Check size={15} weight="bold" />}</span>
    </button>
  );
}

function NonSelectableClaim({ claim, index, supportLabel }: { claim: Claim; index: number; supportLabel: string }) {
  return (
    <div className="claim-card claim-card--background">
      <span className="claim-number">{index + 1}</span>
      <span>{claim.text}</span>
      <small>{supportLabel}</small>
      <Info size={18} aria-hidden="true" />
    </div>
  );
}

export function ConversationPanel({ session }: { session: FireLensSession }) {
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
    selectedLiveResultId,
    setSelectedLiveResultId,
    mapResults,
  } = session;
  const answerSections = getAnswerSections(response);
  const visibleLimitations = Array.from(
    new Set((response?.limitations ?? []).map((item) => item.trim()).filter(Boolean)),
  );
  const selectedRecord = [...mapResults, ...(response?.live_results ?? [])].find(
    (item) => item.result_id === selectedLiveResultId,
  );

  return (
    <section className="conversation-panel" id="conversation" aria-label="Question and answer" tabIndex={-1}>
      <div className="conversation-toolbar">
        <span
          title="FireLens keeps your last 3 question-answer pairs in this browser only and re-sends them with your next question. Nothing is stored on a server."
        >
          <ChatsCircle size={16} /> {history.length} of 6 turns in context
        </span>
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

        <div className={`assistant-message assistant-message--${view.kind}`} ref={(node) => revealAssistantMessage(node, view.kind !== "idle")}>
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
              <AnswerBody
                response={response}
                assistantText={assistantText}
              />
            ) : (
              <p>{assistantText}</p>
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
                const selectable = [
                  "supported",
                  "structured_reviewed",
                  "official_live_typed",
                  "official_quote_only",
                  "source_linked_explanation",
                  "conflict",
                ].includes(state);
                return selectable ? (
                  <ClaimButton
                    key={claim.claim_id}
                    claim={claim}
                    index={index}
                    selected={selected === index}
                    supportLabel={supportLabel}
                    onSelect={() => setSelected(index)}
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
