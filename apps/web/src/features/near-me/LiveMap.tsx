import { useMemo, useState } from "react";
import { CircleMarker, GeoJSON, MapContainer, Popup } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import type { LiveResult } from "../../shared/api/api";
import { bcBoundaryFeature } from "./bcBoundary";
import { BC_BOUNDS, FitResults, type MapFocus } from "./MapViewport";

function formatTimestamp(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "Timestamp unavailable";
  return new Intl.DateTimeFormat("en-CA", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
  }).format(parsed);
}

const INITIAL_LIST_LIMIT = 12;

function resultColour(kind: LiveResult["kind"]): string {
  if (kind === "evacuation") return "#9b3f26";
  if (kind === "perimeter") return "#c26b2d";
  return "#b42318";
}

function isRenderableGeometry(result: LiveResult): boolean {
  const geometry = result.geometry as { type?: string; coordinates?: unknown };
  if (!Array.isArray(geometry.coordinates) || geometry.coordinates.length === 0) return false;
  return ["Point", "Polygon", "MultiPolygon"].includes(geometry.type ?? "");
}

export function LiveMap({
  results,
  aggregateFreshness,
  unavailableLayers = [],
  focus,
  focusResults = [],
  selectedResultId,
  onSelectResult,
  onAskAboutResult,
}: {
  results: LiveResult[];
  aggregateFreshness?: "fresh" | "stale" | "mixed" | undefined;
  unavailableLayers?: string[] | undefined;
  focus?: MapFocus | undefined;
  focusResults?: LiveResult[] | undefined;
  selectedResultId?: string | undefined;
  onSelectResult?: ((resultId: string) => void) | undefined;
  onAskAboutResult?: ((resultId: string, question: string) => void) | undefined;
}) {
  const [showAllRecords, setShowAllRecords] = useState(false);
  const freshnessState = aggregateFreshness ?? (results.length === 0
    ? undefined
    : results.every((result) => result.freshness === "stale")
      ? "stale"
      : results.some((result) => result.freshness === "stale")
        ? "mixed"
        : "fresh"
  );
  const featureResults = useMemo(
    () => results.filter(
      (result) => isRenderableGeometry(result) && (result.geometry as { type?: string }).type !== "Point",
    ),
    [results],
  );
  const pointResults = useMemo(
    () => results.filter(
      (result) => isRenderableGeometry(result) && (result.geometry as { type?: string }).type === "Point",
    ),
    [results],
  );
  const kindCounts = useMemo(
    () => results.reduce(
      (counts, result) => ({ ...counts, [result.kind]: counts[result.kind] + 1 }),
      { incident: 0, evacuation: 0, perimeter: 0 },
    ),
    [results],
  );
  const listedResults = useMemo(() => {
    if (showAllRecords || results.length <= INITIAL_LIST_LIMIT) return results;
    const initial = results.slice(0, INITIAL_LIST_LIMIT);
    const selected = selectedResultId
      ? results.find((result) => result.result_id === selectedResultId)
      : undefined;
    if (!selected || initial.some((result) => result.result_id === selected.result_id)) return initial;
    return [selected, ...initial.slice(0, INITIAL_LIST_LIMIT - 1)];
  }, [results, selectedResultId, showAllRecords]);
  return (
    <section className="live-map" aria-label="Official wildfire records map">
      <div className="live-map__heading">
        <div>
          <span>
            {freshnessState === "stale"
              ? "Official cached records"
              : freshnessState === "mixed"
                ? "Official records — mixed freshness"
                : freshnessState === "fresh"
                  ? "Official live records"
                  : "Official wildfire map"}
          </span>
          <h1>
            {freshnessState === "stale"
              ? "BC wildfire information — includes stale records"
              : freshnessState === "mixed"
                ? "BC wildfire information — mixed freshness"
                : freshnessState === "fresh"
                  ? "Current BC wildfire information"
                  : "Wildfires across British Columbia"}
          </h1>
        </div>
        <a href="https://wildfiresituation.nrs.gov.bc.ca/map" target="_blank" rel="noreferrer">
          Open BCWS map
        </a>
      </div>
      {freshnessState === "stale" && (
        <p className="live-map__warning" role="status">
          Cached official records; refresh failed. These records may be outdated.
        </p>
      )}
      {freshnessState === "mixed" && (
        <p className="live-map__warning" role="status">
          Official records include stale cached data because a refresh failed. Check each record timestamp.
        </p>
      )}
      <MapContainer
        bounds={BC_BOUNDS}
        scrollWheelZoom={false}
        attributionControl={false}
        aria-label="Interactive map of official wildfire records"
      >
        <GeoJSON
          data={bcBoundaryFeature as unknown as GeoJSON.Feature}
          interactive={false}
          style={{
            className: "live-map__bc-boundary",
            color: "#315f4a",
            weight: 1.5,
            fillColor: "#edf2e8",
            fillOpacity: 0.92,
          }}
        />
        <FitResults results={results} focus={focus} focusResults={focusResults} />
        {featureResults.map((result) => (
          <GeoJSON
            key={result.result_id}
            data={
              { type: "Feature", properties: {}, geometry: result.geometry } as unknown as GeoJSON.Feature
            }
            style={{
              className: "live-map__record-geometry",
              color: resultColour(result.kind),
              weight: result.result_id === selectedResultId ? 4 : 2,
              fillOpacity: result.result_id === selectedResultId ? 0.38 : 0.22,
            }}
            eventHandlers={{ click: () => onSelectResult?.(result.result_id) }}
          >
            <Popup>
              <strong>{result.name}</strong><br />
              {result.status}<br />
              Updated {formatTimestamp(result.source_updated_at)}
              {onAskAboutResult && (
                <div className="map-popup-actions">
                  {result.kind !== "evacuation" && (
                    <button type="button" onClick={() => onAskAboutResult(result.result_id, "How far is this fire from me?")}>How far?</button>
                  )}
                  <button type="button" onClick={() => onAskAboutResult(result.result_id, "What is the current status of this fire?")}>Ask status</button>
                </div>
              )}
            </Popup>
          </GeoJSON>
        ))}
        {pointResults.map((result) => {
          const coordinates = (result.geometry as { coordinates: number[] }).coordinates;
          const longitude = coordinates[0];
          const latitude = coordinates[1];
          if (longitude === undefined || latitude === undefined) return null;
          return (
            <CircleMarker
              key={result.result_id}
              center={[latitude, longitude]}
              radius={7}
              eventHandlers={{ click: () => onSelectResult?.(result.result_id) }}
              pathOptions={{
                className: "live-map__record-geometry",
                color: "#fff",
                weight: result.result_id === selectedResultId ? 4 : 2,
                fillColor: resultColour(result.kind),
                fillOpacity: 1,
              }}
            >
              <Popup>
                <strong>{result.name}</strong><br />
                {result.status}<br />
                Updated {formatTimestamp(result.source_updated_at)}
                {onAskAboutResult && (
                  <div className="map-popup-actions">
                    <button type="button" onClick={() => onAskAboutResult(result.result_id, "How far is this fire from me?")}>How far?</button>
                    <button type="button" onClick={() => onAskAboutResult(result.result_id, "What is the current status of this fire?")}>Ask status</button>
                  </div>
                )}
              </Popup>
            </CircleMarker>
          );
        })}
      </MapContainer>
      {focus && (
        <p className="map-surface-status" role="status">
          Map focused on the requested area near {focus.latitude.toFixed(2)}, {focus.longitude.toFixed(2)}.
        </p>
      )}
      <p className="live-map__context-note">
        Privacy-first map context uses a locally bundled, simplified
        {" "}<a href="https://catalogue.data.gov.bc.ca/dataset/province-of-british-columbia-legally-defined-administrative-areas-of-bc" target="_blank" rel="noreferrer">Government of BC provincial boundary</a>
        {" "}under the <a href="https://www2.gov.bc.ca/gov/content/data/open-data/open-government-licence-bc" target="_blank" rel="noreferrer">Open Government Licence – BC</a>.
        No third-party basemap request is made. Use the official BCWS map for detailed geographic context.
      </p>
      {unavailableLayers.length > 0 && (
        <p className="live-map__warning" role="status">
          Some official layers are unavailable: {unavailableLayers.join(", ")}.
          The records below do not represent those missing layers.
        </p>
      )}
      {results.length > 0 && (
        <div className="live-roster-summary" aria-label="Official record totals">
          <strong>{results.length} official map records</strong>
          <span>{kindCounts.incident} fires</span>
          <span>{kindCounts.evacuation} evacuation areas</span>
          <span>{kindCounts.perimeter} perimeters</span>
        </div>
      )}
      <ul className="live-list">
        {listedResults.map((result) => (
          <li key={result.result_id} className={result.result_id === selectedResultId ? "live-list__selected" : ""}>
            <span className={`live-dot live-dot--${result.kind}`} />
            <button type="button" className="live-list__select" onClick={() => onSelectResult?.(result.result_id)}>
              <strong>{result.name}</strong>
              <small>{result.status} · {result.freshness} · {result.authority}</small>
              <small>Source updated {formatTimestamp(result.source_updated_at)}</small>
              <small>Retrieved {formatTimestamp(result.retrieved_at)}</small>
              {result.distance_km != null && <small>{result.distance_km.toFixed(1)} km · {result.distance_basis?.replaceAll("_", " ")}</small>}
            </button>
            <a href={result.source_url} target="_blank" rel="noreferrer">Source</a>
          </li>
        ))}
      </ul>
      {results.length > INITIAL_LIST_LIMIT && (
        <button
          type="button"
          className="live-list-toggle"
          onClick={() => setShowAllRecords((current) => !current)}
          aria-expanded={showAllRecords}
        >
          {showAllRecords
            ? "Show fewer records"
            : `Show all ${results.length} official records`}
        </button>
      )}
      <p className="live-map__note">No matching record is not a safety determination. Follow instructions from the issuing authority.</p>
    </section>
  );
}
