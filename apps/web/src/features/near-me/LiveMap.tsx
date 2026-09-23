import { useMemo, useState } from "react";
import { MapContainer } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import "./liveMap.css";
import type { LiveResult } from "../../shared/api/api";
import { ClusteredPointMarkers } from "./ClusteredPointMarkers";
import { MatchingRecordList, ProvinceRecordList } from "./LiveRecordLists";
import { MapContextLayers } from "./MapContextLayers";
import { LiveMapCoverage } from "./LiveMapCoverage";
import { HistoricalMapRecords, MapRefreshStatus, type MapSnapshotStatus, mapSnapshotAge } from "./MapRefreshStatus";
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
  partialLayers = [],
  geometryOmissions = [],
  focus,
  focusResults = EMPTY_RESULTS,
  selectedResultId,
  onSelectResult,
  onAskAboutResult,
  contextLayersEnabled = false,
  onContextLayersChange,
  variant = "full",
  heading,
  contextLabel,
  onExpand,
  loading = false,
  loadError,
  snapshotStatus,
  historicalResults = EMPTY_RESULTS,
  scopeKey,
}: {
  results: LiveResult[];
  matchingResults?: LiveResult[] | undefined;
  provinceResults?: LiveResult[] | undefined;
  aggregateFreshness?: "fresh" | "stale" | "mixed" | undefined;
  unavailableLayers?: string[] | undefined;
  partialLayers?: string[] | undefined;
  geometryOmissions?: { kind: string; count: number }[] | undefined;
  focus?: MapFocus | undefined;
  focusResults?: LiveResult[] | undefined;
  selectedResultId?: string | undefined;
  onSelectResult?: ((resultId: string) => void) | undefined;
  onAskAboutResult?: ((resultId: string, question: string) => void) | undefined;
  contextLayersEnabled?: boolean | undefined;
  onContextLayersChange?: ((enabled: boolean) => void) | undefined;
  variant?: "compact" | "full";
  heading?: string | undefined;
  contextLabel?: string | undefined;
  onExpand?: (() => void) | undefined;
  loading?: boolean;
  loadError?: string | undefined;
  snapshotStatus?: MapSnapshotStatus | undefined;
  historicalResults?: LiveResult[] | undefined;
  scopeKey?: string | undefined;
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
  const hasMatchingResults = answerMatchingResults.length > 0;
  const [tilesFailed, setTilesFailed] = useState(false);
  const compact = variant === "compact";
  const answerSnapshot = snapshotStatus?.mode === "answer";
  const snapshotAged = snapshotStatus && (mapSnapshotAge(snapshotStatus, results).overdue || Boolean(snapshotStatus.error));
  const Heading = compact ? "h2" : "h1";
  const records = (
    <>
      <MatchingRecordList
        results={displayedMatchingResults}
        selectedResultId={selectedResultId}
        onSelectResult={onSelectResult}
      />
      <ProvinceRecordList
        results={displayedProvinceResults}
        hasMatchingResults={hasMatchingResults}
        selectedResultId={selectedResultId}
        onSelectResult={onSelectResult}
      />
    </>
  );
  return (
    <section
      className={compact ? "live-map live-map--compact" : "live-map"}
      id="official-map"
      aria-label="Official wildfire records map"
      tabIndex={-1}
    >
      <div className="live-map__heading">
        <div>
          <span>
            {answerSnapshot ? "Answer snapshot" : snapshotAged ? "Previously retrieved official records" : freshnessState === "stale"
              ? "Cached official records"
              : freshnessState === "mixed"
                ? "Official records, some out of date"
                : freshnessState === "fresh"
                  ? "Current official records"
                  : "Official wildfire map"}
          </span>
          <Heading>
            {heading ?? (answerSnapshot ? "Records from this answer" : snapshotAged ? "Official wildfire records in B.C." : freshnessState === "stale"
              ? "Wildfires in B.C. (cached records)"
              : freshnessState === "mixed"
                ? "Wildfires in B.C. (some records out of date)"
                : freshnessState === "fresh"
                  ? "Wildfires in B.C. right now"
                  : "Wildfires across British Columbia")}
          </Heading>
          {contextLabel && <p className="live-map__location">{contextLabel}</p>}
        </div>
        {compact && onExpand ? (
          <button type="button" className="live-map__expand" onClick={onExpand}>
            Expand map
          </button>
        ) : !compact && (
        <a href="https://wildfiresituation.nrs.gov.bc.ca/map" target="_blank" rel="noreferrer">
          Open the BC Wildfire Service map
        </a>
        )}
      </div>
      {!compact && onContextLayersChange && (
        <MapContextLayers enabled={contextLayersEnabled} onChange={onContextLayersChange} />
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
        compact={compact}
      />
      <LiveMapCoverage results={results} displayedResults={filteredResults}
        matchingCount={answerMatchingResults.length} displayedMatchingCount={displayedMatchingResults.length}
        freshnessState={freshnessState} loading={loading} loadError={loadError}
        unavailableLayers={unavailableLayers} partialLayers={partialLayers} geometryOmissions={geometryOmissions} />
      <MapRefreshStatus status={snapshotStatus} results={results} />
      <HistoricalMapRecords results={historicalResults} selectedId={selectedResultId} onSelect={onSelectResult} />
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
          scopeKey={scopeKey}
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
        <>
        {filteredResults.length > 0 && (
          <details className="live-map__records" open={tilesFailed || undefined}>
            <summary>View displayed records ({filteredResults.length})</summary>
            {records}
          </details>
        )}
        <div className="live-map__compact-actions">
          <a href="https://wildfiresituation.nrs.gov.bc.ca/map" target="_blank" rel="noreferrer">
            Open official BCWS map
          </a>
          <span>OSM · Open Government Licence – BC</span>
        </div>
        <p className="live-map__safety-note">Follow the issuing authority. This map is not a safety determination.</p>
        </>
      ) : (
        <>
      {records}
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
      <p className="live-map__note">Follow instructions from the issuing authority. The map is not a safety determination.</p>
        </>
      )}
    </section>
  );
}
