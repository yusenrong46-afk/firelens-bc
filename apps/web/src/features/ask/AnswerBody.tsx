import { WarningCircle } from "@phosphor-icons/react";
import type { AskResponse } from "../../shared/api/api";
import { analyticalAnswerSummary } from "../near-me/liveAnalysis";
import { AnswerMarkdown } from "./AnswerMarkdown";
import { answerSectionAuthority, getAnswerSections } from "./answerSections";
import { splitLimitations } from "./limitationsPresentation";
import { LiveAnswerSummary } from "./LiveAnswerSummary";
import { getStatusBanner } from "./proofPresentation";
import { StatusBanner } from "./StatusBanner";

export function AnswerBody({
  onSelectLiveResult,
  response,
  assistantText,
  analytical = false,
}: {
  onSelectLiveResult?: ((resultId: string) => void) | undefined;
  response: AskResponse | undefined;
  assistantText: string;
  analytical?: boolean;
}) {
  const answerSections = getAnswerSections(response);
  const { material, boilerplate } = splitLimitations(
    Array.from(new Set((response?.limitations ?? []).map((item) => item.trim()).filter(Boolean))),
  );
  // The backend answer preserves the requested operation (for example,
  // freshness comparison, ranked distance, or a bounded radius). The
  // analytical summary is presentation-only and must never replace that
  // operation-specific answer merely because multiple records were returned.
  const lead = response?.answer?.trim()
    ?? (analytical ? analyticalAnswerSummary(response?.live_results ?? []) : undefined)
    ?? assistantText;
  const banner = getStatusBanner(response);
  const backgroundMode = response?.response_mode === "background";
  const quoteOnlyAnswer = Boolean(
    (response?.claims?.length ?? 0) > 0
    && response?.claims?.every((claim) => claim.publication?.kind === "official_quote_only"),
  );
  const compactOfficialHandoff = response?.reason_code === "high_risk_claim_not_structured";
  const hasAnswerSections = answerSections.length > 0;
  const liveSummary = Boolean(
    !analytical
    && (response?.response_mode === "live" || response?.response_mode === "mixed")
    && (response?.live_results?.length ?? 0) > 0,
  );
  const freshnessWarning = Boolean(
    banner
    && /stale|mixed|unavailable|did not complete|not established/i.test(
      `${banner.freshness_label} ${banner.availability_label}`,
    ),
  );
  const compactBanner = Boolean(
    banner
    && (response?.response_mode === "live"
      || response?.response_mode === "grounded"
      || response?.response_mode === "mixed")
    && /^(Official (?:current |cached )?records|Official records with mixed freshness|Grounded in reviewed official sources|Partially supported by reviewed sources|Official records plus reviewed guidance)$/i.test(
      banner.headline,
    )
    && !freshnessWarning,
  );

  return (
    <>
      {analytical && <span className="panel-label analytical-short-answer">FireLens answer</span>}
      {!analytical && quoteOnlyAnswer && (
        <span className="panel-label answer-source-kicker">Exact official source wording</span>
      )}
      {!hasAnswerSections && lead && (
        <AnswerMarkdown className={quoteOnlyAnswer
          ? "answer-lead answer-lead--source-quote"
          : "answer-lead"}
        >
          {lead}
        </AnswerMarkdown>
      )}
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
      {liveSummary && response && (
        <LiveAnswerSummary
          response={response}
          onSelectResult={onSelectLiveResult}
        />
      )}
      {!analytical
        && !backgroundMode
        && !compactOfficialHandoff
        && banner
        && (!liveSummary || freshnessWarning)
        && <StatusBanner banner={banner} compact={compactBanner && !freshnessWarning} />}
      {backgroundMode && (
        <p className="answer-provenance" role="note">
          General model knowledge · not checked against FireLens sources
        </p>
      )}
      {analytical && banner && <StatusBanner banner={banner} compact />}
      {!analytical
        && !compactOfficialHandoff
        && (material.length > 0 || (!backgroundMode && boilerplate.length > 0))
        && (
        <aside className="answer-limitations" aria-label="Answer limitations">
          <WarningCircle size={19} aria-hidden="true" />
          <div>
            {material.length > 0 ? (
              <>
                <strong>Important limits</strong>
                <ul>
                  {material.map((item) => <li key={item}>{item}</li>)}
                </ul>
              </>
            ) : (
              <strong>About this answer</strong>
            )}
            {boilerplate.length > 0 && (
              <details className="answer-limitations__more">
                <summary>Why does FireLens say this?</summary>
                <ul>
                  {boilerplate.map((item) => <li key={item}>{item}</li>)}
                </ul>
              </details>
            )}
          </div>
        </aside>
      )}
    </>
  );
}
