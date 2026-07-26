import { useState } from "react";
import {
  ArrowSquareOut,
  CalendarBlank,
  CaretDown,
  CaretUp,
  Check,
  CheckSquare,
  Info,
  PaperPlaneTilt,
  Shield,
  UserCircle,
} from "@phosphor-icons/react";
import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource/newsreader/500.css";
import "@fontsource/newsreader/600.css";
import "./styles.css";

const CLAIMS = [
  {
    text: "Start closest to the home, then work outward through the Home Ignition Zones.",
    title: "Start closest to the home, then work outward through the Home Ignition Zones.",
    sourceTitle: "FireSmart BC Begins at Home Guide",
    sourcePage: "Page 8",
    sectionOne: "Start with the first 1.5 metres",
    paragraphOne: "Embers and small flames can ignite materials close to your home. Start by creating a non-combustible area extending at least 1.5 metres out from all sides of your home.",
    sectionTwo: "Work outward through the three Home Ignition Zones",
    highlightOne: "Complete the activities in Zone 1 first—this is the area closest to your home.",
    highlightTwo: "Then move to Zone 2 and then Zone 3.",
    conclusion: "Working from your home outward reduces the chance that fire can ignite your home and gives you the greatest impact for your effort.",
    support: "This passage explicitly directs you to start in Zone 1 (closest to the home) and then move outward to Zones 2 and 3, matching the claim’s instruction.",
  },
  {
    text: "Remove or reduce flammable vegetation and items that can ignite near your home (e.g., woodpiles, dry debris).",
    title: "Remove or reduce flammable vegetation and items that can ignite near your home.",
    sourceTitle: "FireSmart BC Begins at Home Guide",
    sourcePage: "Page 12",
    sectionOne: "Remove nearby combustible material",
    paragraphOne: "Regularly clear leaves, needles and other combustible debris from decks, balconies, gutters and the area immediately around the home.",
    sectionTwo: "Move stored materials away",
    highlightOne: "Move firewood and other combustible storage at least 10 metres from the home when possible.",
    highlightTwo: "Keep the area beneath decks clean and clear.",
    conclusion: "Routine maintenance reduces the places where embers can collect and ignite materials beside a structure.",
    support: "The guide directly identifies vegetation, debris and wood storage as preventable ignition hazards near the home.",
  },
  {
    text: "Maintain your home and roof, and keep gutters and vents clear of debris.",
    title: "Maintain your home and roof, and keep gutters and vents clear of debris.",
    sourceTitle: "FireSmart BC Information Guide",
    sourcePage: "Page 5",
    sectionOne: "Maintain the structure",
    paragraphOne: "Inspect the roof, exterior walls and attached structures, repairing gaps or damaged materials that may admit embers.",
    sectionTwo: "Keep roofs, gutters and vents clear",
    highlightOne: "Remove leaves and needles from roofs and gutters on a regular schedule.",
    highlightTwo: "Use corrosion-resistant metal screening on vents.",
    conclusion: "These measures help limit ember entry and ignition on or inside the home.",
    support: "The source links routine roof, gutter and vent maintenance to reducing ember exposure at the structure.",
  },
];

function ClaimButton({ claim, index, selected, onSelect }) {
  return (
    <button className={`claim-card ${selected ? "claim-card--selected" : ""}`} type="button" onClick={onSelect} aria-pressed={selected}>
      <span className="claim-number">{index + 1}</span>
      <span>{claim.text}</span>
      <span className="claim-check">{selected && <Check size={15} weight="bold" />}</span>
    </button>
  );
}

function SourcePanel({ claim, open, onToggle }) {
  return (
    <article className="source-panel">
      <div className="source-panel__head">
        <button type="button" className="source-toggle" onClick={onToggle} aria-expanded={open}>
          <span className="source-number">1</span>
          <span className="source-name"><strong>{claim.sourceTitle}</strong><small>{claim.sourcePage}</small></span>
        </button>
        <span className="stable-chip">Stable guidance</span>
        <a href="https://firesmartbc.ca/resource-types/guides-manuals/" target="_blank" rel="noreferrer">View source <ArrowSquareOut size={15} /></a>
        <button type="button" className="caret-button" onClick={onToggle} aria-label={open ? "Collapse source" : "Expand source"}>{open ? <CaretUp /> : <CaretDown />}</button>
      </div>
      {open && (
        <div className="source-panel__body">
          <aside className="source-details">
            <dl>
              <div><dt>Publisher</dt><dd>FireSmart BC</dd></div>
              <div><dt>Document</dt><dd>{claim.sourceTitle}</dd></div>
              <div><dt>Page</dt><dd>{claim.sourcePage.replace("Page ", "")}</dd></div>
              <div><dt>Guidance type</dt><dd>Stable preparedness guidance</dd></div>
              <div><dt>Last reviewed</dt><dd>April 1, 2025</dd></div>
            </dl>
            <div className="canonical"><strong>Canonical source</strong><a href="https://firesmartbc.ca/resource-types/guides-manuals/" target="_blank" rel="noreferrer">firesmartbc.ca/be-bc-guides <ArrowSquareOut size={13} /></a></div>
          </aside>
          <div className="passage">
            <h3>{claim.sectionOne}</h3>
            <p>{claim.paragraphOne}</p>
            <h3>{claim.sectionTwo}</h3>
            <p><mark>{claim.highlightOne}</mark></p>
            <p><mark>{claim.highlightTwo}</mark></p>
            <p>{claim.conclusion}</p>
            <div className="support-box">
              <span className="support-icon"><Shield size={20} weight="duotone" /></span>
              <div><h4>Why this supports the answer</h4><p>{claim.support}</p></div>
            </div>
          </div>
        </div>
      )}
    </article>
  );
}

