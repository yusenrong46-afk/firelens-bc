import { ArrowLeft, ArrowsOut } from "@phosphor-icons/react";
import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import "@fontsource/inter/latin-400.css";
import "@fontsource/inter/latin-500.css";
import "@fontsource/inter/latin-600.css";
import "@fontsource/newsreader/latin-500.css";
import "@fontsource/newsreader/latin-600.css";
import { ConnectionStatus } from "../features/ask/ConnectionStatus";
import { ConversationPanel } from "../features/ask/ConversationPanel";
import { PREPAREDNESS_QUESTION } from "../features/ask/AskStartPanel";
import { QuestionComposer } from "../features/ask/QuestionComposer";
import { useFireLensSession } from "../features/ask/useFireLensSession";
import { EvidencePanel } from "../features/evidence/EvidencePanel";
import { LiveAnalysisWorkspace, preloadAnalysisCharts } from "../features/near-me/LiveAnalysisWorkspace";
import { emitProductEvent } from "../shared/telemetry";
import { ContextChips, deriveContextChips } from "./ContextChips";
import { HowFireLensWorks } from "./HowFireLensWorks";
import { deriveRecentQuestions } from "./ProductSidebar";
import { shouldOfferContextMap, shouldUseAnalyticalWorkspace, workspaceLayout } from "./workspacePresentation";
import { AtlasHeader } from "./AtlasHeader";
import { AtlasQuestion } from "./AtlasQuestion";
import "./tokens.css";
import "./styles.css";
import "./answer.css";
import "./shell.css";
import "./productExperience.css";
import "./atlas.css";
import "./atlasAnswers.css";
import "./atlasSheet.css";

const AtlasLiveMap = lazy(() => import("../features/near-me/AtlasLiveMap"));

