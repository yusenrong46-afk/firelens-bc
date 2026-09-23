import { memo, useEffect, useMemo, useRef } from "react";
import type { GeoJSON as LeafletGeoJSON } from "leaflet";
import { GeoJSON, Popup } from "react-leaflet";
import type { LiveResult } from "../../shared/api/api";
import { MapRecordPopup } from "./MapRecordPopup";
import { resultColour } from "./liveResultPresentation";

export const StaticGeometry = memo(function StaticGeometry({
  result,
  matching,
  selected,
  onAskAboutResult,
  onSelectResult,
}: {
  result: LiveResult;
  matching: boolean;
  selected: boolean;
  onAskAboutResult?: ((resultId: string, question: string) => void) | undefined;
  onSelectResult?: ((resultId: string) => void) | undefined;
}) {
  const data = useMemo(
    () => ({ type: "Feature", properties: {}, geometry: result.geometry } as unknown as GeoJSON.Feature),
    [result.geometry],
  );
  const layer = useRef<LeafletGeoJSON | null>(null);
  const geometryKey = useMemo(() => JSON.stringify(result.geometry), [result.geometry]);
  const previousGeometry = useRef(geometryKey);
  const style = useMemo(() => ({
    className: "live-map__record-geometry",
    color: resultColour(result.kind),
    weight: selected ? 4 : 2,
    opacity: matching ? 1 : 0.32,
    fillOpacity: selected ? 0.38 : matching ? 0.22 : 0.07,
  }), [matching, result.kind, selected]);
  useEffect(() => {
    if (!layer.current || previousGeometry.current === geometryKey) return;
    // react-leaflet treats GeoJSON data as immutable. Apply changed coordinates
    // to the retained layer so selection and the map viewport survive refresh.
    const popupOpen = layer.current.isPopupOpen();
    layer.current.clearLayers().addData(data).setStyle(style);
    previousGeometry.current = geometryKey;
    if (popupOpen) layer.current.openPopup();
  }, [data, geometryKey, style]);
  return (
    <GeoJSON
      ref={layer}
      data={data}
      style={style}
      eventHandlers={{ click: () => onSelectResult?.(result.result_id) }}
    >
      <Popup autoPan={false}>
        <MapRecordPopup result={result} onAskAboutResult={onAskAboutResult} />
      </Popup>
    </GeoJSON>
  );
});
