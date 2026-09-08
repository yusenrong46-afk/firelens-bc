import { House, Info, MapTrifold } from "@phosphor-icons/react";
import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import "@fontsource/inter/latin-400.css";
import "@fontsource/inter/latin-500.css";
import "@fontsource/inter/latin-600.css";
import "@fontsource/newsreader/latin-500.css";
import "@fontsource/newsreader/latin-600.css";
import { ConnectionStatus } from "../features/ask/ConnectionStatus";
import { ConversationPanel } from "../features/ask/ConversationPanel";
import { QuestionComposer } from "../features/ask/QuestionComposer";
import { useFireLensSession } from "../features/ask/useFireLensSession";
import { EvidencePanel } from "../features/evidence/EvidencePanel";
import {
  LiveAnalysisWorkspace,
  preloadAnalysisCharts,
} from "../features/near-me/LiveAnalysisWorkspace";
import { BCWS_MAP_URL } from "../shared/officialLinks";
import { emitProductEvent } from "../shared/telemetry";
import { ContextChips, deriveContextChips } from "./ContextChips";
import { HowFireLensWorks } from "./HowFireLensWorks";
import { LiveDataStatus } from "./LiveDataStatus";
import { OfficialSourcesCard } from "./OfficialSourcesCard";
import { deriveRecentQuestions, ProductSidebar } from "./ProductSidebar";
import {
  preferredContextSurface,
  shouldOfferContextMap,
  shouldUseAnalyticalWorkspace,
  workspaceLayout,
} from "./workspacePresentation";
import "./tokens.css";
import "./styles.css";
import "./answer.css";
import "./shell.css";

const CompactLiveMap = lazy(() =>
  import("../features/near-me/LiveMap").then((module) => ({ default: module.LiveMap })),
);

