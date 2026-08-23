import { lazy, Suspense, useMemo } from "react";
import {
  ArrowSquareOut,
  ChatsCircle,
  Info,
  Shield,
  WarningCircle,
} from "@phosphor-icons/react";
import { abstentionPresentation } from "../ask/abstentionPresentation";
import { ProofCard } from "../ask/StatusBanner";
import {
  getClaimSupportState,
  getProofCards,
  type SupportState,
} from "../ask/proofPresentation";
import type { Evidence, Support } from "../ask/responseModel";
import { resultDisplayName } from "../near-me/liveResultPresentation";
import type { FireLensSession } from "../ask/useFireLensSession";
import {
  EvidencePlaceholder,
  mapResultLinkText,
  SourcePanel,
} from "./evidencePresentation";

const LiveMap = lazy(() => import("../near-me/LiveMap").then((module) => ({ default: module.LiveMap })));


function selectedClaimHeading(state: SupportState): string {
  const headings: Partial<Record<SupportState, string>> = {
    supported: "Source-supported claim",
    structured_reviewed: "Reviewed structured claim",
    official_live_typed: "Official typed fact",
    official_quote_only: "Exact source quotation",
    source_linked_explanation: "Source-linked explanation",
    unknown: "Content not established",
    background: "General background",
    conflict: "Conflicting reviewed claim",
  };
  return headings[state] ?? "Answer support";
}

function selectedClaimFooter(state: SupportState): string {
  const footers: Partial<Record<SupportState, string>> = {
    supported: "This claim is linked to an exact passage in the reviewed source collection.",
    structured_reviewed: "This structured claim has reviewed source support.",
    official_live_typed: "This fact is projected from an official typed record.",
    official_quote_only: "This is exact source wording, not a structured FireLens claim.",
    source_linked_explanation: "This explanation is source-linked but is not a reviewed structured claim.",
    unknown: "FireLens did not establish this content from its reviewed or official sources.",
    background: "This is labelled general background and has no reviewed source support attached.",
    conflict: "Reviewed sources conflict; FireLens has not chosen a winner.",
  };
  return footers[state] ?? "Support details are shown above.";
}

export function EvidencePanel({ session }: { session: FireLensSession }) {
  const {
    askAboutResult,
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
  const answerResponse = view.kind === "answer" ? view.response : undefined;
  const selectedClaim = answerResponse ? claims[selected] : undefined;
  const selectedState = answerResponse && selectedClaim
    ? getClaimSupportState(answerResponse, selectedClaim)
    : undefined;
  const proofCards = getProofCards(answerResponse);
  const selectedProof = selectedClaim
    ? proofCards.find((card) => card.claim_id === selectedClaim.claim_id)
    : proofCards[0];
  const abstentionCopy = abstentionPresentation(
    view.kind === "abstention" ? view.response.reason_code : undefined,
  );
  const evidenceById = useMemo(
    () => new Map((view.kind === "answer" ? (view.response.evidence ?? []) : []).map((item) => [item.evidence_id, item])),
    [view],
  );
  const supportedEvidence = selectedState === "unknown" || selectedState === "background"
    ? []
    : (selectedClaim?.supports ?? [])
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
        {view.kind === "answer" && selectedClaim && selectedState ? (
          <>
            <span className="selected-kicker">Selected claim {selected + 1}</span>
            <h2>{selectedClaim.text}</h2>
            {selectedProof && <ProofCard card={selectedProof} />}
            <div className="answer-claim">
              <Shield size={18} /><strong>{selectedClaimHeading(selectedState)}</strong><span>{selectedClaim.text}</span>
            </div>
            {supportedEvidence.map(({ evidence, support }, index) => (
              <SourcePanel
                key={`${evidence.evidence_id}:${support.quote}`}
                evidence={evidence}
                support={support}
                index={index}
                initiallyOpen={index === 0}
                supportState={selectedState}
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
            <div className="access-date"><Shield size={17} weight="fill" /> {selectedClaimFooter(selectedState)}</div>
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
