import { ArrowSquareOut, Info, MapTrifold, Shield } from "@phosphor-icons/react";
import { useCallback, useEffect, useRef, useState } from "react";
import "@fontsource/inter/latin-400.css";
import "@fontsource/inter/latin-500.css";
import "@fontsource/inter/latin-600.css";
import "@fontsource/newsreader/latin-500.css";
import "@fontsource/newsreader/latin-600.css";
import { ConnectionStatus } from "../features/ask/ConnectionStatus";
import { ConversationPanel } from "../features/ask/ConversationPanel";
import { useFireLensSession } from "../features/ask/useFireLensSession";
import { EvidencePanel } from "../features/evidence/EvidencePanel";
import {
  LiveAnalysisWorkspace,
  preloadAnalysisCharts,
} from "../features/near-me/LiveAnalysisWorkspace";
import { HowFireLensWorks } from "./HowFireLensWorks";
import {
  preferredAnalyticalSurface,
  preferredContextSurface,
  questionExplicitlyRequestsMap,
  shouldOfferContextMap,
  shouldUseAnalyticalWorkspace,
  workspaceLayout,
} from "./workspacePresentation";
import "./styles.css";

const ANALYTICAL_QUERY =
  /\b(?:distribution|distributed|by\s+(?:status|region|fire[- ]?centre)|fire[- ]?centre\s+counts?|where\s+are\s+the\s+most)\b/i;

