import { CircleMarker, GeoJSON, TileLayer } from "react-leaflet";
import { latLngBounds, type LatLngBoundsLiteral } from "leaflet";
import { bcBoundaryFeature } from "./bcBoundary";
import { BC_BOUNDS, type MapFocus } from "./MapViewport";

// Raster context covers B.C. and its surroundings. Official record geometry is
// independent of this tile bound and is never filtered by it.
const paddedBounds = latLngBounds(BC_BOUNDS).pad(0.2);
// A plain coordinate value also works across Vite's independently loaded modules.
const REGIONAL_TILE_BOUNDS: LatLngBoundsLiteral = [
  [paddedBounds.getSouth(), paddedBounds.getWest()],
  [paddedBounds.getNorth(), paddedBounds.getEast()],
];

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
        url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
        referrerPolicy="origin"
        attribution={OSM_ATTRIBUTION}
        bounds={REGIONAL_TILE_BOUNDS}
        updateWhenIdle
        updateWhenZooming={false}
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
