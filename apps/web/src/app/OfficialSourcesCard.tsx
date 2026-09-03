import { ArrowSquareOut, Leaf } from "@phosphor-icons/react";
import { EMERGENCY_INFO_BC_URL } from "../shared/officialLinks";

export function OfficialSourcesCard() {
  return (
    <aside className="official-sources-card" aria-label="Official sources">
      <div className="official-sources-card__title">
        <Leaf size={18} aria-hidden="true" />
        <strong>Stay informed with official sources</strong>
      </div>
      <p>Always confirm critical decisions with local authorities and current official updates.</p>
      <a href={EMERGENCY_INFO_BC_URL} target="_blank" rel="noreferrer">
        EmergencyInfoBC <ArrowSquareOut size={14} aria-hidden="true" />
      </a>
    </aside>
  );
}
