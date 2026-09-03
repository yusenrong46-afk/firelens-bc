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
        aria-label="Show all fires in B.C."
        onChange={(event) => onChange(event.target.checked)}
      />
      Show all fires in B.C.
      <small>Adds the rest of the province; the answer above covers only the records it names.</small>
    </label>
  );
}
