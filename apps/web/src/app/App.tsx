import { ArrowSquareOut, Shield } from "@phosphor-icons/react";
import "@fontsource/inter/latin-400.css";
import "@fontsource/inter/latin-500.css";
import "@fontsource/inter/latin-600.css";
import "@fontsource/newsreader/latin-500.css";
import "@fontsource/newsreader/latin-600.css";
import { ConversationPanel } from "../features/ask/ConversationPanel";
import { useFireLensSession } from "../features/ask/useFireLensSession";
import { EvidencePanel } from "../features/evidence/EvidencePanel";
import "./styles.css";

export function App() {
  const session = useFireLensSession();

  return (
    <div className="app-shell" id="top">
      <header className="topbar">
        <a className="brand" href="#top">
          <img src="/assets/firelens-mark.png" alt="" />
          <span><strong>FireLens</strong> BC <small>V1.5 V3</small></span>
        </a>
        <a className="official-link" href="https://wildfiresituation.nrs.gov.bc.ca/map" target="_blank" rel="noreferrer">
          <ArrowSquareOut size={18} /> Official BCWS map
        </a>
      </header>
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
