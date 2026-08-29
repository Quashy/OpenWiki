import { type ReactNode, useMemo } from "react";
import ReactMarkdown, { defaultUrlTransform, type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

export type MarkdownVariant = "wiki" | "chat" | "citation";

export type MarkdownWikiPage = {
  slug: string;
};

export type CitationLinkRenderer = (citationId: number, children: ReactNode) => ReactNode;

export function MarkdownRenderer({
  content,
  variant = "wiki",
  pages = [],
  onOpenSlug,
  renderCitationLink,
}: {
  content: string;
  variant?: MarkdownVariant;
  pages?: MarkdownWikiPage[];
  onOpenSlug?: (slug: string) => void;
  renderCitationLink?: CitationLinkRenderer;
}) {
  const knownSlugs = useMemo(() => new Set(pages.map((page) => page.slug)), [pages]);
  const renderedContent = useMemo(() => normalizeWikiLinks(content), [content]);
  const components = useMemo(
    () => markdownComponents({ knownSlugs, onOpenSlug, renderCitationLink, variant }),
    [knownSlugs, onOpenSlug, renderCitationLink, variant],
  );

  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={components} urlTransform={markdownUrlTransform}>
      {renderedContent}
    </ReactMarkdown>
  );
}

function markdownUrlTransform(url: string) {
  return url.startsWith("wiki:") || url.startsWith("citation:") ? url : defaultUrlTransform(url);
}

function markdownComponents({
  knownSlugs,
  onOpenSlug,
  renderCitationLink,
  variant,
}: {
  knownSlugs: Set<string>;
  onOpenSlug?: (slug: string) => void;
  renderCitationLink?: CitationLinkRenderer;
  variant: MarkdownVariant;
}): Components {
  const compact = variant === "chat" || variant === "citation";
  const citation = variant === "citation";
  return {
    h1: ({ children }) => <h1 className={`${compact ? "mb-2 mt-1 text-base" : "mb-4 mt-1 text-2xl"} font-semibold leading-tight`}>{children}</h1>,
    h2: ({ children }) => (
      <h2 className={`${compact ? "mb-2 mt-4 text-sm" : "mb-3 mt-7 border-b border-divider pb-2 text-lg"} font-semibold`}>
        {children}
      </h2>
    ),
    h3: ({ children }) => <h3 className={`${compact ? "mb-1.5 mt-3 text-sm" : "mb-2 mt-5 text-base"} font-semibold`}>{children}</h3>,
    h4: ({ children }) => <h4 className={`${compact ? "mb-1 mt-2 text-xs" : "mb-2 mt-4 text-sm"} font-semibold text-default-700`}>{children}</h4>,
    p: ({ children }) => <p className={`${citation ? "my-1" : compact ? "my-2" : "my-3 max-w-4xl"} text-sm leading-7 text-default-700`}>{children}</p>,
    ul: ({ children }) => <ul className={`${citation ? "my-1" : compact ? "my-2" : "my-3"} list-disc space-y-1 pl-5 text-sm leading-7 text-default-700`}>{children}</ul>,
    ol: ({ children }) => <ol className={`${citation ? "my-1" : compact ? "my-2" : "my-3"} list-decimal space-y-1 pl-5 text-sm leading-7 text-default-700`}>{children}</ol>,
    li: ({ children }) => <li className="pl-1">{children}</li>,
    blockquote: ({ children }) => <blockquote className={`${compact ? "my-2" : "my-4"} border-l-3 border-default-300 pl-4 text-sm text-default-600`}>{children}</blockquote>,
    strong: ({ children }) => <strong className="font-semibold text-default-900">{children}</strong>,
    em: ({ children }) => <em className="text-default-800">{children}</em>,
    a: ({ href, children }) => {
      if (href?.startsWith("citation:")) {
        const citationId = Number(decodeURIComponent(href.slice(9)));
        if (Number.isFinite(citationId) && renderCitationLink) {
          return <>{renderCitationLink(citationId, children)}</>;
        }
        return <span>{children}</span>;
      }
      if (href?.startsWith("wiki:")) {
        const slug = decodeURIComponent(href.slice(5));
        if (!onOpenSlug || !knownSlugs.has(slug)) {
          return <span className="text-default-500">{children}</span>;
        }
        return (
          <button
            className="inline-flex align-baseline font-medium text-primary underline decoration-primary-200 underline-offset-2 hover:decoration-primary"
            type="button"
            onClick={() => onOpenSlug(slug)}
          >
            {children}
          </button>
        );
      }
      return (
        <a className="font-medium text-primary underline decoration-primary-200 underline-offset-2 hover:decoration-primary" href={href} target="_blank" rel="noreferrer">
          {children}
        </a>
      );
    },
    code: ({ className, children }) => (
      <code className={`${className ?? ""} rounded-sm bg-default-100 px-1.5 py-0.5 font-mono text-[0.85em] text-default-800`}>
        {children}
      </code>
    ),
    pre: ({ children }) => (
      <pre className={`${compact ? "my-2" : "my-4"} overflow-x-auto rounded-md border border-divider bg-default-100 p-3 text-sm leading-6 text-default-800`}>
        {children}
      </pre>
    ),
    table: ({ children }) => (
      <div className={`${compact ? "my-2" : "my-4"} overflow-x-auto rounded-md border border-divider`}>
        <table className="min-w-full border-collapse text-sm">{children}</table>
      </div>
    ),
    thead: ({ children }) => <thead className="bg-default-100 text-default-700">{children}</thead>,
    th: ({ children }) => <th className="border-b border-divider px-3 py-2 text-left font-semibold">{children}</th>,
    td: ({ children }) => <td className="border-b border-divider px-3 py-2 align-top text-default-700">{children}</td>,
  };
}

export function normalizeWikiLinks(content: string) {
  return content.replace(/\[\[([^|\]\r\n]+)\|([^\]\r\n]+)\]\]/g, (_, slug: string, label: string) => {
    return `[${escapeMarkdownLinkText(label)}](wiki:${encodeURIComponent(slug.trim())})`;
  });
}

function escapeMarkdownLinkText(value: string) {
  return value.replace(/([\\[\]])/g, "\\$1");
}
