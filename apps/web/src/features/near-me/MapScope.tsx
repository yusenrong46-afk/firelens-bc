export function MapScope({
  displayedCount,
  displayedMatchingCount,
  matchingCount,
  resultCount,
}: {
  displayedCount: number;
  displayedMatchingCount: number;
  matchingCount: number;
  resultCount: number;
}) {
  const displayedUnrelatedCount = displayedCount - displayedMatchingCount;
  const unrelatedCount = resultCount - matchingCount;
  const filterNote = displayedCount !== resultCount
    ? " Filters change only what is shown; they do not change the returned records."
    : "";
  const unrelatedShown = displayedUnrelatedCount > 0
    ? ` ${displayedUnrelatedCount} other official ${displayedUnrelatedCount === 1 ? "record is" : "records are"} also shown for B.C.`
    : "";
  const unrelatedHidden = unrelatedCount > 0 && displayedUnrelatedCount === 0
    ? ` ${unrelatedCount} other official ${unrelatedCount === 1 ? "record is" : "records are"} hidden by current filters.`
    : "";

  if (resultCount === 0) {
    return <p className="live-map__scope" role="status">No official map records were returned for this view. This is not an all-clear.</p>;
  }
  if (matchingCount === 0) {
    if (displayedCount === 0) {
      return <p className="live-map__scope">No records were marked as matching this question, and current filters hide all official records returned for B.C.{filterNote}</p>;
    }
    return <p className="live-map__scope">No records were marked as matching this question. The map shows {displayedCount} official {displayedCount === 1 ? "record" : "records"} returned for B.C.{filterNote}</p>;
  }
  if (displayedMatchingCount === 0) {
    return <p className="live-map__scope">Records were returned for this question, but the current filters hide every matching record.{unrelatedShown}{unrelatedHidden}{filterNote}</p>;
  }
  return (
    <p className="live-map__scope">
      {displayedMatchingCount} {displayedMatchingCount === 1 ? "matching record is" : "matching records are"} shown for this question.
      {displayedMatchingCount !== matchingCount ? ` ${matchingCount} records were returned for this question before filtering.` : ""}
      {unrelatedShown}
      {unrelatedHidden}
      {filterNote}
    </p>
  );
}
