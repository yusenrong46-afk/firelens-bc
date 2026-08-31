import { CircleMarker, GeoJSON, TileLayer } from "react-leaflet";
import { bcBoundaryFeature } from "./bcBoundary";
import type { MapFocus } from "./MapViewport";

export const OSM_ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>';

export function TileFailureWarning({ failed }: { failed: boolean }) {
  if (!failed) return null;
  return (
    <p className="live-map__warning" role="status">
      Street-map tiles failed to load. Official records and the B.C. boundary remain available.
    </p>
  );
}

export function OfficialBasemap({
  focus,
  onTileError,
}: {
  focus?: MapFocus | undefined;
  onTileError?: (() => void) | undefined;
}) {
  return (
    <>
      <TileLayer
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        attribution={OSM_ATTRIBUTION}
        {...(onTileError ? { eventHandlers: { tileerror: onTileError } } : {})}
      />
      <GeoJSON
        data={bcBoundaryFeature as never}
        interactive={false}
        style={{
          className: "live-map__bc-boundary",
          color: "#315f4a",
          weight: 1.5,
          fillColor: "#edf2e8",
          fillOpacity: 0.12,
        }}
      />
      {focus && (
        <CircleMarker
          center={[focus.latitude, focus.longitude]}
          interactive={false}
          radius={8}
          pathOptions={{
            className: "live-map__place-pin",
            color: "#1d4ed8",
            weight: 2,
            fillColor: "#60a5fa",
            fillOpacity: 0.9,
          }}
        />
      )}
    </>
  );
}
