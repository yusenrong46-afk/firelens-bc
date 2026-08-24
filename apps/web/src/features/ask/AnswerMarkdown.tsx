import type { ComponentPropsWithoutRef, ReactNode } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

const MARKDOWN_ELEMENTS = [
  "a",
  "blockquote",
  "br",
  "code",
  "del",
  "em",
  "h1",
  "h2",
  "h3",
  "h4",
  "h5",
  "h6",
  "hr",
  "input",
  "li",
  "ol",
  "p",
  "pre",
  "strong",
  "table",
  "tbody",
  "td",
  "th",
  "thead",
  "tr",
  "ul",
] as const;

type HeadingContext = "lead" | "section";

function isAllowedAnswerLink(href: string): boolean {
  const trimmed = href.trim();

  // The browser strips ASCII controls from URLs while resolving a scheme.  A
  // seemingly schemeless `java\nscript:` link would therefore become a
  // `javascript:` URL at click time.  React Markdown also decodes character
  // entities before this function receives a destination, so reject controls
  // before classifying a URL rather than attempting to normalize them.
  if (
    !trimmed
    || /[\u0000-\u0020\u007f-\u009f]/.test(trimmed)
    || trimmed.startsWith("//")
    || trimmed.startsWith("\\\\")
  ) {
    return false;
  }

  if (trimmed.startsWith("#") || trimmed.startsWith("/") || trimmed.startsWith("./") || trimmed.startsWith("../") || trimmed.startsWith("?")) {
    return true;
  }

  if (/^[a-z][a-z\d+.-]*:/i.test(trimmed)) {
    try {
      const parsed = new URL(trimmed);
      return (
        parsed.protocol === "https:"
        && Boolean(parsed.hostname)
        && !parsed.username
        && !parsed.password
      );
    } catch {
      return false;
    }
  }

  return !trimmed.startsWith("\\");
}

function strictAnswerUrlTransform(href: string): string {
  const trimmed = href.trim();
  return isAllowedAnswerLink(trimmed) ? trimmed : "";
}

function SafeSourceLink({ href, children, ...props }: ComponentPropsWithoutRef<"a">) {
  const safeHref = href?.trim();
  if (!safeHref || !isAllowedAnswerLink(safeHref)) {
    return <span>{children}</span>;
  }

  const isExternal = /^https:\/\//i.test(safeHref);

  return (
    <a
      {...props}
      href={safeHref}
      {...(isExternal ? { rel: "noopener noreferrer", target: "_blank" } : {})}
    >
      {children}
    </a>
  );
}

function MarkdownTable({ children, ...props }: ComponentPropsWithoutRef<"table">) {
  return (
    <div
      aria-label="Scrollable answer table"
      className="answer-markdown__table-scroll"
      role="region"
      tabIndex={0}
    >
      <table {...props}>{children}</table>
    </div>
  );
}

function SectionMarkdownHeading({ children }: { children?: ReactNode }) {
  return <h3 className="answer-markdown__heading">{children}</h3>;
}

function LeadMarkdownHeading({ children }: { children?: ReactNode }) {
  return <p className="answer-markdown__heading">{children}</p>;
}

const sharedComponents: Components = {
  a: ({ node: _node, ...props }) => <SafeSourceLink {...props} />,
  table: ({ node: _node, ...props }) => <MarkdownTable {...props} />,
};

const leadComponents: Components = {
  ...sharedComponents,
  h1: LeadMarkdownHeading,
  h2: LeadMarkdownHeading,
  h3: LeadMarkdownHeading,
  h4: LeadMarkdownHeading,
  h5: LeadMarkdownHeading,
  h6: LeadMarkdownHeading,
};

const sectionComponents: Components = {
  ...sharedComponents,
  h1: SectionMarkdownHeading,
  h2: SectionMarkdownHeading,
  h3: SectionMarkdownHeading,
  h4: SectionMarkdownHeading,
  h5: SectionMarkdownHeading,
  h6: SectionMarkdownHeading,
};

const componentsForContext: Record<HeadingContext, Components> = {
  lead: leadComponents,
  section: sectionComponents,
};

export function AnswerMarkdown({
  children,
  className,
  headingContext = "lead",
}: {
  children: string;
  className?: string;
  headingContext?: HeadingContext;
}) {
  return (
    <div className={["answer-markdown", className].filter(Boolean).join(" ")}>
      <ReactMarkdown
        allowedElements={[...MARKDOWN_ELEMENTS]}
        components={componentsForContext[headingContext]}
        remarkPlugins={[remarkGfm]}
        skipHtml
        urlTransform={strictAnswerUrlTransform}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
