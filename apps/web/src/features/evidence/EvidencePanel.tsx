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
import type { AskResponse, LiveResult } from "../../shared/api/api";
import { abstentionPresentation } from "../ask/abstentionPresentation";
import { ProofCard } from "../ask/StatusBanner";
import { getProofCards } from "../ask/proofPresentation";
import type { Evidence, Support } from "../ask/responseModel";
import { resultDisplayName } from "../near-me/liveResultPresentation";
import type { FireLensSession } from "../ask/useFireLensSession";

const LiveMap = lazy(() => import("../near-me/LiveMap").then((module) => ({ default: module.LiveMap })));

function mapResultLinkText(item: LiveResult): string {
  const fallback = item.name || item.incident_number || "Official wildfire record";
  return /(?:featureserver|mapserver|arcgis)/i.test(item.source_url)
    ? `GIS dataset — ${fallback}`
    : fallback;
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

type RelatedLink = NonNullable<AskResponse["related_links"]>[number];

function EvidencePlaceholder({
  icon,
  title,
  children,
  links = [],
}: {
  icon: ReactNode;
  title: string;
  children: ReactNode;
  links?: RelatedLink[] | undefined;
}) {
  return (
    <div className="evidence-placeholder">
      <span>{icon}</span>
      <h2>{title}</h2>
      <p>{children}</p>
      {links.length > 0 && (
        <div className="related-service-links evidence-placeholder__links" aria-label="Related official sources for this boundary">
          {links.map((item) => (
            <a
              key={item.url}
              href={item.url}
              target="_blank"
              rel="noreferrer"
              aria-label={`Open ${item.title} from the answer context`}
            >
              <span><strong>{item.title}</strong><small>{item.description}</small></span>
              <ArrowSquareOut size={18} aria-hidden="true" />
            </a>
          ))}
        </div>
      )}
    </div>
  );
}

export function EvidencePanel({ session }: { session: FireLensSession }) {
  const {
    askAboutResult,
    citedMode,
    claims,
    mapAggregateFreshness,
    mapFocus,
    mapFocusResults,
    mapLoading,
    mapMessage,
    mapResults,
    mapMatchingResults,
    mapProvinceResults,
    mapUnavailableLayers,
    mode,
    selected,
    selectedLiveResultId,
    setSelectedLiveResultId,
    view,
  } = session;
  const selectedClaim = citedMode ? claims[selected] : undefined;
  const proofCards = getProofCards(view.kind === "answer" ? view.response : undefined);
  const selectedProof = selectedClaim
    ? proofCards.find((card) => card.claim_id === selectedClaim.claim_id) ?? proofCards[0]
    : proofCards[0];
  const abstentionCopy = abstentionPresentation(
    view.kind === "abstention" ? view.response.reason_code : undefined,
  );
  const evidenceById = useMemo(
    () => new Map((view.kind === "answer" ? (view.response.evidence ?? []) : []).map((item) => [item.evidence_id, item])),
    [view],
  );
  const supportedEvidence = (selectedClaim?.supports ?? [])
    .map((support) => ({ support, evidence: evidenceById.get(support.evidence_id) }))
    .filter((item): item is { support: Support; evidence: Evidence } => Boolean(item.evidence));

  return (
    <section className="evidence-panel" aria-label="Selected claim evidence">
      <div className="evidence-inner evidence-inner--map-first">
        <Suspense fallback={<EvidencePlaceholder icon={<span className="spinner" />} title="Loading the official map">Preparing map layers…</EvidencePlaceholder>}>
          <LiveMap
            results={mapResults}
            matchingResults={mapMatchingResults}
            provinceResults={mapProvinceResults}
            aggregateFreshness={mapAggregateFreshness}
            unavailableLayers={mapUnavailableLayers}
            focus={mapFocus}
            focusResults={mapFocusResults}
            selectedResultId={selectedLiveResultId}
            onSelectResult={setSelectedLiveResultId}
            onAskAboutResult={askAboutResult}
          />
        </Suspense>
        {mapLoading && <p className="map-surface-status" role="status">Loading official wildfire layers…</p>}
        {mapMessage && <p className="live-map__warning" role="status">{mapMessage} The map remains available for conversation and recovery.</p>}

        <div className="context-lens" aria-label="Answer context">
        {view.kind === "answer" && citedMode && selectedClaim ? (
          <>
            <span className="selected-kicker">Selected claim {selected + 1}</span>
            <h2>{selectedClaim.text}</h2>
            {selectedProof && <ProofCard card={selectedProof} />}
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
            {mode === "mixed" && (view.response.evidence ?? []).length > 0 && (
              <div className="mixed-sources">
                <strong>Preparedness sources</strong>
                {(view.response.evidence ?? []).map((item) => (
                  <a key={item.evidence_id} href={item.canonical_url} target="_blank" rel="noreferrer">{item.title}</a>
                ))}
              </div>
            )}
            <div className="access-date"><Shield size={17} weight="fill" /> Sources come from the reviewed local corpus.</div>
          </>
        ) : view.kind === "answer" && (mode === "live" || mode === "mixed") ? (
          <div className="map-answer-summary">
            <span className="selected-kicker">Official map records</span>
            {selectedProof && <ProofCard card={selectedProof} />}
            {(view.response.live_results ?? []).map((item) => (
              <div className="map-record-actions" key={item.result_id}>
                <button type="button" onClick={() => setSelectedLiveResultId(item.result_id)}>
                  {resultDisplayName(item)}
                </button>
                <a href={item.source_url} target="_blank" rel="noreferrer">
                  {mapResultLinkText(item)} <ArrowSquareOut size={15} />
                </a>
              </div>
            ))}
            {mode === "mixed" && (view.response.evidence ?? []).length > 0 && (
              <div className="mixed-sources">
                <strong>Preparedness sources</strong>
                {(view.response.evidence ?? []).map((item) => (
                  <a key={item.evidence_id} href={item.canonical_url} target="_blank" rel="noreferrer">{item.title}</a>
                ))}
              </div>
            )}
          </div>
        ) : view.kind === "answer" && mode === "background" ? (
          <EvidencePlaceholder icon={<Info size={34} />} title="General background — no corpus evidence attached">
            This explanation uses general model knowledge and was not verified against the reviewed FireLens collection. It is not styled as an official source.
          </EvidencePlaceholder>
        ) : view.kind === "answer" && mode === "capability" ? (
          <EvidencePlaceholder icon={<ChatsCircle size={36} />} title="Explore the FireLens collection">
            Choose a suggested question or ask in your own words. FireLens can discuss reviewed preparedness guidance and clearly labels when an answer uses general background.
          </EvidencePlaceholder>
        ) : view.kind === "loading" ? (
          <EvidencePlaceholder icon={<span className="spinner" />} title="FireLens is working">
            The agent is selecting between official live tools, reviewed retrieval, and labelled general knowledge.
          </EvidencePlaceholder>
        ) : view.kind === "abstention" ? (
          <EvidencePlaceholder
            icon={<WarningCircle size={34} />}
            title={abstentionCopy.title}
            links={view.response.related_links ?? []}
          >
            {abstentionCopy.summary}{" "}
            {(view.response.related_links ?? []).length > 0 ? abstentionCopy.linkLead : ""}
          </EvidencePlaceholder>
        ) : view.kind === "unavailable" || view.kind === "error" ? (
          <EvidencePlaceholder icon={<WarningCircle size={34} />} title="Local service unavailable">
            The failure was returned explicitly. FireLens did not substitute another model or answer from memory.
          </EvidencePlaceholder>
        ) : (
          <EvidencePlaceholder icon={<Shield size={36} />} title="Select a fire or ask anything">
            The official province-wide wildfire map stays visible. Select a record to ask about its status or distance, or use the conversation for reviewed guidance and everyday questions.
          </EvidencePlaceholder>
        )}
        </div>
      </div>
    </section>
  );
}