export function App() {
  const [selected, setSelected] = useState(0);
  const [openPrimary, setOpenPrimary] = useState(true);
  const [openSecondary, setOpenSecondary] = useState(false);
  const [query, setQuery] = useState("");
  const [question, setQuestion] = useState("How can I reduce wildfire risk around my home?");
  const [notice, setNotice] = useState(false);
  const claim = CLAIMS[selected];

  function submit(event) {
    event.preventDefault();
    if (!query.trim()) return;
    setQuestion(query.trim());
    setQuery("");
    setNotice(true);
  }

  return (
    <div className="app-shell" id="top">
      <header className="topbar">
        <a className="brand" href="#top"><img src="/assets/firelens-mark.png" alt="" /><span><strong>FireLens</strong> BC</span></a>
        <a className="official-link" href="https://www.emergencyinfobc.gov.bc.ca/" target="_blank" rel="noreferrer"><ArrowSquareOut size={18} /> Official current information</a>
      </header>
      <div className="boundary"><Shield size={17} /><span>Official preparedness guidance — not current incident or evacuation status.</span></div>

      <main className="workspace">
        <section className="conversation-panel" aria-label="Question and answer">
          <div className="conversation-scroll">
            <div className="question-block">
              <span className="panel-label">Your question</span>
              <div className="question-line">
                <div className="question-bubble"><p>{question}</p><small>10:42 AM</small></div>
                <UserCircle size={38} weight="fill" />
              </div>
            </div>

            <div className="assistant-message">
              <img src="/assets/firelens-mark.png" alt="" />
              <div><span className="assistant-name">FireLens BC</span><p>Focus on reducing things that can ignite or carry fire to your home. Start with the area closest to your home, then work outward. Keep vegetation managed, maintain your home and roof, and look for guidance on common hazards.</p><small>10:42 AM</small></div>
            </div>

            <div className="claim-group">
              <span className="panel-label">Cited claims in this answer</span>
              <div className="claim-list">{CLAIMS.map((item, index) => <ClaimButton key={item.text} claim={item} index={index} selected={selected === index} onSelect={() => { setSelected(index); setOpenPrimary(true); }} />)}</div>
            </div>
          </div>
          <form className="composer" onSubmit={submit}>
            {notice && <span className="composer-notice">Prototype question updated</span>}
            <div className="composer-input"><input aria-label="Ask another preparedness question" value={query} onChange={(event) => { setQuery(event.target.value); setNotice(false); }} placeholder="Ask another preparedness question..." /><button type="submit" disabled={!query.trim()} aria-label="Send question"><PaperPlaneTilt size={20} weight="fill" /></button></div>
            <p><Info size={16} /> For property-specific risk assessments or current fire conditions, consult the appropriate official service.</p>
          </form>
        </section>

        <section className="evidence-panel" aria-label="Selected claim evidence">
          <div className="evidence-inner">
            <span className="selected-kicker">Selected claim {selected + 1}</span>
            <h1>{claim.title}</h1>
            <div className="answer-claim"><Shield size={18} /><strong>Answer claim</strong><span>{claim.text}</span></div>
            <SourcePanel claim={claim} open={openPrimary} onToggle={() => setOpenPrimary(!openPrimary)} />
            <article className="secondary-source">
              <button type="button" className="source-toggle" onClick={() => setOpenSecondary(!openSecondary)} aria-expanded={openSecondary}><span className="source-number">2</span><span className="source-name"><strong>FireSmart BC Information Guide</strong><small>Page 5</small></span></button>
              <span className="stable-chip">Stable guidance</span>
              <a href="https://firesmartbc.ca/resource-types/guides-manuals/" target="_blank" rel="noreferrer">View source <ArrowSquareOut size={15} /></a>
              <button type="button" className="caret-button" onClick={() => setOpenSecondary(!openSecondary)} aria-label={openSecondary ? "Collapse source 2" : "Expand source 2"}>{openSecondary ? <CaretUp /> : <CaretDown />}</button>
              {openSecondary && <p className="secondary-copy">Supporting guidance restates the Home Ignition Zone sequence and recommends beginning with the structure before moving outward.</p>}
            </article>
            <div className="access-date"><CalendarBlank size={17} weight="fill" /> All sources accessed July 25, 2026.</div>
          </div>
        </section>
      </main>
    </div>
  );
}
