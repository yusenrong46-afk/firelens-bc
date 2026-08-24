import { ArrowSquareOut, Info, MapTrifold, Shield } from "@phosphor-icons/react";
import { useCallback, useEffect, useState } from "react";
import "@fontsource/inter/latin-400.css";
import "@fontsource/inter/latin-500.css";
import "@fontsource/inter/latin-600.css";
import "@fontsource/newsreader/latin-500.css";
import "@fontsource/newsreader/latin-600.css";
import { ConnectionStatus } from "../features/ask/ConnectionStatus";
import { ConversationPanel } from "../features/ask/ConversationPanel";
import { useFireLensSession } from "../features/ask/useFireLensSession";
import { EvidencePanel } from "../features/evidence/EvidencePanel";
import { LiveAnalysisWorkspace } from "../features/near-me/LiveAnalysisWorkspace";
import { HowFireLensWorks } from "./HowFireLensWorks";
import { preferredContextSurface, shouldOfferContextMap, shouldUseAnalyticalWorkspace } from "./workspacePresentation";
import "./styles.css";

export function App() {
  const session = useFireLensSession();
  const [contextSurface, setContextSurface] = useState<"evidence" | "map">("evidence");
  const [idleMapOpen, setIdleMapOpen] = useState(false);
  const [contextOpen, setContextOpen] = useState(false);
  const [projectOpen, setProjectOpen] = useState(false);
  const closeProject = useCallback(() => setProjectOpen(false), []);
  const mapAvailable = shouldOfferContextMap({
    mode: session.mode,
    question: session.visibleQuestion,
    response: session.response,
  });
  const analyticalWorkspace = shouldUseAnalyticalWorkspace({
    mode: session.mode,
    question: session.visibleQuestion,
    response: session.response,
  });
  const showMap = (session.view.kind === "idle" && idleMapOpen)
    || (!analyticalWorkspace && contextOpen && mapAvailable && contextSurface === "map");
  const evidenceOpen = !analyticalWorkspace && contextOpen && contextSurface === "evidence";
  const showContext = showMap || evidenceOpen;

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
    setContextSurface(preferred);
    setContextOpen(false);
  }, [session.mode, session.response?.trace_id, session.view.kind, session.visibleQuestion]);

  useEffect(() => {
    if (!analyticalWorkspace) session.setMapVisible(showMap);
  }, [analyticalWorkspace, session.setMapVisible, showMap]);

  function showEvidence() {
    setIdleMapOpen(false);
    setContextSurface("evidence");
    setContextOpen(true);
  }

  function showOfficialMap() {
    if (session.view.kind === "idle") setIdleMapOpen(true);
    setContextSurface("map");
    setContextOpen(true);
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
        <div className="topbar-actions">
          <a className="topbar-anchor" href="#conversation">Ask</a>
          <button className="topbar-project" type="button" aria-label="How FireLens works" onClick={() => setProjectOpen(true)}>
            <Info size={18} />
            <span><strong>How FireLens works</strong><small>For employers &amp; evaluators</small></span>
          </button>
          {(session.view.kind === "idle" || (mapAvailable && !showContext && !analyticalWorkspace)) && (
            <nav className="workspace-jump" aria-label="Choose workspace context">
              <button
                type="button"
                className={showMap ? "workspace-jump__active" : ""}
                onClick={showOfficialMap}
                aria-pressed={showMap}
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
        <span>Official live records, reviewed guidance, and general background stay visibly separate.</span>
      </div>
      <main className={`workspace ${showContext ? "workspace--split" : "workspace--solo"} ${showMap ? "workspace--map" : "workspace--evidence"}`}>
        <ConversationPanel
          session={session}
          analytical={analyticalWorkspace}
          analysisSlot={analyticalWorkspace ? <LiveAnalysisWorkspace session={session} embedded /> : undefined}
          onOpenEvidence={showEvidence}
          onOpenMap={showOfficialMap}
        />
        {showContext && (
          <EvidencePanel
            session={session}
            surface={showMap ? "map" : "evidence"}
            mapAvailable={session.view.kind === "idle" || mapAvailable}
            onSurfaceChange={(surface) => {
              if (surface === "map") showOfficialMap();
              else showEvidence();
            }}
          />
        )}
      </main>
      <HowFireLensWorks open={projectOpen} onClose={closeProject} />
    </div>
  );
}
