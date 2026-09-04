import { ArrowSquareOut } from "@phosphor-icons/react";
import { emitProductEvent } from "../../shared/telemetry";

export function handoffAuthority(title: string): string {
  const lowered = title.toLocaleLowerCase();
  if (lowered.includes("drivebc")) return "DriveBC";
  if (lowered.includes("aqhi") || lowered.includes("air quality")) return "Environment and Climate Change Canada";
  if (lowered.includes("emergencyinfo")) return "EmergencyInfoBC";
  if (lowered.includes("bc wildfire") || lowered.includes("bcws")) return "BC Wildfire Service";
  return "Official authority";
}

export function AuthorityHandoffCards({
  links,
}: {
  links: { title: string; url: string; description?: string }[];
}) {
  if (links.length === 0) return null;
  return (
    <div className="related-service-links authority-handoff-cards" aria-label="Official authority handoffs">
      {links.map((item) => (
        <article key={item.url} className="authority-handoff-card">
          <p className="authority-handoff-card__topic">{item.title}</p>
          <p className="authority-handoff-card__authority">{handoffAuthority(item.title)}</p>
          <p>{item.description}</p>
          <p className="authority-handoff-card__why">FireLens does not track this itself; the official source has the current information.</p>
          <a href={item.url} target="_blank" rel="noreferrer" onClick={() => emitProductEvent("authority_handoff_opened")}>
            <span>Open official source</span>
            <ArrowSquareOut size={18} aria-hidden="true" />
          </a>
        </article>
      ))}
    </div>
  );
}
