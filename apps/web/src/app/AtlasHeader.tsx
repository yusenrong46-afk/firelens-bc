import { List, MagnifyingGlass, X } from "@phosphor-icons/react";
import { useRef } from "react";
import type { RecentQuestion } from "./ProductSidebar";

export function AtlasHeader({ onHome, onAsk, onMap, onPrepare, onExamples, onAbout, onLocation, onRecent, recentQuestions }: {
  onHome: () => void; onAsk: () => void; onMap: () => void;
  onPrepare: () => void; onExamples: () => void; onAbout: () => void;
  onLocation: () => void; onRecent: (question: string) => void;
  recentQuestions: RecentQuestion[];
}) {
  const menu = useRef<HTMLDialogElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  function act(action: () => void) { menu.current?.close(); action(); }
  return <header className="atlas-header">
    <a className="atlas-brand" href="/" aria-label="FireLens home" onClick={(event) => { event.preventDefault(); onHome(); }}>
      <img src="/assets/firelens-mark.png" alt="" width="30" height="30" /><strong>FireLens</strong>
    </a>
    <nav aria-label="Primary navigation">
      <button className="atlas-ask" aria-label="Ask FireLens" type="button" onClick={onAsk}><MagnifyingGlass size={21} /><span>Ask FireLens</span></button>
      <button ref={trigger} type="button" aria-label="Open menu" aria-haspopup="dialog" onClick={() => menu.current?.showModal()}><List size={24} /></button>
    </nav>
    <dialog ref={menu} className="atlas-menu" aria-label="FireLens menu" onClick={(event) => { if (event.target === menu.current) menu.current?.close(); }}>
      <div className="atlas-menu__heading"><strong>FireLens</strong><button type="button" aria-label="Close menu" onClick={() => menu.current?.close()}><X size={20} /></button></div>
      <nav aria-label="More navigation">
        <button type="button" onClick={() => act(onHome)}>Home</button>
        <button type="button" onClick={() => act(onMap)}>Explore B.C. records</button>
        <button type="button" onClick={() => act(onPrepare)}>Preparedness</button>
        <button type="button" onClick={() => act(onExamples)}>Example questions</button>
        <button type="button" onClick={() => act(onLocation)}>Use approximate location</button>
        <button type="button" onClick={() => act(onAbout)}>About & methodology</button>
        <a href="https://wildfiresituation.nrs.gov.bc.ca/map" target="_blank" rel="noreferrer">Official BCWS map</a>
      </nav>
      {recentQuestions.length > 0 && <section aria-label="Recent questions"><h2>Recent questions</h2>{recentQuestions.map((question) => <button key={question.text} type="button" onClick={() => act(() => onRecent(question.text))}>{question.text}</button>)}</section>}
      <p>Independent beta · For emergencies call 9-1-1.</p>
    </dialog>
  </header>;
}
