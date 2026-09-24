import type { LiveResult } from "../../shared/api/api";

/** Answer evidence stays immutable while the map retains the preceding lookup. */
export function answerMapScope(answer: LiveResult[], lookup: LiveResult[], displayed: LiveResult[]) {
  const visible = new Set(displayed.map((record) => record.result_id));
  const answerIds = new Set(answer.map((record) => record.result_id));
  const shown = [...answerIds].filter((id) => visible.has(id)).length;
  const retained = lookup.some((record) => !answerIds.has(record.result_id));
  const lookupCount = new Set(lookup.filter((record) => visible.has(record.result_id)).map((record) => record.result_id)).size;
  return { shown, total: answerIds.size, retained, lookupCount };
}

export function AnswerMapScope({ answer, lookup, displayed }: { answer: LiveResult[]; lookup: LiveResult[]; displayed: LiveResult[] }) {
  if (!answer.length && !lookup.length) return null;
  const scope = answerMapScope(answer, lookup, displayed);
  return <p className="atlas-live-checked">
    {scope.shown} of {scope.total} records from this answer shown
    {scope.retained && <> · {scope.lookupCount} records retained from the lookup shown</>}
    {" · Map observations refresh separately from the answer"}
  </p>;
}
