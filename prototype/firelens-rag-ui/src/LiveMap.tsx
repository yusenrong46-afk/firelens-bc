import { useEffect, useMemo } from "react";
import { CircleMarker, GeoJSON, MapContainer, Popup, TileLayer, useMap } from "react-leaflet";
import type { LatLngBoundsExpression } from "leaflet";
import "leaflet/dist/leaflet.css";
import type { LiveResult } from "./api";

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

const BC_BOUNDS: LatLngBoundsExpression = [
  [48.2, -139.2],
  [60.1, -114.0],
];

function FitResults({ results }: { results: LiveResult[] }) {
  const map = useMap();
  const signature = results.map((result) => result.result_id).join("|");
  useEffect(() => {
    if (results.length === 0) {
      map.fitBounds(BC_BOUNDS, { padding: [12, 12] });
      return;
    }
    const coordinates = results.flatMap((result) => {
      const geometry = result.geometry as { type?: string; coordinates?: unknown };
      if (geometry.type !== "Point" || !Array.isArray(geometry.coordinates)) return [];
      const [longitude, latitude] = geometry.coordinates as number[];
      return Number.isFinite(latitude) && Number.isFinite(longitude)
        ? ([[latitude, longitude]] as [number, number][])
        : [];
    });
    if (coordinates.length > 0) map.fitBounds(coordinates, { padding: [40, 40], maxZoom: 9 });
    else map.fitBounds(BC_BOUNDS, { padding: [12, 12] });
  }, [map, signature, results]);
  return null;
}

function resultColour(kind: LiveResult["kind"]): string {
  if (kind === "evacuation") return "#9b3f26";
  if (kind === "perimeter") return "#c26b2d";
  return "#b42318";
}

export function LiveMap({
  results,
  unavailableLayers = [],
}: {
  results: LiveResult[];
  unavailableLayers?: string[];
}) {
  const featureResults = useMemo(
    () => results.filter((result) => (result.geometry as { type?: string }).type !== "Point"),
    [results],
  );
  const pointResults = useMemo(
    () => results.filter((result) => (result.geometry as { type?: string }).type === "Point"),
    [results],
  );

  return (
    <section className="live-map" aria-label="Official wildfire records map">
      <div className="live-map__heading">
        <div>
          <span>Official live records</span>
          <h1>Current BC wildfire information</h1>
        </div>
        <a href="https://wildfiresituation.nrs.gov.bc.ca/map" target="_blank" rel="noreferrer">
          Open BCWS map
        </a>
      </div>
      <MapContainer bounds={BC_BOUNDS} scrollWheelZoom={false} aria-label="Interactive map of official wildfire records">
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <FitResults results={results} />
        {featureResults.map((result) => (
          <GeoJSON
            key={result.result_id}
            data={
              { type: "Feature", properties: {}, geometry: result.geometry } as unknown as GeoJSON.Feature
            }
            style={{ color: resultColour(result.kind), weight: 2, fillOpacity: 0.22 }}
          >
            <Popup>
              <strong>{result.name}</strong><br />
              {result.status}<br />
              Updated {formatTimestamp(result.source_updated_at)}
            </Popup>
          </GeoJSON>
        ))}
        {pointResults.map((result) => {
          const [longitude, latitude] = (result.geometry as { coordinates: number[] }).coordinates;
          return (
            <CircleMarker
              key={result.result_id}
              center={[latitude, longitude]}
              radius={7}
              pathOptions={{ color: "#fff", weight: 2, fillColor: resultColour(result.kind), fillOpacity: 1 }}
            >
              <Popup>
                <strong>{result.name}</strong><br />
                {result.status}<br />
                Updated {formatTimestamp(result.source_updated_at)}
              </Popup>
            </CircleMarker>
          );
        })}
      </MapContainer>
      {unavailableLayers.length > 0 && (
        <p className="live-map__warning" role="status">
          Some official layers are unavailable: {unavailableLayers.join(", ")}.
          The records below do not represent those missing layers.
        </p>
      )}
      <ul className="live-list">
        {results.slice(0, 8).map((result) => (
          <li key={result.result_id}>
            <span className={`live-dot live-dot--${result.kind}`} />
            <div>
              <strong>{result.name}</strong>
              <small>{result.status} · {result.freshness} · {result.authority}</small>
              <small>Source updated {formatTimestamp(result.source_updated_at)}</small>
              <small>Retrieved {formatTimestamp(result.retrieved_at)}</small>
            </div>
            <a href={result.source_url} target="_blank" rel="noreferrer">Source</a>
          </li>
        ))}
      </ul>
      <p className="live-map__note">No matching record is not a safety determination. Follow instructions from the issuing authority.</p>
    </section>
  );
}
