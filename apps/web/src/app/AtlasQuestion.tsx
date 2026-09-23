import { Crosshair, X } from "@phosphor-icons/react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { AskStartPanel, NEARBY_QUESTION } from "../features/ask/AskStartPanel";
import type { FireLensSession } from "../features/ask/useFireLensSession";

export function AtlasQuestion({ session, composer, open, examplesRequested, onClose, onPrepare, onMap }: {
  session: FireLensSession; composer: ReactNode; open: boolean; examplesRequested: boolean;
  onClose: () => void; onPrepare: (question: string) => void; onMap: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [nearbyOpen, setNearbyOpen] = useState(false);
  const nearbyVisible = nearbyOpen || Boolean(session.locationMessage);
  const community = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (!open) { if (dialog.current?.open) dialog.current.close(); return; }
    dialog.current?.showModal();
    if (examplesRequested) {
      const trigger = dialog.current?.querySelector<HTMLButtonElement>(".guided-questions__trigger");
      if (trigger?.getAttribute("aria-expanded") === "false") trigger.click();
    } else {
      dialog.current?.querySelector<HTMLInputElement>('input[aria-label="Ask FireLens a question"]')?.focus();
    }
  }, [open, examplesRequested]);
  return <dialog ref={dialog} className="atlas-question" aria-label="Ask FireLens" onCancel={onClose} onClose={onClose}>
    <div className="atlas-question__heading"><h2>Ask FireLens</h2><button type="button" aria-label="Close question" onClick={onClose}><X size={22} /></button></div>
    {composer}
    <button className="atlas-nearby-trigger" type="button" aria-expanded={nearbyVisible} onClick={() => { setNearbyOpen(!nearbyOpen); if (!nearbyOpen) requestAnimationFrame(() => community.current?.focus()); }}>Near me</button>
    {nearbyVisible && <section className="atlas-home__nearby" aria-label="Nearby official records">
      <form onSubmit={event => { event.preventDefault(); if (session.locationLabel.trim()) void session.submitQuestion(NEARBY_QUESTION.replaceAll("{place}", session.locationLabel.trim())); }}>
        <label htmlFor="ask-community">Your B.C. community <span>· 50 km radius</span></label>
        <div><input id="ask-community" ref={community} aria-label="BC community for a nearby lookup" placeholder="For example, Kelowna" value={session.locationLabel} onChange={event => { session.setLocationLabel(event.target.value); session.clearManualLocation(); }} maxLength={120} /><button type="submit" disabled={!session.locationLabel.trim()}>Check my area</button></div>
      </form>
      <button className="atlas-home__location" type="button" onClick={() => session.useApproximateLocation(NEARBY_QUESTION.replaceAll("{place}", "this location"))}><Crosshair size={18} />Use approximate location</button>
    </section>}
    {session.view.kind === "idle" && session.locationMessage && <p role="status" aria-live="polite">{session.locationMessage}</p>}
    {session.readiness === "not_ready" && <p role="status">AI answers are unavailable. Official records remain available on the map.</p>}
    <AskStartPanel catalogueOnly locationLabel={session.locationLabel} onLocationChange={session.setLocationLabel} onUseApproximateLocation={session.useApproximateLocation} onSelectQuestion={session.submitQuestion} onPrepareQuestion={onPrepare} onOpenMap={onMap} />
  </dialog>;
}
