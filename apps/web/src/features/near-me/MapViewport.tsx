import { useEffect } from "react";
import { useMap } from "react-leaflet";
import type { LatLngBoundsExpression } from "leaflet";
import type { LiveResult } from "../../shared/api/api";
import { geometryLatLngs } from "./liveResultPresentation";

export const BC_BOUNDS: LatLngBoundsExpression = [
  [48.2, -139.2],
  [60.1, -114.0],
];

export type MapFocus = { latitude: number; longitude: number };

export function FitResults({
  results,
  focus,
  focusResults,
  selectedResultId,
}: {
  results: LiveResult[];
  focus?: MapFocus | undefined;
  focusResults: LiveResult[];
  selectedResultId?: string | undefined;
}) {
  const map = useMap();
  const selected = results.find((result) => result.result_id === selectedResultId);
  const signature = [
    selectedResultId,
    focus?.latitude,
    focus?.longitude,
    ...focusResults.map((result) => result.result_id),
    ...results.map((result) => result.result_id),
  ].join("|");

  useEffect(() => {
    if (selected) {
      const selectedCoordinates = geometryLatLngs(selected);
      if (selectedCoordinates.length > 0) {
        map.fitBounds(selectedCoordinates, { padding: [40, 40], maxZoom: 12 });
        return;
      }
    }
    if (focus) {
      const nearbyCoordinates = focusResults.flatMap(geometryLatLngs);
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
    const coordinates = results.flatMap(geometryLatLngs);
    if (coordinates.length > 0) {
      map.fitBounds(coordinates, { padding: [40, 40], maxZoom: 9 });
    } else {
      map.fitBounds(BC_BOUNDS, { padding: [12, 12] });
    }
  }, [map, signature, results, focus, focusResults, selected]);
  return null;
}
