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
            <span className="panel-label">FireLens BC V1.6</span>
            <h2 ref={heading} id="project-dialog-title" tabIndex={-1}>How FireLens works</h2>
          </div>
          <button ref={closeButton} type="button" onClick={onClose} aria-label="Close how FireLens works">
            <X size={22} />
          </button>
        </div>
        <p className="project-dialog__lead" id="project-dialog-description">
          FireLens uses official records, reviewed claims, and deterministic checks to control factual publication.
        </p>
        <ol className="project-flow">
          <li><Database size={23} /><div><strong>Acquire governed evidence</strong><span>Live facts use typed official records; guidance uses reviewed sources.</span></div></li>
          <li><Code size={23} /><div><strong>Analyze with application-owned code</strong><span>Counts, distance, freshness, and grouping use structured fields.</span></div></li>
          <li><ShieldCheck size={23} /><div><strong>Validate before presentation</strong><span>Identity, authority, quotations, fields, and failure states are checked.</span></div></li>
          <li><CheckCircle size={23} /><div><strong>Keep uncertainty visible</strong><span>Unsupported material stays a quote, limitation, unknown, or handoff.</span></div></li>
        </ol>
        <details className="project-dialog__details">
          <summary>Implementation details</summary>
          <div className="project-dialog__facts" aria-label="V1.6 implementation facts">
            <span><strong>26</strong> bound typed claims</span>
            <span><strong>36/36</strong> raw candidates dispositioned</span>
            <span><strong>50</strong> user-end evaluation questions</span>
            <span><strong>0</strong> generation for high-risk structured guidance</span>
          </div>
        </details>
        <div className="project-dialog__links">
          <a href="/openapi.json" target="_blank" rel="noreferrer">OpenAPI contract <ArrowSquareOut size={17} /></a>
        </div>
        <p className="project-dialog__limit">Not emergency advice, independent certification, or release approval.</p>
      </section>
  );
}
