import { ArrowSquareOut, MapTrifold, Shield } from "@phosphor-icons/react";
import { useEffect, useState } from "react";
import "@fontsource/inter/latin-400.css";
import "@fontsource/inter/latin-500.css";
import "@fontsource/inter/latin-600.css";
import "@fontsource/newsreader/latin-500.css";
import "@fontsource/newsreader/latin-600.css";
import { ConnectionStatus } from "../features/ask/ConnectionStatus";
import { ConversationPanel } from "../features/ask/ConversationPanel";
import { useFireLensSession } from "../features/ask/useFireLensSession";
import { EvidencePanel } from "../features/evidence/EvidencePanel";
import { preferredContextSurface, shouldOfferContextMap } from "./workspacePresentation";
import "./styles.css";

export function App() {
  const session = useFireLensSession();
  const [contextSurface, setContextSurface] = useState<"evidence" | "map">("evidence");
  const [idleMapOpen, setIdleMapOpen] = useState(false);
  const mapAvailable = shouldOfferContextMap({
    mode: session.mode,
    question: session.visibleQuestion,
    response: session.response,
  });
  const hasResponseContext = Boolean(
    session.response
    && (
      session.claims.length > 0
      || (session.response.evidence ?? []).length > 0
      || (session.response.live_results ?? []).length > 0
    ),
  );
  const showMap = (session.view.kind === "idle" && idleMapOpen)
    || (mapAvailable && contextSurface === "map");
  const showContext = hasResponseContext || showMap;

  useEffect(() => {
    if (session.view.kind === "idle") {
      setIdleMapOpen(false);
      setContextSurface("evidence");
      return;
    }
    setIdleMapOpen(false);
    setContextSurface(preferredContextSurface({
      mode: session.mode,
      question: session.visibleQuestion,
    }));
  }, [session.mode, session.response?.trace_id, session.view.kind, session.visibleQuestion]);

  useEffect(() => {
    session.setMapVisible(showMap);
  }, [session.setMapVisible, showMap]);

  function showEvidence() {
    setIdleMapOpen(false);
    setContextSurface("evidence");
  }

  function showOfficialMap() {
    if (session.view.kind === "idle") setIdleMapOpen(true);
    setContextSurface("map");
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
          {(session.view.kind === "idle" || (mapAvailable && !showContext)) && (
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
        <ConversationPanel session={session} />
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
    </div>
  );
}
