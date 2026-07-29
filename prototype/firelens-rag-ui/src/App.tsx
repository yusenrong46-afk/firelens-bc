import { FormEvent, lazy, ReactNode, Suspense, useMemo, useRef, useState } from "react";
import {
  ArrowSquareOut,
  CaretDown,
  CaretUp,
  Check,
  ChatsCircle,
  Info,
  PaperPlaneTilt,
  Crosshair,
  Shield,
  Trash,
  UserCircle,
  WarningCircle,
} from "@phosphor-icons/react";
import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource/newsreader/500.css";
import "@fontsource/newsreader/600.css";
import {
  askFireLens,
  AskResponse,
  ConversationTurn,
  FireLensApiError,
  LocationInput,
  ResponseMode,
} from "./api";
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
type Support = NonNullable<Claim["supports"]>[number];
const LiveMap = lazy(() => import("./LiveMap").then((module) => ({ default: module.LiveMap })));

const INITIAL_SUGGESTIONS = [
  "What belongs in a grab-and-go bag?",
  "What is the difference between an evacuation alert and order?",
  "How can I reduce wildfire risk around my home?",
  "What should I know about wildfire smoke?",
  "What do wildfire stages of control mean?",
  "How do structure-protection sprinklers work?",
];

function getResponseMode(response: AskResponse): ResponseMode {
  if (response.response_mode) return response.response_mode;
  if (response.status === "abstention") return "abstention";
  if ((response.claims ?? []).some((claim) => (claim.supports ?? []).length > 0)) {
    return "grounded";
  }
  return "background";
}

function responseText(response: AskResponse): string {
  if (response.answer) return response.answer;
  const mode = getResponseMode(response);
  if (mode === "capability") return "I can help you explore the reviewed FireLens guidance.";
  if (mode === "scope_redirect") return "That request is outside the FireLens guidance collection.";
  return "FireLens could not produce an answer for this request.";
}

