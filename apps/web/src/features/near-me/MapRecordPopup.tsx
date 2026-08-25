import type { LiveResult } from "../../shared/api/api";
import {
  formatTimestamp,
  mapPopupGeometryMeaning,
  resultDisplayName,
  resultKindLabel,
  resultStatus,
} from "./liveResultPresentation";

export function MapRecordPopup({
  result,
  onAskAboutResult,
}: {
  result: LiveResult;
  onAskAboutResult?: ((resultId: string, question: string) => void) | undefined;
}) {
  return (
    <>
      <strong>{resultDisplayName(result)}</strong>
      <div>{resultKindLabel(result.kind)}</div>
      <div>{mapPopupGeometryMeaning(result)}</div>
      <div>{resultStatus(result)}</div>
      <div>Updated {formatTimestamp(result.source_updated_at)}</div>
      {onAskAboutResult && (
        <div className="map-popup-actions">
          {result.kind !== "evacuation" && (
            <button type="button" onClick={() => onAskAboutResult(result.result_id, "How far is this fire from me?")}>How far?</button>
          )}
          <button type="button" onClick={() => onAskAboutResult(result.result_id, "What is the current status of this fire?")}>Ask status</button>
        </div>
      )}
    </>
  );
}
