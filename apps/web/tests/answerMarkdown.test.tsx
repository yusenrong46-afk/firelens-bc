import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { AnswerBody } from "../src/features/ask/AnswerBody";
import { AnswerMarkdown } from "../src/features/ask/AnswerMarkdown";
import type { AskResponse } from "../src/shared/api/api";

afterEach(cleanup);

describe("answer Markdown", () => {
  it("renders the API answer through the Markdown surface", () => {
    const response = {
      status: "answer",
      response_mode: "capability",
      trace_id: "trace-markdown-answer",
      answer: "**Current overview**\n\n- First record\n- Second record",
      claims: [],
      evidence: [],
      limitations: [],
      presentation_shell: "chat",
      provenance_class: "clarification",
    } as AskResponse;

    render(<AnswerBody response={response} assistantText="" />);

    expect(screen.getByText("Current overview").tagName).toBe("STRONG");
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
  });

  it("uses authority-labelled sections instead of repeating the combined answer", () => {
    const response = {
      status: "answer",
      response_mode: "mixed",
      trace_id: "trace-section-authority",
      answer: "Combined answer that should not be repeated.",
      answer_sections: [
        {
          kind: "current_records",
          heading: "Current official records",
          text: "Exact official section text.",
        },
        {
          kind: "general_background",
          heading: "General background",
          text: "Exact background section text.",
        },
      ],
      claims: [],
      evidence: [],
      limitations: [],
      presentation_shell: "chat",
      provenance_class: "mixed",
    } as AskResponse;

    render(<AnswerBody response={response} assistantText="Fallback text that should not be repeated." />);

    expect(screen.queryByText("Combined answer that should not be repeated.")).not.toBeInTheDocument();
    expect(screen.queryByText("Fallback text that should not be repeated.")).not.toBeInTheDocument();
    expect(screen.getAllByText("Exact official section text.")).toHaveLength(1);
    expect(screen.getAllByText("Exact background section text.")).toHaveLength(1);
  });

  it("renders emphasis and list syntax as semantic content", () => {
    render(
      <AnswerMarkdown>{"**Current official records**\n\n- First fire\n- Second fire"}</AnswerMarkdown>,
    );

    expect(screen.getByText("Current official records").tagName).toBe("STRONG");
    expect(screen.queryByText(/\*\*Current official records\*\*/)).not.toBeInTheDocument();
    const list = screen.getByRole("list");
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
  });

  it("ignores raw HTML and blocks unsafe link protocols", () => {
    const { container } = render(
      <AnswerMarkdown>
        {'Before <script>alert("unsafe")</script> <img src="https://tracker.test/pixel"> after. [Unsafe](javascript:alert(1))'}
      </AnswerMarkdown>,
    );

    expect(container.querySelector("script")).not.toBeInTheDocument();
    expect(container.querySelector("img")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Unsafe" })).not.toBeInTheDocument();
    expect(screen.getByText("Unsafe")).toBeInTheDocument();
  });

  it.each([
    ["protocol-relative", "//evil.test/path"],
    ["HTTP", "http://example.test/source"],
    ["mailto", "mailto:help@example.test"],
    ["credential-bearing HTTPS", "https://user:password@example.test/source"],
    ["line-feed-obfuscated javascript", "java\nscript:alert(1)"],
    ["tab-obfuscated javascript", "java\tscript:alert(1)"],
    ["carriage-return-obfuscated javascript", "java\rscript:alert(1)"],
    ["entity-obfuscated javascript", "javascript&#58;alert(1)"],
    ["entity-obfuscated data URL", "data&#58;text/html,unsafe"],
  ])("does not render %s links as anchors", (_label, href) => {
    const { container } = render(<AnswerMarkdown>{`[Unsafe](${href})`}</AnswerMarkdown>);

    expect(screen.queryByRole("link", { name: "Unsafe" })).not.toBeInTheDocument();
    expect(container).toHaveTextContent("Unsafe");
  });

  it("opens external source links safely", () => {
    render(<AnswerMarkdown>{"[BC Wildfire Service](https://wildfiresituation.nrs.gov.bc.ca/)"}</AnswerMarkdown>);

    expect(screen.getByRole("link", { name: "BC Wildfire Service" })).toMatchObject({
      target: "_blank",
      rel: "noopener noreferrer",
    });
  });

  it("wraps accessible tables for narrow viewports and uses a section heading outline", () => {
    render(
      <AnswerMarkdown headingContext="section">
        {"# Distribution\n\n| Fire centre | Count |\n| --- | ---: |\n| Kamloops | 12 |"}
      </AnswerMarkdown>,
    );

    expect(screen.queryByRole("heading", { level: 1 })).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 3, name: "Distribution" })).toBeInTheDocument();
    const tableRegion = screen.getByRole("region", { name: "Scrollable answer table" });
    expect(tableRegion).toHaveClass("answer-markdown__table-scroll");
    expect(tableRegion).toHaveAttribute("tabindex", "0");
    expect(within(tableRegion).getByRole("table")).toBeInTheDocument();
    expect(within(tableRegion).getByRole("columnheader", { name: "Fire centre" })).toBeInTheDocument();
  });

  it("does not introduce an orphan heading in the top-level answer lead", () => {
    render(<AnswerMarkdown>{"# Current official records"}</AnswerMarkdown>);

    expect(screen.queryByRole("heading")).not.toBeInTheDocument();
    expect(screen.getByText("Current official records").tagName).toBe("P");
  });

  it("keeps long unbroken answer text in the answer-markdown containment surface", () => {
    const token = "a".repeat(400);
    const { container } = render(<AnswerMarkdown>{token}</AnswerMarkdown>);

    expect(container.querySelector(".answer-markdown")).toHaveTextContent(token);
    expect(container.querySelector(".answer-markdown")).toHaveClass("answer-markdown");
  });

  it("preserves plain answer text", () => {
    const text = "No matching current official wildfire record was found.";
    const { container } = render(<AnswerMarkdown>{text}</AnswerMarkdown>);

    expect(container).toHaveTextContent(text);
    expect(container.querySelector("p")).toHaveTextContent(text);
  });

  it("labels quote-only answers from evidence title, not publication.source_title", () => {
    const response = {
      status: "answer",
      response_mode: "grounded",
      trace_id: "trace-quote-source",
      answer: "When to call 9-1-1.",
      presentation_shell: "chat",
      provenance_class: "reviewed_guidance",
      claims: [{
        claim_id: "c1",
        text: "Call 9-1-1 if you are in immediate danger.",
        evidence_status: "verified_corpus",
        publication: {
          kind: "official_quote_only",
          renderer_id: "quote",
          review_status: "reviewed",
          support_provenance: "corpus",
        },
      }],
      evidence: [{
        evidence_id: "e1",
        title: "PreparedBC emergency guide",
        publisher: "PreparedBC",
        canonical_url: "https://example.test/preparedbc",
        locator: null,
        temporal_class: "stable_guidance",
        review_provenance: "native_text",
        primary_text: "Call 9-1-1 if you are in immediate danger.",
        context_text: "",
      }],
      limitations: [],
    } as AskResponse;

    render(<AnswerBody response={response} assistantText="" />);
    expect(screen.getByText("Source: PreparedBC emergency guide")).toBeInTheDocument();
  });
});
