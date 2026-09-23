import { useEffect, useRef } from "react";
import { useMap } from "react-leaflet";
import type { LatLngBoundsLiteral } from "leaflet";
import type { LiveResult } from "../../shared/api/api";
import { geometryLatLngs } from "./liveResultPresentation";

export const BC_BOUNDS: LatLngBoundsLiteral = [
  [48.2, -139.2],
  [60.1, -114.0],
];

export type MapFocus = { latitude: number; longitude: number };

export function FitResults({
  results,
  active = true,
  focus,
  focusResults,
  selectedResultId,
  scopeKey,
}: {
  active?: boolean;
  results: LiveResult[];
  focus?: MapFocus | undefined;
  focusResults: LiveResult[];
  selectedResultId?: string | undefined;
  scopeKey?: string | undefined;
}) {
  const map = useMap();
  const selected = results.find((result) => result.result_id === selectedResultId);
  const scope = [scopeKey, focus?.latitude, focus?.longitude].join("|");
  const previous = useRef<{ scope: string; selectedId?: string | undefined; fittedRecords: boolean } | undefined>(undefined);

  useEffect(() => {
    if (typeof ResizeObserver === "undefined") return;
    // Expanding the in-app map changes its container without a window resize.
    // Update Leaflet's cached dimensions without re-fitting the selected record.
    const observer = new ResizeObserver(() => {
      map.invalidateSize({ animate: false, pan: false });
    });
    observer.observe(map.getContainer());
    return () => observer.disconnect();
  }, [map]);

  useEffect(() => {
    if (!active) return;
    const before = previous.current;
    const needsFit = !before || before.scope !== scope
      || (Boolean(selectedResultId) && before.selectedId !== selectedResultId)
      || (!before.fittedRecords && results.length > 0);
    previous.current = { scope, selectedId: selectedResultId, fittedRecords: before?.fittedRecords || results.length > 0 };
    if (!needsFit) return;
    if (selected) {
      const selectedCoordinates = geometryLatLngs(selected);
      if (selectedCoordinates.length > 0) {
        map.fitBounds(selectedCoordinates, { padding: [40, 40], maxZoom: 12, animate: false });
        return;
      }
    }
    if (focus) {
      const nearbyCoordinates = focusResults.flatMap(geometryLatLngs);
      if (nearbyCoordinates.length > 0) {
        map.fitBounds(
          [[focus.latitude, focus.longitude], ...nearbyCoordinates],
          { padding: [40, 40], maxZoom: 10, animate: false },
        );
      } else {
        map.setView([focus.latitude, focus.longitude], 10, { animate: false });
      }
      return;
    }
    if (results.length === 0) {
      map.fitBounds(BC_BOUNDS, { padding: [12, 12], animate: false });
      return;
    }
    const coordinates = results.flatMap(geometryLatLngs);
    if (coordinates.length > 0) {
      map.fitBounds(coordinates, { padding: [40, 40], maxZoom: 9, animate: false });
    } else {
      map.fitBounds(BC_BOUNDS, { padding: [12, 12], animate: false });
    }
  }, [active, map, scope, results, focus, focusResults, selected, selectedResultId]);
  return null;
}
