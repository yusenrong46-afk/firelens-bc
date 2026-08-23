import { ArrowSquareOut, Shield } from "@phosphor-icons/react";
import "@fontsource/inter/latin-400.css";
import "@fontsource/inter/latin-500.css";
import "@fontsource/inter/latin-600.css";
import "@fontsource/newsreader/latin-500.css";
import "@fontsource/newsreader/latin-600.css";
import { ConnectionStatus } from "../features/ask/ConnectionStatus";
import { ConversationPanel } from "../features/ask/ConversationPanel";
import { useFireLensSession } from "../features/ask/useFireLensSession";
import { EvidencePanel } from "../features/evidence/EvidencePanel";
import "./styles.css";

export function App() {
  const session = useFireLensSession();

  return (
    <div className="app-shell" id="top">
      <a className="skip-link" href="#conversation">Skip to conversation</a>
      <a className="skip-link" href="#official-map">Skip to official map</a>
      <header className="topbar">
        <a className="brand" href="#top">
          <img src="/assets/firelens-mark.png" alt="" />
          <span><strong>FireLens</strong> BC <small>V1.6 RC1</small></span>
        </a>
        <nav className="workspace-jump" aria-label="Move between conversation and map">
          <a href="#conversation">Conversation</a>
          <a href="#official-map">Official map</a>
        </nav>
        <a className="official-link" href="https://wildfiresituation.nrs.gov.bc.ca/map" target="_blank" rel="noreferrer">
          <ArrowSquareOut size={18} /> Official BCWS map
        </a>
      </header>
      <ConnectionStatus />
      <div className="boundary">
        <Shield size={17} />
        <span>One wildfire helper for official live records, reviewed guidance, and clearly labelled general knowledge.</span>
      </div>
      <main className="workspace">
        <ConversationPanel session={session} />
        <EvidencePanel session={session} />
      </main>
    </div>
  );
}
