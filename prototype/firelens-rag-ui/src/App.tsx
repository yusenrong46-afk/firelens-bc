import { FormEvent, ReactNode, useMemo, useState } from "react";
import {
  ArrowSquareOut,
  CaretDown,
  CaretUp,
  Check,
  Info,
  PaperPlaneTilt,
  Shield,
  UserCircle,
  WarningCircle,
} from "@phosphor-icons/react";
import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource/newsreader/500.css";
import "@fontsource/newsreader/600.css";
import { askFireLens, AskResponse, FireLensApiError } from "./api";
import "./styles.css";

type AnswerView = { kind: "answer"; question: string; response: AskResponse };
type AbstentionView = { kind: "abstention"; question: string; response: AskResponse };
type MessageView = {
  kind: "idle" | "loading" | "unavailable" | "error";
  question?: string;
  message?: string;
  retryable?: boolean;
};
type ViewState = AnswerView | AbstentionView | MessageView;

type Claim = NonNullable<AskResponse["claims"]>[number];
type Evidence = NonNullable<AskResponse["evidence"]>[number];
type Support = Claim["supports"][number];

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

function HighlightedPassage({ text, quote }: { text: string; quote: string }) {
  const start = text.indexOf(quote);
  if (start < 0) return <p>{text}</p>;
  return (
    <p>
      {text.slice(0, start)}
      <mark>{quote}</mark>
      {text.slice(start + quote.length)}
    </p>
  );
}

function SourcePanel({
  evidence,
  support,
  index,
  initiallyOpen,
}: {
  evidence: Evidence;
  support: Support;
  index: number;
  initiallyOpen: boolean;
}) {
  const [open, setOpen] = useState(initiallyOpen);
  return (
    <article className="source-panel">
      <div className="source-panel__head">
        <button
          type="button"
          className="source-toggle"
          onClick={() => setOpen(!open)}
          aria-expanded={open}
        >
          <span className="source-number">{index + 1}</span>
          <span className="source-name">
            <strong>{evidence.title}</strong>
            <small>{evidence.locator || "Reviewed source passage"}</small>
          </span>
        </button>
        <span className="stable-chip">Stable guidance</span>
        <a href={evidence.canonical_url} target="_blank" rel="noreferrer">
          View source <ArrowSquareOut size={15} />
        </a>
        <button
          type="button"
          className="caret-button"
          onClick={() => setOpen(!open)}
          aria-label={open ? `Collapse source ${index + 1}` : `Expand source ${index + 1}`}
        >
          {open ? <CaretUp /> : <CaretDown />}
        </button>
      </div>
      {open && (
        <div className="source-panel__body">
          <aside className="source-details">
            <dl>
              <div><dt>Publisher</dt><dd>{evidence.publisher}</dd></div>
              <div><dt>Document</dt><dd>{evidence.title}</dd></div>
              <div><dt>Locator</dt><dd>{evidence.locator || "Source passage"}</dd></div>
              <div><dt>Guidance type</dt><dd>Stable preparedness guidance</dd></div>
              <div><dt>Evidence ID</dt><dd>{evidence.evidence_id}</dd></div>
            </dl>
            <div className="canonical">
              <strong>Canonical source</strong>
              <a href={evidence.canonical_url} target="_blank" rel="noreferrer">
                Open official page <ArrowSquareOut size={13} />
              </a>
            </div>
          </aside>
          <div className="passage">
            <h2>Retrieved passage</h2>
            <HighlightedPassage text={evidence.context_text} quote={support.quote} />
            <div className="support-box">
              <span className="support-icon"><Shield size={20} weight="duotone" /></span>
              <div>
                <h3>Traceability check passed</h3>
                <p>
                  The highlighted quotation is an exact substring of the local primary
                  passage. Semantic support is evaluated separately in the reviewed benchmark.
                </p>
              </div>
            </div>
          </div>
        </div>
      )}
    </article>
  );
}

function EvidencePlaceholder({ icon, title, children }: { icon: ReactNode; title: string; children: ReactNode }) {
  return (
    <div className="evidence-placeholder">
      <span>{icon}</span>
      <h1>{title}</h1>
      <p>{children}</p>
    </div>
  );
}

