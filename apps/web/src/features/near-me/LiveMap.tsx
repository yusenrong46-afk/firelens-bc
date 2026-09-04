import { useMemo, useState } from "react";
import { MapContainer } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import type { LiveResult } from "../../shared/api/api";
import { ClusteredPointMarkers } from "./ClusteredPointMarkers";
import { MatchingRecordList, ProvinceRecordList } from "./LiveRecordLists";
import { MapContextLayers } from "./MapContextLayers";
import { MapScope } from "./MapScope";
import {
  filterMapResults,
  incidentStatuses,
  type IncidentStatusMode,
  MapLayerFilters,
} from "./MapLayerFilters";
import { excludeQuestionMatches, isQuestionMatch } from "./mapClustering";
import { BC_BOUNDS, FitResults, type MapFocus } from "./MapViewport";
import { OfficialBasemap, TileFailureWarning } from "./OfficialBasemap";
import { StaticGeometry } from "./StaticGeometry";
import {
  isRenderableGeometry,
  MAP_GEOMETRY_LEGEND,
} from "./liveResultPresentation";

const EMPTY_RESULTS: LiveResult[] = [];

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
  contextLayersEnabled = false,
  onContextLayersChange,
  variant = "full",
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
  contextLayersEnabled?: boolean | undefined;
  onContextLayersChange?: ((enabled: boolean) => void) | undefined;
  variant?: "compact" | "full";
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
  const compact = variant === "compact";
  return (
    <section
      className={compact ? "live-map live-map--compact" : "live-map"}
      id="official-map"
      aria-label="Official wildfire records map"
      tabIndex={-1}
    >
      {!compact && (
      <div className="live-map__heading">
        <div>
          <span>
            {freshnessState === "stale"
              ? "Cached official records"
              : freshnessState === "mixed"
                ? "Official records, some out of date"
                : freshnessState === "fresh"
                  ? "Current official records"
                  : "Official wildfire map"}
          </span>
          <h1>
            {freshnessState === "stale"
              ? "Wildfires in B.C. (cached records)"
              : freshnessState === "mixed"
                ? "Wildfires in B.C. (some records out of date)"
                : freshnessState === "fresh"
                  ? "Wildfires in B.C. right now"
                  : "Wildfires across British Columbia"}
          </h1>
        </div>
        <a href="https://wildfiresituation.nrs.gov.bc.ca/map" target="_blank" rel="noreferrer">
          Open the BC Wildfire Service map
        </a>
      </div>
      )}
      {!compact && onContextLayersChange && (
        <MapContextLayers enabled={contextLayersEnabled} onChange={onContextLayersChange} />
      )}
      {freshnessState === "stale" && (
        <p className="live-map__warning" role="status">
          FireLens could not refresh these records, so it is showing its last cached copy. They may be out of date.
        </p>
      )}
      {freshnessState === "mixed" && (
        <p className="live-map__warning" role="status">
          Some of these records are cached copies because a refresh failed. Check each record's update time.
        </p>
      )}
      {unavailableLayers.length > 0 && (
        <p className="live-map__warning" role="status">
          Some official layers are unavailable: {unavailableLayers.join(", ")}.
          The records below do not represent those missing layers.
        </p>
      )}
      <TileFailureWarning failed={tilesFailed} />
      {!compact && (
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
      )}
      {!compact && (
      <MapScope
        displayedCount={filteredResults.length}
        displayedMatchingCount={displayedMatchingResults.length}
        matchingCount={answerMatchingResults.length}
        resultCount={results.length}
      />
      )}
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
      {compact ? (
        <div className="live-map__compact-actions">
          <a href="https://wildfiresituation.nrs.gov.bc.ca/map" target="_blank" rel="noreferrer">
            Open official BCWS map
          </a>
          <span>OSM · Open Government Licence – BC</span>
        </div>
      ) : (
        <>
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
        </>
      )}
    </section>
  );
}
