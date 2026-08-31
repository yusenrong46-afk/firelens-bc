import {
  ArrowRight,
  Backpack,
  ChartBar,
  Crosshair,
  MapPin,
} from "@phosphor-icons/react";

const DEFAULT_PLACE = "Kelowna, BC";

const INTENTS = [
  {
    id: "fires",
    icon: MapPin,
    label: "Fires near this place?",
    question: (place: string) => `What official fires are near ${place}?`,
  },
  {
    id: "distribution",
    icon: ChartBar,
    label: "Wildfire distribution?",
    question: () => "Show current wildfire distribution by fire centre across B.C.",
  },
  {
    id: "preparedness",
    icon: Backpack,
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
    <section className="conversation-intro ask-start-panel">
      <div className="ask-start-panel__intro">
        <span className="panel-label">British Columbia wildfire information</span>
        <h1>Ask about a fire, a B.C. place, or preparedness.</h1>
        <p>Official incidents, reviewed guidance, and labelled background stay separate.</p>
      </div>
      <div className="ask-start-panel__console">
        <div className="ask-start-panel__console-heading">
          <span className="panel-label">Start a query</span>
          <span>3 paths</span>
        </div>
        <label className="ask-start-panel__place">
          <span>B.C. place <small>Optional</small></span>
          <input
            aria-label="BC community for a nearby lookup"
            value={locationLabel}
            onChange={(event) => onLocationChange(event.target.value)}
            placeholder={DEFAULT_PLACE}
            maxLength={120}
          />
        </label>
        <button type="button" className="ask-start-panel__approx" aria-label="Use approximate location" onClick={onUseApproximateLocation}>
          <Crosshair size={18} aria-hidden="true" />
          <span>Use approximate location <small>Not stored</small></span>
        </button>
        <div className="ask-start-panel__intents" role="group" aria-label="Start with an intent">
          {INTENTS.map((intent, index) => {
            const Icon = intent.icon;
            return (
              <button
                type="button"
                key={intent.id}
                aria-label={intent.label}
                onClick={() => onAsk(intent.question(place))}
              >
                <span className="ask-start-panel__intent-index">0{index + 1}</span>
                <Icon size={20} aria-hidden="true" />
                <span>{intent.label}</span>
                <ArrowRight size={18} aria-hidden="true" />
              </button>
            );
          })}
        </div>
      </div>
    </section>
  );
}
