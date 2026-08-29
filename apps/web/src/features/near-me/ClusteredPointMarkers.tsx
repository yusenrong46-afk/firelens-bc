import { useEffect, useMemo, useState } from "react";
import { CircleMarker, Popup, useMap } from "react-leaflet";
import type { LiveResult } from "../../shared/api/api";
import { clusterPointResults, isQuestionMatch } from "./mapClustering";
import { MapRecordPopup } from "./MapRecordPopup";
import { resultColour } from "./liveResultPresentation";

export function ClusteredPointMarkers({
  matchingResultIds,
  onAskAboutResult,
  onSelectResult,
  results,
  selectedResultId,
}: {
  matchingResultIds: Set<string>;
  onAskAboutResult?: ((resultId: string, question: string) => void) | undefined;
  onSelectResult?: ((resultId: string) => void) | undefined;
  results: LiveResult[];
  selectedResultId?: string | undefined;
}) {
  const map = useMap();
  const [zoom, setZoom] = useState(map.getZoom());
  useEffect(() => {
    const onZoom = () => setZoom(map.getZoom());
    map.on("zoomend", onZoom);
    return () => {
      map.off("zoomend", onZoom);
    };
  }, [map]);
  const clusters = useMemo(() => clusterPointResults(results, zoom), [results, zoom]);
  return (
    <>
      {clusters.map((item) => {
        if (item.type === "cluster") {
          const matching = isQuestionMatch(item.ids, matchingResultIds);
          return (
            <CircleMarker
              key={`cluster:${item.ids.join("|")}`}
              center={[item.latitude, item.longitude]}
              radius={Math.min(18, 8 + item.count / 4)}
              eventHandlers={{
                click: () => map.setView(
                  [item.latitude, item.longitude],
                  Math.min(map.getMaxZoom(), zoom + 2),
                ),
              }}
              pathOptions={{
                className: "live-map__record-geometry",
                color: "#fff",
                weight: 2,
                fillColor: "#6b4f2a",
                opacity: matching ? 1 : 0.35,
                fillOpacity: matching ? 0.85 : 0.25,
              }}
            >
              <Popup>{item.count} official records in this area. Zoom in to inspect each record.</Popup>
            </CircleMarker>
          );
        }
        const matching = isQuestionMatch([item.result.result_id], matchingResultIds);
        return (
          <CircleMarker
            key={item.result.result_id}
            center={[item.latitude, item.longitude]}
            radius={7}
            eventHandlers={{ click: () => onSelectResult?.(item.result.result_id) }}
            pathOptions={{
              className: "live-map__record-geometry",
              color: "#fff",
              weight: item.result.result_id === selectedResultId ? 4 : 2,
              fillColor: resultColour(item.result.kind),
              opacity: matching ? 1 : 0.35,
              fillOpacity: matching ? 1 : 0.25,
            }}
          >
            <Popup>
              <MapRecordPopup result={item.result} onAskAboutResult={onAskAboutResult} />
            </Popup>
          </CircleMarker>
        );
      })}
    </>
  );
}