export function App() {
  const [query, setQuery] = useState("");
  const [lastQuestion, setLastQuestion] = useState("");
  const [selected, setSelected] = useState(0);
  const [view, setView] = useState<ViewState>({ kind: "idle" });

  const answer = view.kind === "answer" ? view.response : undefined;
  const claims = answer?.claims ?? [];
  const selectedClaim = claims[selected];
  const evidenceById = useMemo(
    () => new Map((answer?.evidence ?? []).map((item) => [item.evidence_id, item])),
    [answer],
  );
  const supportedEvidence = (selectedClaim?.supports ?? [])
    .map((support) => ({ support, evidence: evidenceById.get(support.evidence_id) }))
    .filter((item): item is { support: Support; evidence: Evidence } => Boolean(item.evidence));

  async function submitQuestion(question: string) {
    const normalized = question.trim();
    if (!normalized) return;
    setLastQuestion(normalized);
    setSelected(0);
    setView({ kind: "loading", question: normalized });
    try {
      const response = await askFireLens(normalized);
      if (response.status === "answer") {
        setView({ kind: "answer", question: normalized, response });
      } else {
        setView({ kind: "abstention", question: normalized, response });
      }
    } catch (error) {
      if (error instanceof FireLensApiError) {
        setView({
          kind: error.detail.retryable ? "unavailable" : "error",
          question: normalized,
          message: error.detail.message,
          retryable: error.detail.retryable,
        });
      } else {
        setView({
          kind: "error",
          question: normalized,
          message: "FireLens could not read the local service response.",
        });
      }
    }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const question = query;
    setQuery("");
    void submitQuestion(question);
  }

  const visibleQuestion = "question" in view && view.question ? view.question : undefined;
  const assistantText =
    view.kind === "answer" || view.kind === "abstention"
      ? view.response.answer
      : view.kind === "loading"
        ? "Searching the reviewed guidance and validating its evidence…"
        : view.kind === "unavailable" || view.kind === "error"
          ? view.message
          : "Ask about stable BC wildfire preparedness guidance. FireLens will either return locally cited evidence or explain why it cannot answer.";

  return (
    <div className="app-shell" id="top">
      <header className="topbar">
        <a className="brand" href="#top">
          <img src="/assets/firelens-mark.png" alt="" />
          <span><strong>FireLens</strong> BC</span>
        </a>
        <a className="official-link" href="https://www.emergencyinfobc.gov.bc.ca/" target="_blank" rel="noreferrer">
          <ArrowSquareOut size={18} /> Official current information
        </a>
      </header>
      <div className="boundary">
        <Shield size={17} />
        <span>Official preparedness guidance — not current incident or evacuation status.</span>
      </div>

      <main className="workspace">
        <section className="conversation-panel" aria-label="Question and answer">
          <div className="conversation-scroll" aria-live="polite">
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
                <p>{assistantText}</p>
                {(view.kind === "unavailable" || (view.kind === "error" && view.retryable)) && (
                  <button className="retry-button" type="button" onClick={() => void submitQuestion(lastQuestion)}>
                    Retry this question
                  </button>
                )}
                {view.kind === "answer" && <small>Trace: {view.response.trace_id}</small>}
              </div>
            </div>

            {view.kind === "answer" && (
              <div className="claim-group">
                <span className="panel-label">Cited claims in this answer</span>
                <div className="claim-list">
                  {claims.map((claim, index) => (
                    <ClaimButton
                      key={claim.claim_id}
                      claim={claim}
                      index={index}
                      selected={selected === index}
                      onSelect={() => setSelected(index)}
                    />
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
            <p><Info size={16} /> For property-specific risk assessments or current fire conditions, consult the appropriate official service.</p>
          </form>
        </section>

        <section className="evidence-panel" aria-label="Selected claim evidence">
          <div className="evidence-inner">
            {view.kind === "answer" && selectedClaim ? (
              <>
                <span className="selected-kicker">Selected claim {selected + 1}</span>
                <h1>{selectedClaim.text}</h1>
                <div className="answer-claim">
                  <Shield size={18} /><strong>Answer claim</strong><span>{selectedClaim.text}</span>
                </div>
                {supportedEvidence.map(({ evidence, support }, index) => (
                  <SourcePanel
                    key={`${evidence.evidence_id}:${support.quote}`}
                    evidence={evidence}
                    support={support}
                    index={index}
                    initiallyOpen={index === 0}
                  />
                ))}
                <div className="access-date"><Shield size={17} weight="fill" /> Sources come from the reviewed local corpus.</div>
              </>
            ) : view.kind === "loading" ? (
              <EvidencePlaceholder icon={<span className="spinner" />} title="Building an evidence packet">
                FireLens is retrieving, reranking, and validating local passages. No answer appears until every structural check passes.
              </EvidencePlaceholder>
            ) : view.kind === "abstention" ? (
              <EvidencePlaceholder icon={<WarningCircle size={34} />} title="No evidence-backed answer">
                The request crossed a product boundary or the approved corpus could not support an answer. Use the official-current-information link for live conditions.
              </EvidencePlaceholder>
            ) : view.kind === "unavailable" || view.kind === "error" ? (
              <EvidencePlaceholder icon={<WarningCircle size={34} />} title="Local service unavailable">
                The failure was returned explicitly. FireLens did not substitute another model or answer from memory.
              </EvidencePlaceholder>
            ) : (
              <EvidencePlaceholder icon={<Shield size={36} />} title="Inspect every cited claim">
                Submit a stable preparedness question. An accepted answer will expose its exact quotations, local evidence IDs, publishers, and canonical source links here.
              </EvidencePlaceholder>
            )}
          </div>
        </section>
      </main>
    </div>
  );
}
