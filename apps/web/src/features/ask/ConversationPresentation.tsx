import { ArrowSquareOut, ChatsCircle, Info, Trash, WarningCircle } from "@phosphor-icons/react";
import type { SupportState } from "./proofPresentation";
import type { Claim, Evidence } from "./responseModel";

const OFFICIAL_BCWS_MAP_URL = "https://wildfiresituation.nrs.gov.bc.ca/map";

export function revealAssistantMessage(node: HTMLElement | null, active: boolean) {
  if (!node || !active) return;
  const scroller = node.closest(".conversation-scroll");
  if (!(scroller instanceof HTMLElement)) return;

  // The analytical workspace is a two-column grid inside this scroller. The
  // normal chat behavior intentionally follows the newest assistant message,
  // but doing that here moves both the answer rail and the analysis canvas so
  // their question/KPI content starts below the first viewport. A new
  // analytical answer already has its own Summary default, so keep its shared
  // scroller at the top and let ordinary conversations retain auto-follow.
  if (node.closest(".conversation-panel--analytical")) {
    scroller.scrollTop = 0;
    return;
  }

  const previous = node.previousElementSibling;
  const target = previous instanceof HTMLElement && previous.classList.contains("question-block")
    ? previous
    : node;
  target.scrollIntoView?.({ block: "start", inline: "nearest" });
  scroller.scrollTop += target.getBoundingClientRect().top - scroller.getBoundingClientRect().top;
}

export function conversationContextLabel(priorTurnCount: number): string {
  return `${priorTurnCount} of 6 prior turns in context`;
}

export function ConversationToolbar({
  onClear,
  priorTurnCount,
}: {
  onClear: () => void;
  priorTurnCount: number;
}) {
  return (
    <div className={`conversation-toolbar ${priorTurnCount === 0 ? "conversation-toolbar--clear-only" : ""}`}>
      {priorTurnCount > 0 && (
        <span
          title="FireLens keeps your last 3 question-answer pairs in this browser only and re-sends them with your next question. Nothing is stored on a server."
        >
          <ChatsCircle size={16} aria-hidden="true" /> {conversationContextLabel(priorTurnCount)}
        </span>
      )}
      <button type="button" onClick={onClear} aria-label="Clear conversation history">
        <Trash size={15} aria-hidden="true" /> {priorTurnCount === 0 ? "New conversation" : "Clear"}
      </button>
    </div>
  );
}

export function SuggestedQuestions({
  disabled,
  onSelect,
  suggestions,
}: {
  disabled: boolean;
  onSelect: (question: string) => void;
  suggestions: string[];
}) {
  if (suggestions.length === 0) return null;
  return (
    <div className="suggestion-group" aria-label="Suggested questions">
      <span className="panel-label">Start with an example</span>
      <div>
        {suggestions.map((suggestion) => (
          <button type="button" key={suggestion} onClick={() => onSelect(suggestion)} disabled={disabled}>
            {suggestion}
          </button>
        ))}
      </div>
    </div>
  );
}

export function ServiceFailureState({
  message,
  onRetry,
  retryable,
}: {
  message: string;
  onRetry: () => void;
  retryable: boolean;
}) {
  return (
    <div
      className="service-failure"
      role={retryable ? "status" : "alert"}
      aria-labelledby="service-failure-heading"
    >
      <WarningCircle size={22} aria-hidden="true" />
      <div>
        <strong id="service-failure-heading">We couldn't complete this question</strong>
        <p>{message}</p>
        <p>No wildfire status was shown or inferred.</p>
        <div className="service-failure__actions">
          {retryable && (
            <button className="retry-button" type="button" onClick={onRetry}>
              Retry this question
            </button>
          )}
          <a href={OFFICIAL_BCWS_MAP_URL} target="_blank" rel="noreferrer">
            Official BC Wildfire Service map
            <ArrowSquareOut size={18} aria-hidden="true" />
          </a>
        </div>
      </div>
    </div>
  );
}

export function ClaimEvidence({
  claim,
  index,
  supportLabel,
  evidence,
  showSource,
  onReviewEvidence,
}: {
  claim: Claim;
  index: number;
  supportLabel: string;
  evidence?: Evidence | undefined;
  showSource: boolean;
  onReviewEvidence: () => void;
}) {
  const quote = showSource ? claim.supports?.[0]?.quote?.trim() : undefined;
  const reviewLabel = claim.publication?.kind === "official_quote_only"
    ? "Source extraction only; no structured-claim review"
    : evidence?.review_provenance === "human_verified_repair"
      ? "Human-verified source transcription"
      : evidence?.review_provenance?.replaceAll("_", " ");
  return (
    <article
      className="claim-evidence"
      aria-label={`Supported claim ${index + 1}: ${supportLabel}`}
    >
      <div className="claim-evidence__statement">
        <span className="claim-number">{index + 1}</span>
        <div><strong>{claim.text}</strong><small>{supportLabel}</small></div>
      </div>
      {quote && (
        <blockquote>
          <span>Exact source wording</span>
          <p><mark>{quote}</mark></p>
          {evidence && (
            <small>{evidence.publisher} · {evidence.title}{reviewLabel ? ` · ${reviewLabel}` : ""}</small>
          )}
        </blockquote>
      )}
      <button type="button" aria-label={`Review technical evidence for ${claim.text}`} onClick={onReviewEvidence}>Review technical evidence</button>
    </article>
  );
}

export function NonSelectableClaim({ claim, index, supportLabel }: { claim: Claim; index: number; supportLabel: string }) {
  return (
    <div className="claim-card claim-card--background">
      <span className="claim-number">{index + 1}</span>
      <span>{claim.text}</span>
      <small>{supportLabel}</small>
      <p>This is labelled general background and has no reviewed source support attached.</p>
      <Info size={18} aria-hidden="true" />
    </div>
  );
}

function reviewProvenanceLabel(value: string | null | undefined): string | undefined {
  if (!value) return undefined;
  return value === "human_verified_repair"
    ? "Human-verified source transcription"
    : value.replaceAll("_", " ");
}

export function PreparednessSources({
  evidence,
}: {
  evidence: Array<{ item: Evidence; state: SupportState }>;
}) {
  if (evidence.length === 0) return null;
  return (
    <section className="answer-sources" aria-label="Preparedness sources">
      <span className="panel-label">Preparedness sources</span>
      <ul>
        {evidence.map(({ item, state }) => (
          <li key={item.evidence_id}>
            <div>
              <strong>{item.publisher}</strong>
              <a href={item.canonical_url} target="_blank" rel="noreferrer">{item.title}</a>
            </div>
            {(state === "official_quote_only" || reviewProvenanceLabel(item.review_provenance)) && (
              <small>{state === "official_quote_only"
                ? "Source extraction only; no structured-claim review"
                : reviewProvenanceLabel(item.review_provenance)}</small>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
