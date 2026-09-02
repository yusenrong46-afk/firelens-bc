export function MapContextLayers({
  enabled,
  onChange,
}: {
  enabled: boolean;
  onChange: (enabled: boolean) => void;
}) {
  return (
    <label className="live-map__context-layers">
      <input
        type="checkbox"
        checked={enabled}
        aria-label="Show additional B.C. context layers"
        onChange={(event) => onChange(event.target.checked)}
      />
      Show additional B.C. context layers
      <small>These records are not in the authorized answer set.</small>
    </label>
  );
}
