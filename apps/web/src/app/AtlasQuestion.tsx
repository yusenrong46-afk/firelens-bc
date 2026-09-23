import { X } from "@phosphor-icons/react";
import { useEffect, useRef, type ReactNode } from "react";
import { AskStartPanel } from "../features/ask/AskStartPanel";
import type { FireLensSession } from "../features/ask/useFireLensSession";

export function AtlasQuestion({ session, composer, open, examplesRequested, onClose, onPrepare, onMap }: {
  session: FireLensSession; composer: ReactNode; open: boolean; examplesRequested: boolean;
  onClose: () => void; onPrepare: (question: string) => void; onMap: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    if (!open) { if (dialog.current?.open) dialog.current.close(); return; }
    dialog.current?.showModal();
    if (examplesRequested) {
      const trigger = dialog.current?.querySelector<HTMLButtonElement>(".guided-questions__trigger");
      if (trigger?.getAttribute("aria-expanded") === "false") trigger.click();
    } else {
      dialog.current?.querySelector<HTMLInputElement>('input[aria-label="Ask FireLens a question"]')?.focus();
    }
  }, [open, examplesRequested]);
  return <dialog ref={dialog} className="atlas-question" aria-label="Ask FireLens" onCancel={onClose} onClose={onClose}>
    <div className="atlas-question__heading"><h2>Ask FireLens</h2><button type="button" aria-label="Close question" onClick={onClose}><X size={22} /></button></div>
    {composer}
    <AskStartPanel catalogueOnly locationLabel={session.locationLabel} onLocationChange={session.setLocationLabel} onUseApproximateLocation={session.useApproximateLocation} onSelectQuestion={session.submitQuestion} onPrepareQuestion={onPrepare} onOpenMap={onMap} />
  </dialog>;
}
