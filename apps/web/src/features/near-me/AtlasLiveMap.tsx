import { AnswerMapScope, answerMapScope } from "./AnswerMapScope";
import { useMemo, useState, type ReactNode } from "react";
import { MapContainer, ZoomControl } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import "./liveMap.css";
import type { FireLensSession } from "../ask/useFireLensSession";
import { ClusteredPointMarkers } from "./ClusteredPointMarkers";
import { MatchingRecordList, ProvinceRecordList } from "./LiveRecordLists";
import { LiveMapCoverage } from "./LiveMapCoverage";
import { MapLayerFilters, filterMapResults, incidentStatuses, type IncidentStatusMode } from "./MapLayerFilters";
import { BC_BOUNDS, FitResults } from "./MapViewport";
import { OfficialBasemap, TileFailureWarning } from "./OfficialBasemap";
import { StaticGeometry } from "./StaticGeometry";
import { isRenderableGeometry } from "./liveResultPresentation";
import { HistoricalMapRecords, MapRefreshStatus } from "./MapRefreshStatus";

/** Geographic presentation of the session's existing official map response. */
export default function AtlasLiveMap({ session, visible = true, statusSlot }: { session: FireLensSession; visible?: boolean; statusSlot?: ReactNode }) {
  const [hiddenKinds, setHiddenKinds] = useState<Set<"incident" | "perimeter" | "evacuation">>(new Set());
  const [statuses, setStatuses] = useState<Set<string>>(new Set());
  const [statusMode, setStatusMode] = useState<IncidentStatusMode>("all");
  const [tilesFailed, setTilesFailed] = useState(false);
  const filtered = useMemo(() => filterMapResults(session.mapResults, hiddenKinds, statusMode, statuses), [session.mapResults, hiddenKinds, statusMode, statuses]);
  const matches = useMemo(() => new Set(session.mapMatchingResults.map((r) => r.result_id)), [session.mapMatchingResults]);
  const matching = filtered.filter((r) => matches.has(r.result_id));
  const province = filtered.filter((r) => !matches.has(r.result_id));
  const answerRecords = session.response?.live_results ?? [];
  const retainedLookup = answerMapScope(answerRecords, session.mapMatchingResults, filtered).retained;
  const points = filtered.filter((r) => isRenderableGeometry(r) && r.geometry?.type === "Point");
  const areas = filtered.filter((r) => isRenderableGeometry(r) && r.geometry?.type !== "Point");
  return <section className="atlas-live-map live-map" id="official-map" aria-label="Official wildfire records map" tabIndex={-1}>
    <div className="atlas-live-canvas" role="region" aria-label="Interactive map of official wildfire records">
      <MapContainer bounds={BC_BOUNDS} zoomControl={false} scrollWheelZoom={false} zoomAnimation={false} keyboard>
        <OfficialBasemap focus={session.mapFocus} onTileError={() => setTilesFailed(true)} />
        <FitResults active={visible} results={filtered} focus={session.mapFocus} focusResults={session.mapFocusResults} selectedResultId={session.selectedLiveResultId} scopeKey={session.mapScopeKey} />
        {areas.map((result) => <StaticGeometry key={result.result_id} result={result} matching={matches.has(result.result_id)} selected={session.selectedLiveResultId === result.result_id} onSelectResult={session.setSelectedLiveResultId} onAskAboutResult={session.askAboutResult} />)}
        <ClusteredPointMarkers results={points} matchingResultIds={matches} selectedResultId={session.selectedLiveResultId} onSelectResult={session.setSelectedLiveResultId} onAskAboutResult={session.askAboutResult} />
        <ZoomControl position="bottomright" />
      </MapContainer>
    </div>
    <div className="atlas-live-tools">
      <h2 className="response-announcement" data-surface-visually-hidden="true">Official wildfire records</h2>
      {session.activeLocation?.label && <p>Supplied location: {session.activeLocation.label} · {session.activeLocation.radius_km ?? 50} km radius</p>}
      {session.mapFocus && <details className="atlas-map-location"><summary>Location details</summary><p>Approximate place marker near {session.mapFocus.latitude.toFixed(2)}, {session.mapFocus.longitude.toFixed(2)}</p></details>}
      <MapLayerFilters compact hiddenKinds={hiddenKinds} availableStatuses={incidentStatuses(session.mapResults)} statuses={statuses} statusMode={statusMode}
        onToggleKind={(kind) => setHiddenKinds((old) => { const next = new Set(old); if (next.has(kind)) next.delete(kind); else next.add(kind); return next; })}
        onToggleStatus={(status) => { setStatusMode("selected"); setStatuses((old) => { if (statusMode === "all") return new Set([status]); const next = new Set(old); if (next.has(status)) next.delete(status); else next.add(status); return next; }); }}
        onShowAllStatuses={() => { setStatusMode("all"); setStatuses(new Set()); }} />
    </div>
    {visible && <div className="atlas-live-status">
      {statusSlot}
      <TileFailureWarning failed={tilesFailed} />
      <LiveMapCoverage condensed results={session.mapResults} displayedResults={filtered} matchingCount={session.mapMatchingResults.length} displayedMatchingCount={matching.length}
        freshnessState={session.mapAggregateFreshness} loading={!session.mapLoaded && !session.mapMessage} loadError={session.mapMessage}
        partialLayers={session.mapPartialLayers} unavailableLayers={session.mapUnavailableLayers} geometryOmissions={session.mapGeometryOmissions ?? []} />
      <AnswerMapScope answer={answerRecords} lookup={session.mapMatchingResults} displayed={filtered} />
      <MapRefreshStatus status={session.mapSnapshotStatus} results={session.mapResults} />
      <HistoricalMapRecords results={session.mapHistoricalResults ?? []} selectedId={session.selectedLiveResultId} onSelect={session.setSelectedLiveResultId} />
      <details className="atlas-live-records" open={tilesFailed || undefined}>
        <summary>View displayed records ({filtered.length})</summary>
        <MatchingRecordList label={retainedLookup ? "Records retained from the lookup" : "Matching this question"} results={matching} selectedResultId={session.selectedLiveResultId} onSelectResult={session.setSelectedLiveResultId} />
        <ProvinceRecordList results={province} hasMatchingResults={matching.length > 0} selectedResultId={session.selectedLiveResultId} onSelectResult={session.setSelectedLiveResultId} />
        <p>Follow local authorities. Missing records are not an all-clear.</p>
        <a href="https://wildfiresituation.nrs.gov.bc.ca/map" target="_blank" rel="noreferrer">Open official BCWS map</a>
      </details>
      <details className="official-sources-details">
        <summary>Map sources and privacy</summary>
        <p>Street context uses OpenStreetMap tiles. The B.C. outline is the locally bundled <a href="https://catalogue.data.gov.bc.ca/dataset/province-of-british-columbia-legally-defined-administrative-areas-of-bc" target="_blank" rel="noreferrer">Government of BC provincial boundary</a> under the <a href="https://www2.gov.bc.ca/gov/content/data/open-data/open-government-licence-bc" target="_blank" rel="noreferrer">Open Government Licence – BC</a>.</p>
        <p>Tile requests go directly to OpenStreetMap and reveal the map area being viewed. The referrer contains only the site origin, without your question or page path. Use the official BCWS map for operational context.</p>
      </details>
    </div>}
  </section>;
}
