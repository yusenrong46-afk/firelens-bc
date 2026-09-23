import { Info, WarningCircle } from "@phosphor-icons/react";
import type { ReactNode } from "react";
import type { AskResponse } from "../../shared/api/api";
import { analyticalAnswerSummary } from "../near-me/liveAnalysis";
import { AnswerMarkdown } from "./AnswerMarkdown";
import { answerSectionAuthority, getAnswerSections } from "./answerSections";
import { readableAnswer } from "./readableAnswer";
import { guidanceGroups } from "./guidanceGroups";
import { splitLimitations } from "./limitationsPresentation";
import { LiveSourceLine } from "./LiveAnswerSummary";
import { getStatusBanner } from "./proofPresentation";
import { SourceProof, reviewedSources, sourcesForQuote } from "./SourceProof";
import { StatusBanner } from "./StatusBanner";

export function AnswerBody({
  response,
  assistantText,
  analytical = false,
  footer,
  records,
  authority,
  onInspectEvidence,
  condensed = false,
  evidenceDetails,
}: {
  condensed?: boolean;
  evidenceDetails?: ReactNode;
  response: AskResponse | undefined;
  assistantText: string;
  analytical?: boolean;
  footer?: ReactNode;
  records?: ReactNode;
  authority?: ReactNode;
  onInspectEvidence?: (() => void) | undefined;
}) {
  const answerSections = getAnswerSections(response);
  const split = splitLimitations(
    Array.from(new Set((response?.limitations ?? []).map((item) => item.trim()).filter(Boolean))),
  );
  const provenanceNotes = condensed ? split.material.filter((item) => /^Grounded in reviewed official sources\.?$/i.test(item)) : [];
  const material = split.material.filter((item) => !provenanceNotes.includes(item));
  const boilerplate = [...split.boilerplate, ...provenanceNotes];
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
  const groups = response ? guidanceGroups(response) : [];
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
    && /^(Grounded in reviewed official sources|Official records|(?:Current|Cached) official records|Official records, some out of date|From reviewed official guidance|Partly from reviewed guidance|Official records and reviewed guidance)$/i.test(
      banner.headline,
    )
    && !freshnessWarning,
  );

  const sources = reviewedSources(response);
  const publisher = sources[0]?.publisher ?? response?.live_results?.[0]?.authority;
  const supportingDetails = <>      {authority && <div className="answer-state-strip">{authority}</div>}
      {liveSummary && response && <LiveSourceLine results={response.live_results ?? []} />}
      {!analytical
        && !backgroundMode
        && !compactOfficialHandoff
        && banner
        && !(liveSummary && compactBanner)
        && <StatusBanner banner={banner} compact={compactBanner && !freshnessWarning} showSummary={!compactBanner || !authority} />}
      {backgroundMode && (
        <p className="answer-provenance" role="note">
          General knowledge — not checked against FireLens sources
        </p>
      )}
      {analytical && banner && <StatusBanner banner={banner} compact />}
