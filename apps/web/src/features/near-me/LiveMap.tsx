import { useMemo, useState } from "react";
import { CircleMarker, GeoJSON, MapContainer, Popup } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import type { LiveResult } from "../../shared/api/api";
import { MatchingRecordList, ProvinceRecordList } from "./LiveRecordLists";
import { MapRecordPopup } from "./MapRecordPopup";
import { BC_BOUNDS, FitResults, type MapFocus } from "./MapViewport";
import { OfficialBasemap, TileFailureWarning } from "./OfficialBasemap";
import {
  isRenderableGeometry,
  MAP_GEOMETRY_LEGEND,
  resultColour,
} from "./liveResultPresentation";

export function LiveMap({
  results,
  matchingResults,
  provinceResults,
  aggregateFreshness,
  unavailableLayers = [],
  focus,
  focusResults = [],
  selectedResultId,
  onSelectResult,
  onAskAboutResult,
}: {
  results: LiveResult[];
  matchingResults?: LiveResult[] | undefined;
  provinceResults?: LiveResult[] | undefined;
  aggregateFreshness?: "fresh" | "stale" | "mixed" | undefined;
  unavailableLayers?: string[] | undefined;
  focus?: MapFocus | undefined;
  focusResults?: LiveResult[] | undefined;
  selectedResultId?: string | undefined;
  onSelectResult?: ((resultId: string) => void) | undefined;
  onAskAboutResult?: ((resultId: string, question: string) => void) | undefined;
}) {
  const displayedMatchingResults = matchingResults ?? focusResults;
  const displayedMatchingIds = useMemo(
    () => new Set(displayedMatchingResults.map((result) => result.result_id)),
    [displayedMatchingResults],
  );
  const displayedProvinceResults = useMemo(
    () => provinceResults ?? results.filter((result) => !displayedMatchingIds.has(result.result_id)),
    [displayedMatchingIds, provinceResults, results],
  );
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
  const hasMatchingResults = displayedMatchingResults.length > 0;
  const [tilesFailed, setTilesFailed] = useState(false);
  return (
    <section className="live-map" id="official-map" aria-label="Official wildfire records map" tabIndex={-1}>
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
      {unavailableLayers.length > 0 && (
        <p className="live-map__warning" role="status">
          Some official layers are unavailable: {unavailableLayers.join(", ")}.
          The records below do not represent those missing layers.
        </p>
      )}
      {tilesFailed && <TileFailureWarning failed />}
      <div role="region" aria-label="Interactive map of official wildfire records">
        <MapContainer
          bounds={BC_BOUNDS}
          scrollWheelZoom={false}
          keyboard={false}
          zoomAnimation={false}
          attributionControl={true}
        >
        <OfficialBasemap focus={focus} onTileError={() => setTilesFailed(true)} />
        <FitResults
          results={results}
          focus={focus}
          focusResults={focusResults}
          selectedResultId={selectedResultId}
        />
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
              opacity: displayedMatchingIds.size === 0 || displayedMatchingIds.has(result.result_id) ? 1 : 0.32,
              fillOpacity: result.result_id === selectedResultId
                ? 0.38
                : displayedMatchingIds.size === 0 || displayedMatchingIds.has(result.result_id) ? 0.22 : 0.07,
            }}
            eventHandlers={{ click: () => onSelectResult?.(result.result_id) }}
          >
            <Popup>
              <MapRecordPopup result={result} onAskAboutResult={onAskAboutResult} />
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
                opacity: displayedMatchingIds.size === 0 || displayedMatchingIds.has(result.result_id) ? 1 : 0.35,
                fillOpacity: displayedMatchingIds.size === 0 || displayedMatchingIds.has(result.result_id) ? 1 : 0.25,
              }}
            >
              <Popup>
                <MapRecordPopup result={result} onAskAboutResult={onAskAboutResult} />
              </Popup>
            </CircleMarker>
          );
        })}
        </MapContainer>
      </div>
      <MatchingRecordList
        results={displayedMatchingResults}
        selectedResultId={selectedResultId}
        onSelectResult={onSelectResult}
      />
      {focus && (
        <p className="map-surface-status" role="status">
          Approximate place marker near {focus.latitude.toFixed(2)}, {focus.longitude.toFixed(2)}.
        </p>
      )}
      <p className="live-map__context-note">
        Street context is OpenStreetMap Carto tiles. The BC outline is a locally bundled
        {" "}<a href="https://catalogue.data.gov.bc.ca/dataset/province-of-british-columbia-legally-defined-administrative-areas-of-bc" target="_blank" rel="noreferrer">Government of BC provincial boundary</a>
        {" "}under the <a href="https://www2.gov.bc.ca/gov/content/data/open-data/open-government-licence-bc" target="_blank" rel="noreferrer">Open Government Licence – BC</a>.
        Tile requests go to OpenStreetMap. Use the official BCWS map for operational context.
      </p>
      <div className="live-map__legend" aria-label="Map legend">
        <span>{MAP_GEOMETRY_LEGEND.points}</span>
        <span>{MAP_GEOMETRY_LEGEND.polygons}</span>
      </div>
      {results.length > 0 && (
        <div className="live-roster-summary" aria-label="Official record totals">
          <strong>{results.length} official map records</strong>
          <span>{kindCounts.incident} fires</span>
          <span>{kindCounts.evacuation} evacuation areas</span>
          <span>{kindCounts.perimeter} perimeters</span>
        </div>
      )}
      <ProvinceRecordList
        results={displayedProvinceResults}
        hasMatchingResults={hasMatchingResults}
        selectedResultId={selectedResultId}
        onSelectResult={onSelectResult}
      />
      <p className="live-map__note">Follow instructions from the issuing authority. The map is not a safety determination.</p>
    </section>
  );
}
