import { memo, useMemo, useState } from "react";
import { GeoJSON, MapContainer, Popup } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import type { LiveResult } from "../../shared/api/api";
import { ClusteredPointMarkers } from "./ClusteredPointMarkers";
import { MatchingRecordList, ProvinceRecordList } from "./LiveRecordLists";
import { MapScope } from "./MapScope";
import {
  filterMapResults,
  incidentStatuses,
  type IncidentStatusMode,
  MapLayerFilters,
} from "./MapLayerFilters";
import { MapRecordPopup } from "./MapRecordPopup";
import { excludeQuestionMatches, isQuestionMatch } from "./mapClustering";
import { BC_BOUNDS, FitResults, type MapFocus } from "./MapViewport";
import { OfficialBasemap, TileFailureWarning } from "./OfficialBasemap";
import {
  isRenderableGeometry,
  MAP_GEOMETRY_LEGEND,
  resultColour,
} from "./liveResultPresentation";

const EMPTY_RESULTS: LiveResult[] = [];

const StaticGeometry = memo(function StaticGeometry({
  result,
  matching,
  selected,
  onAskAboutResult,
  onSelectResult,
}: {
  result: LiveResult;
  matching: boolean;
  selected: boolean;
  onAskAboutResult?: ((resultId: string, question: string) => void) | undefined;
  onSelectResult?: ((resultId: string) => void) | undefined;
}) {
  const data = useMemo(
    () => ({ type: "Feature", properties: {}, geometry: result.geometry } as unknown as GeoJSON.Feature),
    [result.geometry],
  );
  const style = useMemo(() => ({
    className: "live-map__record-geometry",
    color: resultColour(result.kind),
    weight: selected ? 4 : 2,
    opacity: matching ? 1 : 0.32,
    fillOpacity: selected ? 0.38 : matching ? 0.22 : 0.07,
  }), [matching, result.kind, selected]);
  return (
    <GeoJSON
      data={data}
      style={style}
      eventHandlers={{ click: () => onSelectResult?.(result.result_id) }}
    >
      <Popup autoPan={false}>
        <MapRecordPopup result={result} onAskAboutResult={onAskAboutResult} />
      </Popup>
    </GeoJSON>
  );
});

export function LiveMap({
  results,
  matchingResults,
  provinceResults,
  aggregateFreshness,
  unavailableLayers = [],
  focus,
  focusResults = EMPTY_RESULTS,
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
  const [hiddenKinds, setHiddenKinds] = useState<Set<LiveResult["kind"]>>(new Set());
  const [statusMode, setStatusMode] = useState<IncidentStatusMode>("all");
  const [statuses, setStatuses] = useState<Set<string>>(new Set());
  const availableStatuses = useMemo(() => incidentStatuses(results), [results]);
  const answerMatchingResults = matchingResults ?? focusResults;
  const matchingResultIds = useMemo(
    () => new Set(answerMatchingResults.map((result) => result.result_id)),
    [answerMatchingResults],
  );
  const filteredResults = useMemo(
    () => filterMapResults(results, hiddenKinds, statusMode, statuses),
    [hiddenKinds, results, statusMode, statuses],
  );
  const displayedMatchingResults = useMemo(
    () => filterMapResults(answerMatchingResults, hiddenKinds, statusMode, statuses),
    [answerMatchingResults, hiddenKinds, statusMode, statuses],
  );
  const displayedProvinceResults = useMemo(
    () => filterMapResults(
        excludeQuestionMatches(provinceResults ?? results, matchingResultIds),
        hiddenKinds,
        statusMode,
        statuses,
      ),
    [hiddenKinds, matchingResultIds, provinceResults, results, statusMode, statuses],
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
    () => filteredResults.filter(
      (result) => isRenderableGeometry(result) && (result.geometry as { type?: string }).type !== "Point",
    ),
    [filteredResults],
  );
  const pointResults = useMemo(
    () => filteredResults.filter(
      (result) => isRenderableGeometry(result) && (result.geometry as { type?: string }).type === "Point",
    ),
    [filteredResults],
  );
  const kindCounts = useMemo(
    () => filteredResults.reduce(
      (counts, result) => ({ ...counts, [result.kind]: counts[result.kind] + 1 }),
      { incident: 0, evacuation: 0, perimeter: 0 },
    ),
    [filteredResults],
  );
  const hasMatchingResults = answerMatchingResults.length > 0;
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
      <TileFailureWarning failed={tilesFailed} />
      <MapLayerFilters
        hiddenKinds={hiddenKinds}
        availableStatuses={availableStatuses}
        statuses={statuses}
        onToggleKind={(kind) => {
          setHiddenKinds((current) => {
            const next = new Set(current);
            if (next.has(kind)) next.delete(kind);
            else next.add(kind);
            return next;
          });
        }}
        onToggleStatus={(status) => {
          setStatusMode("selected");
          setStatuses((current) => {
            if (statusMode === "all") return new Set([status]);
            const next = new Set(current);
            if (next.has(status)) next.delete(status);
            else next.add(status);
            return next;
          });
        }}
        onShowAllStatuses={() => {
          setStatusMode("all");
          setStatuses(new Set());
        }}
        statusMode={statusMode}
      />
      <MapScope
        displayedCount={filteredResults.length}
        displayedMatchingCount={displayedMatchingResults.length}
        matchingCount={answerMatchingResults.length}
        resultCount={results.length}
      />
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
          results={filteredResults}
          focus={focus}
          focusResults={focusResults}
          selectedResultId={selectedResultId}
        />
        {featureResults.map((result) => (
          <StaticGeometry
            key={result.result_id}
            result={result}
            matching={isQuestionMatch([result.result_id], matchingResultIds)}
            selected={result.result_id === selectedResultId}
            onSelectResult={onSelectResult}
            onAskAboutResult={onAskAboutResult}
          />
        ))}
        <ClusteredPointMarkers
          results={pointResults}
          matchingResultIds={matchingResultIds}
          selectedResultId={selectedResultId}
          onSelectResult={onSelectResult}
          onAskAboutResult={onAskAboutResult}
        />
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
        Street context is provided by OpenStreetMap Carto tiles. The B.C. outline is a locally bundled
        {" "}<a href="https://catalogue.data.gov.bc.ca/dataset/province-of-british-columbia-legally-defined-administrative-areas-of-bc" target="_blank" rel="noreferrer">Government of BC provincial boundary</a>
        {" "}under the <a href="https://www2.gov.bc.ca/gov/content/data/open-data/open-government-licence-bc" target="_blank" rel="noreferrer">Open Government Licence – BC</a>.
        Tile requests go directly to OpenStreetMap. Use the official BCWS map for operational context.
      </p>
      <div className="live-map__legend" aria-label="Map legend">
        <span>{MAP_GEOMETRY_LEGEND.points}</span>
        <span>{MAP_GEOMETRY_LEGEND.polygons}</span>
      </div>
      {filteredResults.length > 0 && (
        <div className="live-roster-summary" aria-label="Official record totals">
          <strong>{filteredResults.length} official map records</strong>
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
