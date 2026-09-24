import type { AskResponse } from "../shared/api/api";

export type ContextChip = {
  id: string;
  label: string;
};

/**
 * Noninteractive context chips backed only by typed session/response state.
 * Never parse chips from generated prose when typed fields exist.
 */
export function deriveContextChips({
  response,
  locationLabel,
  activeRadiusKm,
}: {
  response: AskResponse | undefined;
  locationLabel?: string | undefined;
  activeRadiusKm?: number | undefined;
}): ContextChip[] {
  if (!response) return [];
  const mode = response.response_mode;
  if (mode === "background" || mode === "capability" || mode === "abstention") return [];

  const chips: ContextChip[] = [];
  const hasLive = (response.live_results?.length ?? 0) > 0
    || mode === "live"
    || mode === "mixed";
  if (!hasLive) return [];

  const kinds = new Set((response.live_results ?? []).map((record) => record.kind));
  const label = kinds.size === 1 && kinds.has("evacuation") ? "Evacuation records"
    : kinds.size > 0 && !kinds.has("evacuation") ? "Wildfire records"
    : "Official records";
  chips.push({ id: "scope-current", label });

  const radius = activeRadiusKm;
  if (typeof radius === "number" && Number.isFinite(radius)) {
    chips.push({ id: "radius", label: `Within ${Math.round(radius)} km` });
  }

  const place = locationLabel?.trim() || undefined;
  if (place) {
    chips.push({ id: "place", label: place });
  }

  return chips;
}

export function ContextChips({ chips }: { chips: ContextChip[] }) {
  if (chips.length === 0) return null;
  return (
    <ul className="context-chips" aria-label="Active question context">
      {chips.map((chip) => (
        <li key={chip.id}>
          <span className="context-chip">{chip.label}</span>
        </li>
      ))}
    </ul>
  );
}