</>;

  return (
    <>
      {analytical && <span className="panel-label analytical-short-answer">FireLens answer</span>}
      {!analytical && quoteOnlyAnswer && (
        <span className="panel-label answer-source-kicker">Exact wording from the cited source revision</span>
      )}
      {groups.length > 0 && response ? (
        <ul className="guidance-groups" aria-label="Source descriptions by topic">
          {groups.map(group => <li key={group.heading}>
            <h2>{group.heading}</h2>
            {group.claims.map(claim => <div key={claim.claim_id}>
              <span className="answer-section__authority">{claim.publication?.kind === "official_quote_only" ? "Exact source wording" : "Reviewed guidance"}</span>
              <AnswerMarkdown>{readableAnswer(claim.text, response.claims, response.evidence)}</AnswerMarkdown>
            </div>)}
          </li>)}
        </ul>
      ) : !hasAnswerSections && quoteOnlyAnswer && response ? (
        <QuoteOnlyAnswer response={response} fallback={lead} />
      ) : !hasAnswerSections && lead ? (
        <AnswerMarkdown className="answer-lead" emphasizeOpening={!analytical}>{readableAnswer(lead, response?.claims, response?.evidence)}</AnswerMarkdown>
      ) : null}
      {hasAnswerSections && (
        <div className="answer-sections" aria-label="Authority-labelled answer">
          {answerSections.map((section, index) => (
            <section className="answer-section" key={`${section.kind}-${index}`}>
              <span className="answer-section__authority">{answerSectionAuthority(section.kind)}</span>
              <h2>{section.heading}</h2>
              <AnswerMarkdown headingContext="section">{readableAnswer(section.text, response?.claims, response?.evidence)}</AnswerMarkdown>
            </section>
          ))}
        </div>
      )}
      {!condensed && <>{supportingDetails}</>}
      {condensed && freshnessWarning && banner && <StatusBanner banner={banner} compact />}
      {condensed && backgroundMode && <p className="answer-provenance">General background · Not source-verified</p>}
      {!analytical
        && (material.length > 0 || (!condensed && !backgroundMode && boilerplate.length > 0))
        && (
        <aside className={`answer-limitations${material.length === 0 ? " answer-limitations--routine" : ""}`} aria-label="Answer limitations">
          {material.length > 0 ? <WarningCircle size={18} aria-hidden="true" /> : <Info size={18} aria-hidden="true" />}
          <div>
            {material.length > 0 ? (
              <>
                <strong>Important limits</strong>
                <ul>
                  {material.map((item) => <li key={item}>{item}</li>)}
                </ul>
              </>
            ) : null}
            {!condensed && boilerplate.length > 0 && (
              <details className="answer-limitations__more">
                <summary>Usage notes</summary>
                <ul>
                  {boilerplate.map((item) => <li key={item}>{item}</li>)}
                </ul>
              </details>
            )}
          </div>
        </aside>
      )}
      {condensed && records ? <details className="sheet-records"><summary>{response?.live_results?.length ?? 0} matching records</summary>{records}</details> : records}
      {condensed ? <details className="sheet-sources" key={response?.trace_id}>
        <summary><span>{backgroundMode ? "Conversation details" : publisher ?? "Sources & support"}</span><span>{!backgroundMode && (banner?.headline ?? "Support metadata unavailable")}</span></summary>
        {supportingDetails}
        <SourceProof response={response} showExcerpts={false} onInspectEvidence={onInspectEvidence} />
        {boilerplate.length > 0 && <details><summary>Usage notes</summary><ul>{boilerplate.map((item) => <li key={item}>{item}</li>)}</ul></details>}
        {evidenceDetails}
      </details> : !backgroundMode && <SourceProof response={response} showExcerpts={false} onInspectEvidence={onInspectEvidence} />}
      <div className="answer-notes">{footer}</div>
    </>
  );
}

function QuoteOnlyAnswer({
  response,
  fallback,
}: {
  response: AskResponse;
  fallback: string;
}) {
  const quotes = (response.claims ?? [])
    .map((claim) => claim.text.trim())
    .filter(Boolean);
  if (quotes.length === 0) {
    return <AnswerMarkdown className="answer-lead answer-lead--source-quote">{fallback}</AnswerMarkdown>;
  }
  const emergency = quotes.find((text) => /9\s*-\s*1\s*-\s*1|911/.test(text));
  const routine = quotes.find((text) => /EmergencyInfoBC|local authorit/i.test(text));
  const sourcesFor = (quote: string) => sourcesForQuote(response, quote);
  const documentKey = (item: NonNullable<AskResponse["evidence"]>[number]) =>
    `${item.canonical_url}\n${item.document_sha256 ?? ""}`;
  const allSources = quotes.flatMap(sourcesFor);
  const oneDocument = quotes.every((quote) => sourcesFor(quote).length > 0)
    && new Set(allSources.map(documentKey)).size === 1;
  const commonTitle = oneDocument ? allSources[0]?.title : undefined;
  const excerpt = (quote: string) => (
    <div className="quote-distinction__excerpt" key={quote}>
      <blockquote>
        <AnswerMarkdown>{readableAnswer(quote, response.claims, response.evidence)}</AnswerMarkdown>
      </blockquote>
      {!oneDocument && (sourcesFor(quote).length ? sourcesFor(quote).map((item) => (
        <p className="quote-distinction__source" key={item.evidence_id} data-source-revision={item.document_sha256 ?? undefined}>
          Source: {item.title}{item.locator ? ` · ${item.locator}` : ""}
        </p>
      )) : <p className="quote-distinction__source">Source attribution unavailable</p>)}
    </div>
  );
  return (
    <div className="answer-lead answer-lead--source-quote quote-distinction">
      {emergency && routine && (
        <p>
          <strong>Immediate danger versus routine official information.</strong>
        </p>
      )}
      {quotes.map(excerpt)}
      {commonTitle ? <p className="quote-distinction__source">Source: {commonTitle}</p> : null}
    </div>
  );
}
