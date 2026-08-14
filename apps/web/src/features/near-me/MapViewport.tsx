import { useEffect } from "react";
import { useMap } from "react-leaflet";
import type { LatLngBoundsExpression } from "leaflet";
import type { LiveResult } from "../../shared/api/api";

export const BC_BOUNDS: LatLngBoundsExpression = [
  [48.2, -139.2],
  [60.1, -114.0],
];

export type MapFocus = { latitude: number; longitude: number };

function pointCoordinates(results: LiveResult[]): [number, number][] {
  return results.flatMap((result) => {
    const geometry = result.geometry as { type?: string; coordinates?: unknown };
    if (geometry.type !== "Point" || !Array.isArray(geometry.coordinates)) return [];
    const [longitude, latitude] = geometry.coordinates as number[];
    return Number.isFinite(latitude) && Number.isFinite(longitude)
      ? ([[latitude, longitude]] as [number, number][])
      : [];
  });
}

export function FitResults({
  results,
  focus,
  focusResults,
}: {
  results: LiveResult[];
  focus?: MapFocus | undefined;
  focusResults: LiveResult[];
}) {
  const map = useMap();
  const signature = [
    focus?.latitude,
    focus?.longitude,
    ...focusResults.map((result) => result.result_id),
    ...results.map((result) => result.result_id),
  ].join("|");

  useEffect(() => {
    if (focus) {
      const nearbyCoordinates = pointCoordinates(focusResults);
      if (nearbyCoordinates.length > 0) {
        map.fitBounds(
          [[focus.latitude, focus.longitude], ...nearbyCoordinates],
          { padding: [40, 40], maxZoom: 10 },
        );
      } else {
        map.setView([focus.latitude, focus.longitude], 10);
      }
      return;
    }
    if (results.length === 0) {
      map.fitBounds(BC_BOUNDS, { padding: [12, 12] });
      return;
    }
    const coordinates = pointCoordinates(results);
    if (coordinates.length > 0) {
      map.fitBounds(coordinates, { padding: [40, 40], maxZoom: 9 });
    } else {
      map.fitBounds(BC_BOUNDS, { padding: [12, 12] });
    }
  }, [map, signature, results, focus, focusResults]);
  return null;
}
