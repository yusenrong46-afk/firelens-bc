import { WarningCircle } from "@phosphor-icons/react";
import type { AskResponse } from "../../shared/api/api";
import { answerSectionAuthority, getAnswerSections } from "./answerSections";
import { getStatusBanner, getSupportChecklist } from "./proofPresentation";
import { StatusBanner, SupportChecklist } from "./StatusBanner";

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
  const checklist = getSupportChecklist(response);

  return (
    <>
      {banner && (
        <p className="status-banner-kicker">
          <strong>{banner.headline}</strong>
        </p>
      )}
      {lead && <p className="answer-lead">{lead}</p>}
      {visibleLimitations.length > 0 && (
        <div className="answer-limitations" aria-label="Answer limitations" role="status">
          <WarningCircle size={19} aria-hidden="true" />
          <div>
            <strong>Important limits</strong>
            <ul>
              {visibleLimitations.map((item) => <li key={item}>{item}</li>)}
            </ul>
          </div>
        </div>
      )}
      {banner && <StatusBanner banner={banner} hideHeadline />}
      <SupportChecklist supported={checklist.supported} unknown={checklist.unknown} />
      {answerSections.length > 0 && (
        <div className="answer-sections" aria-label="Authority-labelled answer">
          {answerSections.map((section) => (
            <section className="answer-section" key={section.kind}>
              <span className="answer-section__authority">{answerSectionAuthority(section.kind)}</span>
              <h2>{section.heading}</h2>
              <p>{section.text}</p>
            </section>
          ))}
        </div>
      )}
    </>
  );
}
