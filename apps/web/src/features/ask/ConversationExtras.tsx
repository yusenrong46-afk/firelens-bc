import { FeedbackControls } from "../feedback/FeedbackControls";
import { ConversationToolbar, SuggestedQuestions } from "./ConversationPresentation";
import type { FireLensSession } from "./useFireLensSession";

/** Secondary conversation tools remain available inside the source disclosure. */
export function ConversationExtras({ session, onSuggest }: { session: FireLensSession; onSuggest: (question: string) => void }) {
  return <>
    {session.earlierTurns.length > 0 && <details className="history-group" aria-label="Earlier conversation">
      <summary>Earlier conversation</summary>
      {session.earlierTurns.map((turn, index) => <div className={`history-turn history-turn--${turn.role}`} key={index}><strong>{turn.role === "user" ? "You" : "FireLens"}</strong><p>{turn.content}</p></div>)}
    </details>}
    {session.suggestions.length > 0 && <details className="answer-suggestions"><summary>Suggested follow-ups</summary><SuggestedQuestions disabled={false} onSelect={onSuggest} suggestions={session.suggestions} /></details>}
    {session.response?.trace_id && <details className="answer-feedback"><summary>Feedback</summary><FeedbackControls traceId={session.response.trace_id} /></details>}
    <ConversationToolbar priorTurnCount={session.earlierTurns.length} onClear={session.clearHistory} />
  </>;
}
