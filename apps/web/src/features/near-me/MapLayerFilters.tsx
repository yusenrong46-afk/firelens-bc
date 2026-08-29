import type { LiveResult } from "../../shared/api/api";

const LAYERS: { id: LiveResult["kind"]; label: string }[] = [
  { id: "incident", label: "Fires" },
  { id: "evacuation", label: "Evacuations" },
  { id: "perimeter", label: "Perimeters" },
];

export type IncidentStatusMode = "all" | "selected";

export function incidentStatuses(results: LiveResult[]): string[] {
  return [...new Set(
    results
      .filter((result) => result.kind === "incident")
      .map((result) => result.status?.trim())
      .filter((status): status is string => Boolean(status)),
  )].sort((left, right) => left.localeCompare(right));
}

export function MapLayerFilters({
  hiddenKinds,
  availableStatuses,
  onToggleKind,
  onShowAllStatuses,
  onToggleStatus,
  statusMode,
  statuses,
}: {
  hiddenKinds: Set<LiveResult["kind"]>;
  availableStatuses: string[];
  onToggleKind: (kind: LiveResult["kind"]) => void;
  onShowAllStatuses: () => void;
  onToggleStatus: (status: string) => void;
  statusMode: IncidentStatusMode;
  statuses: Set<string>;
}) {
  return (
    <div className="live-map__filters" aria-label="Filter official map records">
      <div className="live-map__filter-row" role="group" aria-label="Layers">
        {LAYERS.map((layer) => (
          <button
            type="button"
            key={layer.id}
            aria-pressed={!hiddenKinds.has(layer.id)}
            onClick={() => onToggleKind(layer.id)}
          >
            {layer.label}
          </button>
        ))}
      </div>
      {availableStatuses.length > 0 && (
      <div className="live-map__filter-row" role="group" aria-label="Incident status">
        <button
          type="button"
          aria-pressed={statusMode === "all"}
          onClick={onShowAllStatuses}
        >
          All statuses
        </button>
        {availableStatuses.map((status) => (
          <button
            type="button"
            key={status}
            aria-pressed={statusMode === "selected" && statuses.has(status)}
            onClick={() => onToggleStatus(status)}
          >
            {status}
          </button>
        ))}
      </div>
      )}
    </div>
  );
}

export function filterMapResults(
  results: LiveResult[],
  hiddenKinds: Set<LiveResult["kind"]>,
  statusMode: IncidentStatusMode,
  statuses: Set<string>,
): LiveResult[] {
  return results.filter((result) => {
    if (hiddenKinds.has(result.kind)) return false;
    if (result.kind !== "incident" || statusMode === "all") return true;
    return statuses.has(result.status?.trim() ?? "");
  });
}
