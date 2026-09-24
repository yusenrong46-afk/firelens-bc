import { ArrowRight, Backpack, Crosshair, MapPin, MapTrifold } from "@phosphor-icons/react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { NEARBY_QUESTION } from "../features/ask/AskStartPanel";
import type { FireLensSession } from "../features/ask/useFireLensSession";
import { LiveDataStatus } from "./LiveDataStatus";

export function AtlasHome({ session, composer, onMap, onPrepare, onExamples }: {
  session: FireLensSession; composer: ReactNode;
  onMap: () => void; onPrepare: () => void; onExamples: () => void;
}) {
  const [nearbyOpen, setNearbyOpen] = useState(false);
  const community = useRef<HTMLInputElement>(null);
  useEffect(() => { if (session.locationMessage) setNearbyOpen(true); }, [session.locationMessage]);
  return <main className="atlas-home" id="conversation" aria-label="Find wildfire information">
    <div className="atlas-home__intro">
      <p className="atlas-home__eyebrow">Wildfire information for British Columbia</p>
      <h1>Know what’s happening.<br />Know where it came from.</h1>
      <p className="atlas-home__description">Official records and source-backed answers, in one place.</p>
    </div>
    <div className="atlas-home__composer">{composer}</div>
    <div className="atlas-home__tasks" aria-label="Choose a task">
      <button type="button" aria-expanded={nearbyOpen} aria-controls="home-nearby" onClick={() => { setNearbyOpen(!nearbyOpen); if (!nearbyOpen) requestAnimationFrame(() => community.current?.focus()); }}><MapPin size={22} /><span>Near me</span><ArrowRight size={18} /></button>
      <button type="button" onClick={onMap}><MapTrifold size={22} /><span>Explore map</span><ArrowRight size={18} /></button>
      <button type="button" onClick={onPrepare}><Backpack size={22} /><span>Preparedness</span><ArrowRight size={18} /></button>
    </div>
    {nearbyOpen && <section className="atlas-home__nearby" id="home-nearby" aria-label="Nearby official records">
      <form onSubmit={event => { event.preventDefault(); if (session.locationLabel.trim()) void session.submitQuestion(NEARBY_QUESTION.replaceAll("{place}", session.locationLabel.trim())); }}>
        <label htmlFor="home-community">Your B.C. community <span>· 50 km radius</span></label>
        <div><input id="home-community" ref={community} aria-label="BC community for a nearby lookup" placeholder="For example, Kelowna" value={session.locationLabel} onChange={event => { session.setLocationLabel(event.target.value); session.clearManualLocation(); }} maxLength={120} /><button type="submit" disabled={!session.locationLabel.trim()}>Check my area <ArrowRight size={18} /></button></div>
      </form>
      <button className="atlas-home__location" type="button" onClick={() => session.useApproximateLocation(NEARBY_QUESTION.replaceAll("{place}", "this location"))}><Crosshair size={18} />Use approximate location</button>
    </section>}
    {session.locationMessage && <p className="atlas-location-message" role="status">{session.locationMessage}</p>}
    <button className="atlas-home__examples" type="button" onClick={onExamples}>Explore example questions <ArrowRight size={17} /></button>
    <div className="atlas-home__status"><LiveDataStatus liveSummary={session.liveSummary} readiness={session.readiness} now={session.statusNow} />{session.readiness === "not_ready" && <p>AI answers are unavailable. You can still explore official records.</p>}</div>
    <footer className="pc-disclaimer">Independent beta. Follow local authorities. For emergencies call 9-1-1.</footer>
  </main>;
}