export function App() {
  const session = useFireLensSession();
  const [mapRequested, setMapRequested] = useState(false);
  const [mapEpoch, setMapEpoch] = useState(0);
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  const [projectOpen, setProjectOpen] = useState(false);
  const [askOpen, setAskOpen] = useState(false);
  const [examplesRequested, setExamplesRequested] = useState(false);
  const [mapExpanded, setMapExpanded] = useState(false);
  const contextRef = useRef<HTMLElement>(null);
  const evidenceDialog = useRef<HTMLDialogElement>(null);
  const mapRailRef = useRef<HTMLElement>(null);
  const contextTrigger = useRef<HTMLElement | null>(null);
  const composerRef = useRef<HTMLInputElement | null>(null);
  const closeProject = useCallback(() => setProjectOpen(false), []);
  const analytical = shouldUseAnalyticalWorkspace({ mode: session.mode, response: session.response });
  const contextualMap = !analytical && shouldOfferContextMap({ mode: session.mode, response: session.response });
  const home = session.view.kind === "idle";
  const showMap = home || mapExpanded || mapRequested || contextualMap;
  const layout = workspaceLayout({ analytical, spatial: showMap });
  const recentQuestions = useMemo(() => deriveRecentQuestions(session.history, session.visibleQuestion), [session.history, session.visibleQuestion]);
  const contextChips = useMemo(() => deriveContextChips({ response: session.response, locationLabel: session.activeLocation?.label ?? session.locationLabel, activeRadiusKm: session.activeLocation?.radius_km }), [session.activeLocation, session.locationLabel, session.response]);

  useEffect(() => {
    setMapRequested(false);
    setMapExpanded(false);
    setEvidenceOpen(false);
    setAskOpen(false);
  }, [session.view.kind, session.response?.trace_id, session.visibleQuestion]);

  useEffect(() => {
    // The analytical workspace owns its tab visibility. All other routes use
    // the visible map surface; guidance pauses automatic province refresh.
    if (analytical) return;
    session.setMapVisible(showMap);
    session.setContextLayersEnabled(showMap);
  }, [analytical, session.setMapVisible, session.setContextLayersEnabled, showMap]);

  useEffect(() => {
    if (session.response?.presentation_shell === "analysis") void preloadAnalysisCharts();
  }, [session.response?.presentation_shell]);

  useEffect(() => {
    if (evidenceOpen) { evidenceDialog.current?.showModal(); contextRef.current?.focus({ preventScroll: true }); }
    else if (evidenceDialog.current?.open) evidenceDialog.current.close();
  }, [evidenceOpen]);

  useEffect(() => {
    if (showMap && !evidenceOpen && !session.requiresLocation) mapRailRef.current?.focus({ preventScroll: true });
  }, [showMap, evidenceOpen, session.requiresLocation, session.response?.trace_id]);

  function showEvidence() {
    contextTrigger.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setEvidenceOpen(true);
    emitProductEvent("evidence_opened");
  }
  function closeEvidence() {
    evidenceDialog.current?.close();
    setEvidenceOpen(false);
    const trigger = contextTrigger.current;
    if (trigger?.isConnected) trigger.focus();
    requestAnimationFrame(() => { if (trigger?.isConnected) trigger.focus(); });
  }
  function showOfficialMap() {
    setAskOpen(false);
    setMapRequested(true);
    requestAnimationFrame(() => { mapRailRef.current?.scrollIntoView?.({ block: "start" }); mapRailRef.current?.focus({ preventScroll: true }); });
    emitProductEvent("map_opened");
  }
  function expandOfficialMap() { session.setContextLayersEnabled(true); showOfficialMap(); setMapExpanded(true); }
  function goHome() {
    session.clearHistory(); setMapEpoch(epoch => epoch + 1); setMapRequested(false); setEvidenceOpen(false); setProjectOpen(false); setAskOpen(false); setMapExpanded(false);
    window.scrollTo({ top: 0 });
    requestAnimationFrame(() => mapRailRef.current?.focus());
  }
  function fillQuestion(question: string) {
    setMapExpanded(false); setMapRequested(false); setAskOpen(true); session.setQuery(question);
    requestAnimationFrame(() => composerRef.current?.focus());
  }
  function openAsk() {
    if (!mapExpanded && session.view.kind !== "idle") requestAnimationFrame(() => composerRef.current?.focus());
    else setAskOpen(true);
  }
  function showExamples() { setExamplesRequested(true); setAskOpen(true); }
  const composer = <QuestionComposer idle={session.view.kind === "idle"} loading={session.view.kind === "loading"} continuationPending={session.requiresLocation} query={session.query} onQueryChange={session.setQuery} onSubmit={session.submit} inputRef={composerRef} />;
  return <div className={`app-shell atlas-shell atlas-sheet-shell${home ? " app-shell--home" : ""}`} id="top">
    {!mapExpanded && !home && <a className="skip-link" href="#conversation">Skip to conversation</a>}
    {showMap && <a className="skip-link" href="#official-map">Skip to official map</a>}
    <ConnectionStatus />
    <HowFireLensWorks open={projectOpen} onClose={closeProject} />
    <AtlasHeader onHome={goHome} onAsk={openAsk} onMap={expandOfficialMap} onPrepare={() => fillQuestion(PREPAREDNESS_QUESTION)} onExamples={showExamples} onAbout={() => setProjectOpen(true)} onLocation={() => { setAskOpen(true); session.useApproximateLocation(); }} onRecent={fillQuestion} recentQuestions={recentQuestions} />
    <div className="pc-frame" role={mapExpanded || session.view.kind === "idle" ? "main" : undefined} aria-label={mapExpanded || session.view.kind === "idle" ? "Explore official records" : undefined}>
      <div className={`pc-layout${showMap ? "" : " pc-layout--no-map"}${mapExpanded || home ? " pc-layout--expanded" : ""}`}>
        {session.view.kind !== "idle" && <div className="pc-main" hidden={mapExpanded}>
          <nav className="sheet-heading" aria-label="Answer navigation"><button type="button" onClick={expandOfficialMap}><ArrowLeft size={18} />Back to map</button><button type="button" onClick={expandOfficialMap} aria-label="Expand map"><ArrowsOut size={18} />Expand map</button></nav>
          {session.visibleQuestion && <section aria-label="Current question"><h1 className="pc-current-question">{session.visibleQuestion}</h1></section>}
          <main className={`workspace workspace--${layout} workspace--solo ${showMap ? "workspace--map" : "workspace--evidence"}`}>
            <ConversationPanel session={session} analytical={analytical} condensed={!analytical}
                analysisSlot={analytical ? <LiveAnalysisWorkspace session={session} answerIdentity={session.response?.trace_id ?? ""} evidenceOpen={evidenceOpen} externalMapOpen={mapExpanded} onOpenEvidence={() => { session.setSelected(0); showEvidence(); }} /> : undefined}
                homeComposer={composer} onPrepareQuestion={fillQuestion} onExploreMap={expandOfficialMap} onOpenEvidence={showEvidence} onOpenMap={showOfficialMap} contextOpen={showMap || evidenceOpen} contextSurface={showMap ? "map" : "evidence"} contextChips={<ContextChips chips={contextChips} />} />
          </main>
          {!askOpen && <div className="sheet-composer" role="search" aria-label="Ask FireLens">{composer}</div>}
          <footer className="pc-disclaimer">Follow local authorities. For emergencies call 9-1-1.</footer>
        </div>}
        <aside hidden={!showMap} className="pc-map-rail" aria-label="Map" id="map-context" ref={mapRailRef} tabIndex={-1}>
          {mapExpanded && !home && <div className="pc-map-rail__toolbar"><button type="button" className="product-nav map-back" onClick={() => { setMapExpanded(false); setMapRequested(false); requestAnimationFrame(() => composerRef.current?.focus()); }}><ArrowLeft size={18} />Back to answer</button></div>}
          <Suspense fallback={<p role="status">Loading map…</p>}><AtlasLiveMap key={mapEpoch} session={session} visible={showMap} /></Suspense>
        </aside>
      </div>
    </div>
    <dialog ref={evidenceDialog} className="evidence-dialog" aria-label="Inspect answer evidence" onCancel={closeEvidence} onClose={() => setEvidenceOpen(false)}>
      {evidenceOpen && <EvidencePanel session={session} surface="evidence" mapAvailable={false} panelRef={contextRef} onClose={closeEvidence} onSurfaceChange={() => { closeEvidence(); showOfficialMap(); }} />}
    </dialog>
    <AtlasQuestion session={session} composer={askOpen ? composer : undefined} open={askOpen} examplesRequested={examplesRequested} onClose={() => { setAskOpen(false); setExamplesRequested(false); }} onPrepare={fillQuestion} onMap={expandOfficialMap} />
  </div>;
}
