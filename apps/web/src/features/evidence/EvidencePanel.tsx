import { lazy, type ReactNode, Suspense, useMemo, useState } from "react";
import {
  ArrowSquareOut,
  CaretDown,
  CaretUp,
  ChatsCircle,
  Info,
  Shield,
  WarningCircle,
} from "@phosphor-icons/react";
import type { Evidence, Support } from "../ask/responseModel";
import type { FireLensSession } from "../ask/useFireLensSession";

const LiveMap = lazy(() => import("../near-me/LiveMap").then((module) => ({ default: module.LiveMap })));

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
        <button type="button" className="source-toggle" onClick={() => setOpen(!open)} aria-expanded={open}>
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
              {evidence.review_provenance === "human_verified_repair" && (
                <div><dt>Text review</dt><dd>Human-verified source transcription</dd></div>
              )}
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

export function EvidencePanel({ session }: { session: FireLensSession }) {
  const { citedMode, claims, mode, selected, view } = session;
  const selectedClaim = citedMode ? claims[selected] : undefined;
  const evidenceById = useMemo(
    () => new Map((view.kind === "answer" ? (view.response.evidence ?? []) : []).map((item) => [item.evidence_id, item])),
    [view],
  );
  const supportedEvidence = (selectedClaim?.supports ?? [])
    .map((support) => ({ support, evidence: evidenceById.get(support.evidence_id) }))
    .filter((item): item is { support: Support; evidence: Evidence } => Boolean(item.evidence));

  return (
    <section className="evidence-panel" aria-label="Selected claim evidence">
      <div className="evidence-inner">
        {view.kind === "answer" && (mode === "live" || mode === "mixed") && (view.response.live_results ?? []).length > 0 ? (
          <Suspense fallback={<EvidencePlaceholder icon={<span className="spinner" />} title="Loading the official map">Preparing map layers…</EvidencePlaceholder>}>
            <LiveMap
              results={view.response.live_results ?? []}
              aggregateFreshness={view.response.aggregate_freshness ?? undefined}
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
  );
}