export function App() {
  const session = useFireLensSession();
  const [contextSurface, setContextSurface] = useState<"evidence" | "map">("evidence");
  const [idleMapOpen, setIdleMapOpen] = useState(false);
  const [contextOpen, setContextOpen] = useState(false);
  const [projectOpen, setProjectOpen] = useState(false);
  const contextRef = useRef<HTMLElement>(null);
  const contextTriggerRef = useRef<HTMLElement | null>(null);
  const mapTriggerRef = useRef<HTMLButtonElement>(null);
  const restoreContextFocusRef = useRef(false);
  const closeProject = useCallback(() => setProjectOpen(false), []);
  const mapAvailable = shouldOfferContextMap({
    mode: session.mode,
    question: session.visibleQuestion,
    response: session.response,
  });
  const analyticalWorkspace = shouldUseAnalyticalWorkspace({
    mode: session.mode,
    response: session.response,
  });
  const analyticalInitialSurface = preferredAnalyticalSurface({
    mode: session.mode,
    question: session.visibleQuestion,
    response: session.response,
  });
  const showMap = (session.view.kind === "idle" && idleMapOpen)
    || (!analyticalWorkspace && contextOpen && mapAvailable && contextSurface === "map");
  const evidenceOpen = contextOpen && contextSurface === "evidence";
  const showContext = showMap || evidenceOpen;
  const layout = workspaceLayout({ analytical: analyticalWorkspace, spatial: showMap });

  useEffect(() => {
    if (session.view.kind === "idle") {
      setIdleMapOpen(false);
      setContextOpen(false);
      setContextSurface("evidence");
      return;
    }
    setIdleMapOpen(false);
    const preferred = preferredContextSurface({
      mode: session.mode,
      question: session.visibleQuestion,
    });
    const shouldOpenPreferredMap = preferred === "map"
      && !analyticalWorkspace
      && questionExplicitlyRequestsMap(session.visibleQuestion);
    if (shouldOpenPreferredMap) contextTriggerRef.current = null;
    setContextSurface(preferred);
    setContextOpen(shouldOpenPreferredMap);
  }, [analyticalWorkspace, session.mode, session.response?.trace_id, session.view.kind, session.visibleQuestion]);

  useEffect(() => {
    if (!showContext) return;
    contextRef.current?.scrollIntoView?.({ block: "start", inline: "nearest" });
    contextRef.current?.focus({ preventScroll: true });
  }, [contextSurface, showContext]);

  useEffect(() => {
    if (showContext || !restoreContextFocusRef.current) return;
    restoreContextFocusRef.current = false;
    const trigger = contextTriggerRef.current?.isConnected
      ? contextTriggerRef.current
      : mapTriggerRef.current;
    contextTriggerRef.current = null;
    trigger?.focus();
  }, [showContext]);

  useEffect(() => {
    if (!analyticalWorkspace) session.setMapVisible(showMap);
  }, [analyticalWorkspace, session.setMapVisible, showMap]);

  useEffect(() => {
    if (
      session.view.kind === "loading"
      && ANALYTICAL_QUERY.test(session.visibleQuestion ?? "")
    ) {
      void preloadAnalysisCharts();
    }
  }, [session.view.kind, session.visibleQuestion]);

  function showEvidence() {
    if (!contextOpen) {
      contextTriggerRef.current = document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    }
    setIdleMapOpen(false);
    setContextSurface("evidence");
    setContextOpen(true);
  }

  function showOfficialMap() {
    if (!contextOpen) {
      contextTriggerRef.current = document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    }
    if (session.view.kind === "idle") setIdleMapOpen(true);
    setContextSurface("map");
    setContextOpen(true);
  }

  function closeContext() {
    restoreContextFocusRef.current = true;
    setIdleMapOpen(false);
    setContextOpen(false);
  }

  return (
    <div className="app-shell" id="top">
      <a className="skip-link" href="#conversation">Skip to conversation</a>
      {showMap && <a className="skip-link" href="#official-map">Skip to official map</a>}
      <header className="topbar">
        <a className="brand" href="#top">
          <img src="/assets/firelens-mark.png" alt="" />
          <span><strong>FireLens</strong> BC <small>V1.6</small></span>
        </a>
        <span className="topbar-lockup" aria-label="Civic Intelligence Desk">Civic Intelligence Desk</span>
        <div className="topbar-actions">
          <button
            className="topbar-project"
            type="button"
            aria-label="How FireLens works"
            aria-expanded={projectOpen}
            aria-controls="how-firelens-works"
            onClick={() => setProjectOpen((open) => !open)}
          >
            <Info size={18} />
            <span className="topbar-project__detail"><strong>How FireLens works</strong><small>For employers &amp; evaluators</small></span>
            <span className="topbar-project__compact-label">How it works</span>
          </button>
          {analyticalWorkspace && (
            <a className="topbar-anchor" href="https://wildfiresituation.nrs.gov.bc.ca/map" target="_blank" rel="noreferrer">
              <MapTrifold size={17} /> Explore live map
            </a>
          )}
          {(session.view.kind === "idle" || (mapAvailable && !showContext && !analyticalWorkspace)) && (
            <nav className="workspace-jump" aria-label="Choose workspace context">
              <button
                ref={mapTriggerRef}
                type="button"
                className={showMap ? "workspace-jump__active" : ""}
                onClick={showOfficialMap}
                aria-pressed={showMap}
                aria-expanded={showMap}
                aria-controls="answer-context"
              >
                <MapTrifold size={17} /> {session.view.kind === "idle" ? "Explore live map" : "Open map"}
              </button>
            </nav>
          )}
          <a className="official-link" href="https://wildfiresituation.nrs.gov.bc.ca/map" target="_blank" rel="noreferrer">
            <ArrowSquareOut size={18} /> Official BCWS map
          </a>
        </div>
      </header>
      <ConnectionStatus />
      <div className="boundary">
        <Shield size={17} />
        <span>Official-source data. Not a safety assessment.</span>
      </div>
      <HowFireLensWorks open={projectOpen} onClose={closeProject} />
      <main className={`workspace workspace--${layout} ${showContext ? "workspace--split" : "workspace--solo"} ${showMap ? "workspace--map" : "workspace--evidence"}`}>
        <ConversationPanel
          session={session}
          analytical={analyticalWorkspace}
          analysisSlot={analyticalWorkspace ? (
            <LiveAnalysisWorkspace
              session={session}
              answerIdentity={session.response?.trace_id ?? ""}
              evidenceOpen={showContext && contextSurface === "evidence"}
              initialSurface={analyticalInitialSurface}
              onOpenEvidence={() => {
                session.setSelected(0);
                showEvidence();
              }}
            />
          ) : undefined}
          onOpenEvidence={showEvidence}
          onOpenMap={showOfficialMap}
          contextOpen={showContext}
          contextSurface={contextSurface}
        />
        {showContext && (
          <EvidencePanel
            session={session}
            surface={showMap ? "map" : "evidence"}
            mapAvailable={!analyticalWorkspace && (session.view.kind === "idle" || mapAvailable)}
            panelRef={contextRef}
            onClose={closeContext}
            onSurfaceChange={(surface) => {
              if (surface === "map") showOfficialMap();
              else showEvidence();
            }}
          />
        )}
      </main>
    </div>
  );
}
