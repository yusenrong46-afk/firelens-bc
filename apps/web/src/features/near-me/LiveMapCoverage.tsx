import type { LiveResult } from "../../shared/api/api";
import { MapScope } from "./MapScope";

/** Coverage stays explicit when the province request has not returned usable data. */
export function LiveMapCoverage({ results, displayedResults, matchingCount, displayedMatchingCount,
  freshnessState, loading, loadError, unavailableLayers, partialLayers, geometryOmissions, condensed = false,
}: {
  condensed?: boolean;
  results: LiveResult[];
  displayedResults: LiveResult[];
  matchingCount: number;
  displayedMatchingCount: number;
  freshnessState: "fresh" | "stale" | "mixed" | undefined;
  loading: boolean;
  loadError: string | undefined;
  unavailableLayers: string[];
  partialLayers: string[];
  geometryOmissions: { kind: string; count: number }[];
}) {
  const coveragePending = loading || Boolean(loadError);
  const kindCounts = displayedResults.reduce(
    (counts, result) => ({ ...counts, [result.kind]: counts[result.kind] + 1 }),
    { incident: 0, evacuation: 0, perimeter: 0 },
  );
  return <>
      {loadError ? (
        <p className="live-map__warning" role="status">
          Province-wide records are unavailable. {loadError} Missing records are not an all-clear.
        </p>
      ) : loading && (
        <p className="map-surface-status" role="status">
          Loading province-wide records. Coverage and totals are not yet available.
        </p>
      )}
      {freshnessState === "stale" && (
        <p className="live-map__warning" role="status">
          These official observations are stale and do not establish current conditions. Check the supplied source times and limitations.
        </p>
      )}
      {freshnessState === "mixed" && (
        <p className="live-map__warning" role="status">
          These official observations have mixed freshness. Some do not establish current conditions; check each record's source times and limitations.
        </p>
      )}
      {partialLayers.length > 0 && <p className="live-map__warning" role="status">Partial coverage for {partialLayers.join(", ")}: only validated records are shown. Missing records are not an all-clear.</p>}
      {unavailableLayers.length > 0 && (
        <p className="live-map__warning" role="status">
          Some official layers are unavailable: {unavailableLayers.join(", ")}.
          The records below do not represent those missing layers.
        </p>
      )}
      {geometryOmissions.length > 0 && (
        <p className="live-map__warning" role="status">
          Partial coverage: {geometryOmissions.map(({ kind, count }) => `${count} ${kind} records omitted`).join(", ")}
          {" because their boundaries could not be validated. Displayed counts are incomplete. A missing area is not an all-clear. "}
          <a href="https://www.emergencyinfobc.gov.bc.ca/" target="_blank" rel="noreferrer">Check official emergency information</a>.
        </p>
      )}
      {(!condensed || results.length === 0) && !coveragePending && <MapScope
        displayedCount={displayedResults.length}
        displayedMatchingCount={displayedMatchingCount}
        matchingCount={matchingCount}
        resultCount={results.length}
      />}
      {coveragePending ? (
        <div className="live-roster-summary" aria-label="Official record totals">
          <strong>{displayedResults.length > 0
            ? `${displayedResults.length} retained official ${displayedResults.length === 1 ? "record" : "records"} displayed`
            : "Displayed-record totals unavailable"}</strong>
          <span>Province-wide layer coverage {loadError ? "unavailable" : "pending"}.</span>
        </div>
      ) : <div className="live-roster-summary" aria-label="Official record totals">
        <strong>{displayedResults.length} displayed official {displayedResults.length === 1 ? "record" : "records"}</strong>
        <span>{unavailableLayers.includes("incident") ? "Fire records unavailable" : `${kindCounts.incident} fires${(partialLayers.includes("incident") || geometryOmissions.some((item) => item.kind === "incident")) ? " (partial)" : ""}`}</span>
        <span>{unavailableLayers.includes("evacuation") ? "Evacuation records unavailable" : `${kindCounts.evacuation} evacuation areas${(partialLayers.includes("evacuation") || geometryOmissions.some((item) => item.kind === "evacuation")) ? " (partial)" : ""}`}</span>
        <span>{unavailableLayers.includes("perimeter") ? "Perimeter records unavailable" : `${kindCounts.perimeter} perimeters${(partialLayers.includes("perimeter") || geometryOmissions.some((item) => item.kind === "perimeter")) ? " (partial)" : ""}`}</span>
      </div>}
  </>;
}