function ResponseModeBadge({ mode }: { mode: ResponseMode }) {
  const labels: Record<ResponseMode, string> = {
    grounded: "Reviewed sources",
    partial: "Partially supported",
    background: "General background",
    capability: "FireLens topics",
    scope_redirect: "Outside FireLens scope",
    abstention: "Official current information required",
    live: "Official live records",
    mixed: "Live records + reviewed guidance",
  };
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
            </dl>
            <div className="canonical">
              <strong>Canonical source</strong>
              <a href={evidence.canonical_url} target="_blank" rel="noreferrer">
                Open official page <ArrowSquareOut size={13} />
              </a>
            </div>
          </aside>
          <div className="passage">
            <h2>Source passage</h2>
            <HighlightedPassage text={evidence.context_text} quote={support.quote} />
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
  const [history, setHistory] = useState<ConversationTurn[]>([]);
  const [locationLabel, setLocationLabel] = useState("");
  const [coarseLocation, setCoarseLocation] = useState<LocationInput | undefined>();
  const [locationMessage, setLocationMessage] = useState("");
  const activeRequest = useRef<AbortController | null>(null);

  const answer = view.kind === "answer" ? view.response : undefined;
  const response = view.kind === "answer" || view.kind === "abstention" ? view.response : undefined;
  const mode = response ? getResponseMode(response) : undefined;
  const claims = answer?.claims ?? [];
  const citedMode = mode === "grounded" || mode === "partial" || mode === "mixed";
  const selectedClaim = citedMode ? claims[selected] : undefined;
  const evidenceById = useMemo(
    () => new Map((answer?.evidence ?? []).map((item) => [item.evidence_id, item])),
    [answer],
  );
  const supportedEvidence = (selectedClaim?.supports ?? [])
    .map((support) => ({ support, evidence: evidenceById.get(support.evidence_id) }))
    .filter((item): item is { support: Support; evidence: Evidence } => Boolean(item.evidence));

  const currentPairIsStored =
    (view.kind === "answer" || view.kind === "abstention") &&
    history.length >= 2 &&
    history.at(-2)?.role === "user" &&
    history.at(-2)?.content === view.question;
  const earlierTurns = currentPairIsStored ? history.slice(0, -2) : history;
  const suggestions = response?.suggested_questions?.length
    ? response.suggested_questions.slice(0, 6)
    : view.kind === "idle"
      ? INITIAL_SUGGESTIONS
      : [];

  async function submitQuestion(question: string) {
    const normalized = question.trim();
    if (!normalized) return;
    const requestHistory = history.slice(-6);
    activeRequest.current?.abort();
    const controller = new AbortController();
    activeRequest.current = controller;
    setLastQuestion(normalized);
    setSelected(0);
    setView({ kind: "loading", question: normalized });
    try {
      const requestLocation = locationLabel.trim()
        ? { label: locationLabel.trim(), radius_km: 50 }
        : coarseLocation;
      const nextResponse = await askFireLens(
        normalized,
        requestHistory,
        requestLocation,
        controller.signal,
      );
      const nextHistory: ConversationTurn[] = [
        ...requestHistory,
        { role: "user", content: normalized },
        { role: "assistant", content: responseText(nextResponse) },
      ];
      setHistory(nextHistory.slice(-6));
      if (nextResponse.status === "answer") {
        setView({ kind: "answer", question: normalized, response: nextResponse });
      } else {
        setView({ kind: "abstention", question: normalized, response: nextResponse });
      }
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return;
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
    } finally {
      if (activeRequest.current === controller) activeRequest.current = null;
    }
  }

  function clearHistory() {
    activeRequest.current?.abort();
    activeRequest.current = null;
    setHistory([]);
    setLastQuestion("");
    setSelected(0);
    setLocationLabel("");
    setCoarseLocation(undefined);
    setLocationMessage("");
    setView({ kind: "idle" });
  }

  function useApproximateLocation() {
    if (!navigator.geolocation) {
      setLocationMessage("Location is not available in this browser.");
      return;
    }
    setLocationMessage("Requesting permission…");
    navigator.geolocation.getCurrentPosition(
      ({ coords }) => {
        setLocationLabel("");
        setCoarseLocation({
          latitude: Math.round(coords.latitude * 100) / 100,
          longitude: Math.round(coords.longitude * 100) / 100,
          radius_km: 50,
        });
        setLocationMessage("Approximate location ready for this session.");
      },
      () => setLocationMessage("Location was not shared."),
      { enableHighAccuracy: false, maximumAge: 300_000, timeout: 8_000 },
    );
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
      ? responseText(view.response)
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
          <span><strong>FireLens</strong> BC <small>V1.5 RC</small></span>
        </a>
        <a className="official-link" href="https://wildfiresituation.nrs.gov.bc.ca/map" target="_blank" rel="noreferrer">
          <ArrowSquareOut size={18} /> Official BCWS map
        </a>
      </header>
      <div className="boundary">
        <Shield size={17} />
        <span>Reviewed preparedness guidance and official live records — not emergency direction.</span>
      </div>

      <main className="workspace">
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
                {mode && <ResponseModeBadge mode={mode} />}
                <p>{assistantText}</p>
                {(view.kind === "unavailable" || (view.kind === "error" && view.retryable)) && (
                  <button className="retry-button" type="button" onClick={() => void submitQuestion(lastQuestion)}>
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
                      <ClaimButton
                        key={claim.claim_id}
                        claim={claim}
                        index={index}
                        selected={selected === index}
                        onSelect={() => setSelected(index)}
                      />
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
                    <button
                      type="button"
                      key={suggestion}
                      onClick={() => void submitQuestion(suggestion)}
                      disabled={view.kind === "loading"}
                    >
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
                  setCoarseLocation(undefined);
                  setLocationMessage("");
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

        <section className="evidence-panel" aria-label="Selected claim evidence">
          <div className="evidence-inner">
            {view.kind === "answer" && (mode === "live" || mode === "mixed") && (view.response.live_results ?? []).length > 0 ? (
              <Suspense fallback={<EvidencePlaceholder icon={<span className="spinner" />} title="Loading the official map">Preparing map layers…</EvidencePlaceholder>}>
                <LiveMap
                  results={view.response.live_results ?? []}
                  unavailableLayers={view.response.unavailable_layers ?? []}
                />
                {mode === "mixed" && (view.response.evidence ?? []).length > 0 && (
                  <div className="mixed-sources">
                    <strong>Preparedness sources</strong>
                    {(view.response.evidence ?? []).map((item) => (
                      <a key={item.evidence_id} href={item.canonical_url} target="_blank" rel="noreferrer">{item.title}</a>
                    ))}
                  </div>
                )}
              </Suspense>
            ) : view.kind === "answer" && citedMode && selectedClaim ? (
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
            ) : view.kind === "answer" && mode === "background" ? (
              <EvidencePlaceholder icon={<Info size={34} />} title="General background — no corpus evidence attached">
                This explanation is related to wildfire preparedness, but its claims were not verified against the reviewed FireLens collection. Background claims cannot open an evidence panel.
              </EvidencePlaceholder>
            ) : view.kind === "answer" && mode === "capability" ? (
              <EvidencePlaceholder icon={<ChatsCircle size={36} />} title="Explore the FireLens collection">
                Choose a suggested question or ask in your own words. FireLens can discuss reviewed preparedness guidance and clearly labels when an answer uses general background.
              </EvidencePlaceholder>
            ) : view.kind === "answer" && mode === "scope_redirect" ? (
              <EvidencePlaceholder icon={<Info size={34} />} title="Outside the FireLens collection">
                FireLens keeps the conversation open for wildfire and preparedness topics. Completely unrelated requests receive a short redirect and suggested ways back into the collection.
              </EvidencePlaceholder>
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
              <EvidencePlaceholder icon={<Shield size={36} />} title="Ask, then inspect the source">
                FireLens answers from reviewed guidance, or shows current official wildfire records when a live question requires them.
              </EvidencePlaceholder>
            )}
          </div>
        </section>
      </main>
    </div>
  );
}