export function App() {
  const session = useFireLensSession();
  const [contextSurface, setContextSurface] = useState<"evidence" | "map">("evidence");
  const [idleMapOpen, setIdleMapOpen] = useState(false);
  const [contextOpen, setContextOpen] = useState(false);
  const [projectOpen, setProjectOpen] = useState(false);
  const [mapDismissed, setMapDismissed] = useState(false);
  const contextRef = useRef<HTMLElement>(null);
  const mapRailRef = useRef<HTMLElement>(null);
  const contextTriggerRef = useRef<HTMLElement | null>(null);
  const mapTriggerRef = useRef<HTMLButtonElement>(null);
  const restoreContextFocusRef = useRef(false);
  const composerFocusRef = useRef<HTMLInputElement | null>(null);
  const selectedSourceRecord = [...session.mapResults, ...(session.response?.live_results ?? [])]
    .find((record) => record.result_id === session.selectedLiveResultId);
  const closeProject = useCallback(() => setProjectOpen(false), []);

  const mapAvailable = shouldOfferContextMap({
    mode: session.mode,
    question: session.visibleQuestion,
    response: session.response,
  });
  const responseAnalyticalWorkspace = shouldUseAnalyticalWorkspace({
    mode: session.mode,
    response: session.response,
  });
  const analyticalWorkspace = responseAnalyticalWorkspace;
  const spatialShell = session.response?.presentation_shell === "spatial"
    && (session.mode === "live" || session.mode === "mixed")
    && !analyticalWorkspace;
  const showCompactMapRail = !mapDismissed && (
    spatialShell
    || (session.view.kind === "idle" && idleMapOpen)
    || (!analyticalWorkspace && contextOpen && mapAvailable && contextSurface === "map")
  );
  const evidenceOpen = contextOpen && contextSurface === "evidence" && !spatialShell;
  const showEvidencePanel = evidenceOpen;
  const showMap = showCompactMapRail;
  const layout = workspaceLayout({ analytical: analyticalWorkspace, spatial: showMap });

  const recentQuestions = useMemo(
    () => deriveRecentQuestions(session.history, session.visibleQuestion),
    [session.history, session.visibleQuestion],
  );
  const contextChips = useMemo(
    () => deriveContextChips({
      response: session.response,
      locationLabel: session.activeLocation?.label ?? session.locationLabel,
      activeRadiusKm: session.activeLocation?.radius_km,
    }),
    [session.activeLocation, session.locationLabel, session.response],
  );

  useEffect(() => {
    if (session.view.kind === "idle") {
      setIdleMapOpen(false);
      setContextOpen(false);
      setContextSurface("evidence");
      setMapDismissed(false);
      return;
    }
    setIdleMapOpen(false);
    setMapDismissed(false);
    const preferred = preferredContextSurface({
      mode: session.mode,
      response: session.response,
    });
    const shouldOpenPreferredMap = preferred === "map"
      && !analyticalWorkspace
      && session.response?.presentation_shell === "spatial";
    if (shouldOpenPreferredMap) contextTriggerRef.current = null;
    setContextSurface(preferred);
    setContextOpen(false);
  }, [analyticalWorkspace, session.mode, session.response?.trace_id, session.view.kind, session.visibleQuestion]);

  useEffect(() => {
    if (!showEvidencePanel) return;
    contextRef.current?.focus({ preventScroll: true });
  }, [contextSurface, showEvidencePanel]);

  useEffect(() => {
    if (!showCompactMapRail || showEvidencePanel) return;
    mapRailRef.current?.focus({ preventScroll: true });
  }, [idleMapOpen, showCompactMapRail, showEvidencePanel, session.response?.trace_id]);

  useEffect(() => {
    if (showCompactMapRail || showEvidencePanel || !restoreContextFocusRef.current) return;
    restoreContextFocusRef.current = false;
    const trigger = contextTriggerRef.current?.isConnected
      ? contextTriggerRef.current
      : mapTriggerRef.current
        ?? document.querySelector<HTMLElement>('button[aria-controls="answer-context"]');
    contextTriggerRef.current = null;
    trigger?.focus();
  }, [showCompactMapRail, showEvidencePanel]);

  useEffect(() => {
    if (!analyticalWorkspace) session.setMapVisible(showMap);
  }, [analyticalWorkspace, session.setMapVisible, showMap]);

  useEffect(() => {
    if (session.response?.presentation_shell === "analysis") {
      void preloadAnalysisCharts();
    }
  }, [session.response?.presentation_shell]);

  function showEvidence() {
    if (!contextOpen) {
      contextTriggerRef.current = document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    }
    setIdleMapOpen(false);
    setMapDismissed(false);
    setContextSurface("evidence");
    setContextOpen(true);
    emitProductEvent("evidence_opened");
  }

  function showOfficialMap() {
    contextTriggerRef.current = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;
    if (session.view.kind === "idle") setIdleMapOpen(true);
    setMapDismissed(false);
    setContextSurface("map");
    setContextOpen(true);
    // An explicit map action navigates to it even when spatial answers have
    // already opened the rail below the fold. Automatic opening stays in place.
    requestAnimationFrame(() => {
      mapRailRef.current?.scrollIntoView?.({ block: "start" });
      mapRailRef.current?.focus({ preventScroll: true });
    });
    emitProductEvent("map_opened");
  }

  function closeContext() {
    restoreContextFocusRef.current = true;
    setIdleMapOpen(false);
    setContextOpen(false);
    setMapDismissed(true);
  }

  function goHome() {
    session.clearHistory();
    setIdleMapOpen(false);
    setContextOpen(false);
    setProjectOpen(false);
    window.scrollTo({ top: 0 });
    requestAnimationFrame(() => {
      document.querySelector<HTMLInputElement>('input[aria-label="Ask FireLens a question"]')?.focus();
    });
  }

  function fillFromRecent(question: string) {
    session.setQuery(question);
    requestAnimationFrame(() => {
      const input = document.querySelector<HTMLInputElement>('input[aria-label="Ask FireLens a question"]');
      input?.focus();
    });
  }

  const layoutClass = showCompactMapRail
    ? "pc-layout"
    : "pc-layout pc-layout--no-map";

  return (
    <div className="app-shell" id="top">
      <a className="skip-link" href="#conversation">Skip to conversation</a>
      {showMap && <a className="skip-link" href="#official-map">Skip to official map</a>}
      <ConnectionStatus />
      <HowFireLensWorks open={projectOpen} onClose={closeProject} />
      <div className="pc-frame">
        <header className="pc-mobile-header">
          <a
            className="pc-mobile-header__brand"
            href="/"
            aria-label="FireLens home"
            onClick={(event) => { event.preventDefault(); goHome(); }}
          >
            <img src="/assets/firelens-mark.png" alt="" />
            <strong>FireLens</strong>
          </a>
          <div className="pc-mobile-header__actions">
            <button type="button" onClick={goHome} aria-label="Home"><House size={18} /></button>
            <button
              type="button"
              aria-label="How FireLens works"
              aria-expanded={projectOpen}
              onClick={() => setProjectOpen((open) => !open)}
            >
              <Info size={18} />
            </button>
            <a href={BCWS_MAP_URL} target="_blank" rel="noreferrer" aria-label="Official BCWS map">
              <MapTrifold size={18} />
            </a>
          </div>
        </header>

        <div className={layoutClass}>
          <ProductSidebar
            homeActive={session.view.kind === "idle"}
            onHome={goHome}
            onHowItWorks={() => setProjectOpen((open) => !open)}
            onClear={goHome}
            onSelectQuestion={fillFromRecent}
            howItWorksOpen={projectOpen}
            recentQuestions={recentQuestions}
          />

          <div className="pc-main">
            {session.visibleQuestion && <section aria-label="Current question"><h1 className="pc-current-question response-announcement">{session.visibleQuestion}</h1></section>}
            {!showCompactMapRail && (session.view.kind === "idle" || session.mode === "live" || session.mode === "mixed") && (
              <div className="pc-main__status">
                <LiveDataStatus liveSummary={session.liveSummary} readiness={session.readiness} now={session.statusNow} />
                {session.view.kind === "idle" && (
                  <button
                    ref={mapTriggerRef}
                    type="button"
                    className="product-nav"
                    onClick={showOfficialMap}
                    aria-pressed={showMap}
                  >
                    <MapTrifold size={17} /> Explore live map
                  </button>
                )}
              </div>
            )}
            <main
              className={`workspace workspace--${layout} workspace--solo ${showMap ? "workspace--map" : "workspace--evidence"}`}
            >
              <ConversationPanel
                session={session}
                analytical={analyticalWorkspace}
                analysisSlot={responseAnalyticalWorkspace ? (
                  <LiveAnalysisWorkspace
                    session={session}
                    answerIdentity={session.response?.trace_id ?? ""}
                    evidenceOpen={showEvidencePanel}
                    onOpenEvidence={() => {
                      session.setSelected(0);
                      showEvidence();
                    }}
                  />
                ) : undefined}
                onOpenEvidence={showEvidence}
                onOpenMap={showOfficialMap}
                contextOpen={showCompactMapRail || showEvidencePanel}
                contextSurface={showCompactMapRail ? "map" : contextSurface}
                contextChips={<ContextChips chips={contextChips} />}
              />
              {showEvidencePanel && (
                <EvidencePanel
                  session={session}
                  surface="evidence"
                  mapAvailable={false}
                  panelRef={contextRef}
                  onClose={closeContext}
                  onSurfaceChange={(surface) => {
                    if (surface === "map") showOfficialMap();
                    else showEvidence();
                  }}
                />
              )}
            </main>
            <footer className="pc-disclaimer">
              FireLens provides information, not decisions. For emergencies call 9-1-1 and follow local authorities.
            </footer>
            {!showCompactMapRail && (session.mode === "live" || session.mode === "mixed") && (
              <OfficialSourcesCard response={session.response} selectedResultId={session.selectedLiveResultId} selectedRecord={selectedSourceRecord} />
            )}
          </div>

          {showCompactMapRail && !analyticalWorkspace && (
            <aside
              className="pc-map-rail"
              aria-label="Map"
              id={showEvidencePanel ? undefined : "answer-context"}
              ref={mapRailRef}
              tabIndex={-1}
            >
              <div className="pc-map-rail__toolbar">
                <LiveDataStatus liveSummary={session.liveSummary} readiness={session.readiness} now={session.statusNow} />
                {(idleMapOpen || contextOpen || spatialShell) && (
                  <button
                    type="button"
                    className="context-close"
                    aria-label="Close answer context"
                    onClick={closeContext}
                  >
                    Close
                  </button>
                )}
              </div>
              <Suspense fallback={<p role="status">Loading map…</p>}>
                <CompactLiveMap
                  variant={spatialShell && !idleMapOpen ? "compact" : "full"}
                  results={session.mapResults}
                  matchingResults={session.mapMatchingResults}
                  provinceResults={session.mapProvinceResults}
                  aggregateFreshness={session.mapAggregateFreshness}
                  partialLayers={session.mapPartialLayers}
                  unavailableLayers={session.mapUnavailableLayers}
                  geometryOmissions={session.mapGeometryOmissions}
                  focus={session.mapFocus}
                  focusResults={session.mapFocusResults}
                  selectedResultId={session.selectedLiveResultId}
                  onSelectResult={session.setSelectedLiveResultId}
                  onAskAboutResult={session.askAboutResult}
                  contextLayersEnabled={session.contextLayersEnabled}
                  onContextLayersChange={session.setContextLayersEnabled}
                />
              </Suspense>
              <OfficialSourcesCard response={session.response} selectedResultId={session.selectedLiveResultId} selectedRecord={selectedSourceRecord} />
            </aside>
          )}
        </div>
      </div>
      <div className="pc-composer-dock" role="search" aria-label="Ask FireLens">
        <QuestionComposer
          idle={session.view.kind === "idle"}
          loading={session.view.kind === "loading"}
          continuationPending={session.requiresLocation}
          query={session.query}
          onQueryChange={session.setQuery}
          onSubmit={session.submit}
          inputRef={composerFocusRef}
        />
      </div>
    </div>
  );
}
