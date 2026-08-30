import { Crosshair } from "@phosphor-icons/react";

const DEFAULT_PLACE = "Kelowna, BC";

const INTENTS = [
  {
    id: "fires",
    label: "Fires near this place?",
    question: (place: string) => `What official fires are near ${place}?`,
  },
  {
    id: "distribution",
    label: "Wildfire distribution?",
    question: () => "Show current wildfire distribution by fire centre across B.C.",
  },
  {
    id: "preparedness",
    label: "What to pack?",
    question: () => "What belongs in a wildfire grab-and-go bag?",
  },
] as const;

export function AskStartPanel({
  locationLabel,
  onAsk,
  onLocationChange,
  onUseApproximateLocation,
}: {
  locationLabel: string;
  onAsk: (question: string) => void;
  onLocationChange: (value: string) => void;
  onUseApproximateLocation: () => void;
}) {
  const place = locationLabel.trim() || DEFAULT_PLACE;
  return (
    <div className="conversation-intro ask-start-panel">
      <span className="panel-label">British Columbia wildfire information</span>
      <h1>Ask about a fire, a B.C. place, or preparedness.</h1>
      <p>
        FireLens shows what came from official live records, reviewed sources, or clearly labelled
        general background.
      </p>
      <label className="ask-start-panel__place">
        <span>Place (optional)</span>
        <input
          aria-label="BC community for a nearby lookup"
          value={locationLabel}
          onChange={(event) => onLocationChange(event.target.value)}
          placeholder={DEFAULT_PLACE}
          maxLength={120}
        />
      </label>
      <button type="button" className="ask-start-panel__approx" onClick={onUseApproximateLocation}>
        <Crosshair size={16} aria-hidden="true" /> Use approximate location — not stored
      </button>
      <div className="ask-start-panel__intents" role="group" aria-label="Start with an intent">
        {INTENTS.map((intent) => (
          <button
            type="button"
            key={intent.id}
            onClick={() => onAsk(intent.question(place))}
          >
            {intent.label}
          </button>
        ))}
      </div>
    </div>
  );
}
