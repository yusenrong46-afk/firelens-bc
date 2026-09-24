import { Check, Copy, Info, ArrowRight } from "@phosphor-icons/react";
import { useEffect, useId, useMemo, useRef, useState } from "react";
import type { AskResponse } from "../../shared/api/api";
import { formatTimestamp } from "../near-me/liveResultPresentation";
import { explainAnswer, formatAnswerForCopy } from "./answerActionPresentation";
import "./answerActions.css";

export function AnswerActions({ response, displayedText, onOpenEvidence }: {
  response: AskResponse;
  displayedText: string;
  onOpenEvidence?: (() => void) | undefined;
}) {
  const panelId = useId();
  const [whyOpen, setWhyOpen] = useState(false);
  const [copyState, setCopyState] = useState<"idle" | "copying" | "copied" | "manual">("idle");
  const manualRef = useRef<HTMLTextAreaElement>(null);
  const whyTriggerRef = useRef<HTMLButtonElement>(null);
  const copyGeneration = useRef(0);
  const explanation = useMemo(() => explainAnswer(response), [response]);
  const copiedText = useMemo(() => formatAnswerForCopy(response, displayedText), [response, displayedText]);

  useEffect(() => {
    copyGeneration.current += 1;
    setCopyState("idle");
    setWhyOpen(false);
    return () => { copyGeneration.current += 1; };
  }, [response, displayedText]);

  useEffect(() => {
    if (copyState !== "manual") return;
    manualRef.current?.focus();
    manualRef.current?.select();
  }, [copyState]);

  async function copyAnswer() {
    const generation = ++copyGeneration.current;
    setCopyState("copying");
    try {
      if (!navigator.clipboard?.writeText) throw new Error("Clipboard unavailable");
      await navigator.clipboard.writeText(copiedText);
      if (copyGeneration.current === generation) setCopyState("copied");
    } catch {
      if (copyGeneration.current === generation) setCopyState("manual");
    }
  }

  return (
    <div className="answer-actions">
      <div className="answer-actions__toolbar" role="group" aria-label="Answer actions">
        <button
          type="button"
          className="answer-actions__button"
          onClick={() => void copyAnswer()}
          disabled={copyState === "copying"}
          title="Copies the answer, limits and sources. Places named in the answer are included."
        >
          {copyState === "copied" ? <Check size={16} aria-hidden="true" /> : <Copy size={16} aria-hidden="true" />}
          {copyState === "copying" ? "Copying…" : copyState === "copied" ? "Copied" : "Copy answer"}
        </button>
        <button
          ref={whyTriggerRef}
          type="button"
          className="answer-actions__button"
          aria-expanded={whyOpen}
          aria-controls={panelId}
          onClick={() => setWhyOpen((open) => !open)}
        >
          <Info size={16} aria-hidden="true" /> Why this answer?
        </button>
      </div>
      <span className="response-announcement" role="status" aria-live="polite" aria-atomic="true">
        {copyState === "copied" ? "Answer, limits and sources copied." : copyState === "manual" ? "Automatic copy is unavailable. The answer text is selected for manual copying." : ""}
      </span>
      {copyState === "manual" && (
        <div className="answer-actions__manual">
          <label htmlFor={`${panelId}-copy`}>Copy this answer manually</label>
          <p>Includes the answer, limits and sources, including any places named in the answer.</p>
          <textarea id={`${panelId}-copy`} ref={manualRef} value={copiedText} readOnly rows={7} />
          <button type="button" className="answer-actions__button" onClick={() => { manualRef.current?.focus(); manualRef.current?.select(); }}>Select answer text</button>
        </div>
      )}
      {whyOpen && (
        <section
          className="answer-explanation"
          id={panelId}
          aria-label="Why this answer"
          onKeyDown={(event) => {
            if (event.key !== "Escape") return;
            event.preventDefault();
            setWhyOpen(false);
            whyTriggerRef.current?.focus();
          }}
        >
          <header>
            <span className="answer-explanation__eyebrow">Behind the answer</span>
            <h2>Information you can inspect.</h2>
            <p>The sources, coverage and checks attached to this response.</p>
          </header>
          <div className="answer-explanation__sections">
            <section>
              <h3>Answer type</h3>
              <ul>{explanation.answerTypes.map((item) => <li key={item}>{item}</li>)}</ul>
              {explanation.supportLabels.length > 0 && <p className="answer-explanation__muted">Statement support: {explanation.supportLabels.join(" · ")}</p>}
            </section>
            <section>
              <h3>Sources attached</h3>
              {explanation.sources.length > 0 ? (
                <ul className="answer-explanation__sources">{explanation.sources.map((source, index) => (
                  <li key={`${source.url}-${index}`}>
                    <strong>{source.publisher}</strong>
                    <a href={source.url} target="_blank" rel="noreferrer">{source.title}<span className="response-announcement"> (opens in a new tab)</span></a>
                    {source.checkedAt && <p className="answer-explanation__muted">Record checked: {formatTimestamp(source.checkedAt)}</p>}
                    {source.updatedAt && <p className="answer-explanation__muted">Record updated: {formatTimestamp(source.updatedAt)}</p>}
                    {source.revision && (
                      <details className="answer-explanation__muted">
                        <summary>Document revision</summary>
                        <p>SHA-256: <code>{source.revision}</code></p>
                        <p>The publisher link may show a newer edition.</p>
                      </details>
                    )}
                  </li>
                ))}</ul>
              ) : <p>No source support is attached for inspection.</p>}
              {onOpenEvidence && explanation.canInspectEvidence && <button type="button" className="answer-actions__button" onClick={onOpenEvidence}>Inspect evidence <ArrowRight size={15} aria-hidden="true" /></button>}
            </section>
              <section>
                <h3>Coverage and limits</h3>
                <ul>{[...explanation.coverage, ...explanation.location, ...explanation.limitations].map((item, index) => <li key={`${index}-${item}`}>{item}</li>)}</ul>
                {explanation.coverage.length === 0 && <p>Coverage metadata was not supplied.</p>}
                {explanation.location.length === 0 && <p>Location and distance metadata were not supplied.</p>}
                {explanation.limitations.length === 0 && <p>No material limitations were supplied.</p>}
                <p className="answer-explanation__muted">Response checked: {explanation.checkedAt ? formatTimestamp(explanation.checkedAt) : "Not supplied"}</p>
                <p className="answer-explanation__muted">Response source updated: {explanation.updatedAt ? formatTimestamp(explanation.updatedAt) : "Not supplied"}</p>
              </section>
            <section>
              <h3>Response checks</h3>
              {explanation.checks ? (
                <>
                  <dl className="answer-explanation__checks">{explanation.checks.map((check) => (
                    <div key={check.label}><dt>{check.label}</dt><dd data-result={check.result}>{check.result}</dd></div>
                  ))}</dl>
                  <p className="answer-explanation__muted">These response checks do not establish safety or imply human review.</p>
                </>
              ) : <p>Check details were not supplied with this response.</p>}
            </section>
          </div>
        </section>
      )}
    </div>
  );
}
