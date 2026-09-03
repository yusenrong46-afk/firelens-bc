import { ArrowSquareOut, CheckCircle, Code, Database, ShieldCheck, X } from "@phosphor-icons/react";
import { useEffect, useRef } from "react";

export function HowFireLensWorks({ open, onClose }: { open: boolean; onClose: () => void }) {
  const closeButton = useRef<HTMLButtonElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    if (!open) return;
    const previouslyFocused = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    heading.current?.focus();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      previouslyFocused?.focus();
    };
  }, [onClose, open]);

  if (!open) return null;
  return (
      <section
        id="how-firelens-works"
        className="project-explainer"
        role="region"
        aria-labelledby="project-dialog-title"
        aria-describedby="project-dialog-description"
      >
        <div className="project-dialog__header">
          <div>
            <span className="panel-label">About</span>
            <h2 ref={heading} id="project-dialog-title" tabIndex={-1}>How FireLens works</h2>
          </div>
          <button ref={closeButton} type="button" onClick={onClose} aria-label="Close how FireLens works">
            <X size={22} />
          </button>
        </div>
        <p className="project-dialog__lead" id="project-dialog-description">
          FireLens answers questions about wildfires in British Columbia using official records and
          reviewed guidance, and shows you where each answer comes from.
        </p>
        <ol className="project-flow">
          <li><Database size={23} /><div><strong>Official records</strong><span>Fire locations, status, size, and evacuation orders and alerts come from the BC Wildfire Service and EmergencyInfoBC, fetched when you ask.</span></div></li>
          <li><Code size={23} /><div><strong>Counts and distances are calculated, not guessed</strong><span>Straight-line distances, counts, and update times are computed from the official records.</span></div></li>
          <li><ShieldCheck size={23} /><div><strong>Guidance is quoted from reviewed sources</strong><span>Preparedness and safety guidance is shown with the publisher, document, and exact passage.</span></div></li>
          <li><CheckCircle size={23} /><div><strong>Limits are stated</strong><span>If FireLens cannot confirm something, it says so and points you to the official source instead of guessing.</span></div></li>
        </ol>
        <div className="project-dialog__links">
          <a href="https://wildfiresituation.nrs.gov.bc.ca/map" target="_blank" rel="noreferrer">BC Wildfire Service map <ArrowSquareOut size={17} /></a>
          <a href="https://www.emergencyinfobc.gov.bc.ca/" target="_blank" rel="noreferrer">EmergencyInfoBC <ArrowSquareOut size={17} /></a>
          <a href="/openapi.json" target="_blank" rel="noreferrer">OpenAPI contract <ArrowSquareOut size={17} /></a>
        </div>
        <p className="project-dialog__limit">FireLens is not emergency advice. In immediate danger, call 9-1-1 and follow instructions from local authorities.</p>
      </section>
  );
}
