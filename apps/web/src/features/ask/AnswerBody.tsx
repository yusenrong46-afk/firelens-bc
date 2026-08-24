import { WarningCircle } from "@phosphor-icons/react";
import type { AskResponse } from "../../shared/api/api";
import { AnswerMarkdown } from "./AnswerMarkdown";
import { answerSectionAuthority, getAnswerSections } from "./answerSections";
import { getStatusBanner } from "./proofPresentation";
import { StatusBanner } from "./StatusBanner";

export function AnswerBody({
  response,
  assistantText,
}: {
  response: AskResponse | undefined;
  assistantText: string;
}) {
  const answerSections = getAnswerSections(response);
  const visibleLimitations = Array.from(
    new Set((response?.limitations ?? []).map((item) => item.trim()).filter(Boolean)),
  );
  const lead = response?.answer?.trim() || assistantText;
  const banner = getStatusBanner(response);
  const hasAnswerSections = answerSections.length > 0;

  return (
    <>
      {banner && <StatusBanner banner={banner} />}
      {!hasAnswerSections && lead && <AnswerMarkdown className="answer-lead">{lead}</AnswerMarkdown>}
      {hasAnswerSections && (
        <div className="answer-sections" aria-label="Authority-labelled answer">
          {answerSections.map((section) => (
            <section className="answer-section" key={section.kind}>
              <span className="answer-section__authority">{answerSectionAuthority(section.kind)}</span>
              <h2>{section.heading}</h2>
              <AnswerMarkdown headingContext="section">{section.text}</AnswerMarkdown>
            </section>
          ))}
        </div>
      )}
      {visibleLimitations.length > 0 && (
        <aside className="answer-limitations" aria-label="Answer limitations">
          <WarningCircle size={19} aria-hidden="true" />
          <div>
            <strong>Important limits</strong>
            <ul>
              {visibleLimitations.map((item) => <li key={item}>{item}</li>)}
            </ul>
          </div>
        </aside>
      )}
    </>
  );
}
