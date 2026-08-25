import { ArrowSquareOut, CheckCircle, Code, Database, ShieldCheck, X } from "@phosphor-icons/react";
import { useEffect, useRef } from "react";

export function HowFireLensWorks({ open, onClose }: { open: boolean; onClose: () => void }) {
  const closeButton = useRef<HTMLButtonElement>(null);
  const dialog = useRef<HTMLElement>(null);

  useEffect(() => {
    if (!open) return;
    const previouslyFocused = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    closeButton.current?.focus();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
      if (event.key !== "Tab" || !dialog.current) return;
      const focusable = Array.from(dialog.current.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])',
      ));
      if (focusable.length === 0) return;
      const first = focusable[0]!;
      const last = focusable.at(-1)!;
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      previouslyFocused?.focus();
    };
  }, [onClose, open]);

  if (!open) return null;
  return (
    <div className="project-dialog-backdrop" onMouseDown={(event) => {
      if (event.currentTarget === event.target) onClose();
    }}>
      <section ref={dialog} className="project-dialog" role="dialog" aria-modal="true" aria-labelledby="project-dialog-title" aria-describedby="project-dialog-description">
        <div className="project-dialog__header">
          <div>
            <span className="panel-label">FireLens BC V1.6</span>
            <h2 id="project-dialog-title">How FireLens earns the right to publish</h2>
          </div>
          <button ref={closeButton} type="button" onClick={onClose} aria-label="Close how FireLens works">
            <X size={22} />
          </button>
        </div>
        <p className="project-dialog__lead" id="project-dialog-description">
          FireLens is an evidence-governed environmental information system. Models may route a question or propose wording; official records, reviewed claims, and deterministic validators control factual publication.
        </p>
        <ol className="project-flow">
          <li><Database size={23} /><div><strong>Acquire governed evidence</strong><span>Current facts come from typed official wildfire records. Stable guidance comes from a hash-bound reviewed corpus.</span></div></li>
          <li><Code size={23} /><div><strong>Analyze with application-owned code</strong><span>Counts, distance, freshness, grouping, and comparisons are computed from structured fields—not extracted from fluent prose.</span></div></li>
          <li><ShieldCheck size={23} /><div><strong>Validate before presentation</strong><span>Identity, exact quotations, authority, relevance, critical fields, and failure states are checked before an answer is labelled.</span></div></li>
          <li><CheckCircle size={23} /><div><strong>Keep uncertainty visible</strong><span>Unsupported material becomes an exact quote, limitation, unknown, or official handoff. Empty results are never an all-clear.</span></div></li>
        </ol>
        <div className="project-dialog__facts" aria-label="V1.6 implementation facts">
          <span><strong>26</strong> bound typed claims</span>
          <span><strong>36/36</strong> raw candidates dispositioned</span>
          <span><strong>50</strong> user-end evaluation questions</span>
          <span><strong>0</strong> generation for high-risk structured guidance</span>
        </div>
        <div className="project-dialog__links">
          <a href="https://github.com/yusenrong46-afk/firelens-bc" target="_blank" rel="noreferrer">Repository <ArrowSquareOut size={17} /></a>
          <a href="https://github.com/yusenrong46-afk/firelens-bc/blob/main/docs/openapi.v1.json" target="_blank" rel="noreferrer">OpenAPI contract <ArrowSquareOut size={17} /></a>
        </div>
        <p className="project-dialog__limit">Engineering evidence is not emergency advice, independent certification, or a release approval.</p>
      </section>
    </div>
  );
}
