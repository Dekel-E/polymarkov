"use client";

import ReactMarkdown from "react-markdown";

/** Dossier markdown rendered in the desk design language. */
export default function Markdown({ children }: { children: string }) {
  return (
    <ReactMarkdown
      components={{
        h1: ({ children }) => (
          <h1 className="mb-3 mt-1 font-display text-xl font-bold uppercase tracking-wide text-desk-ink">
            {children}
          </h1>
        ),
        h2: ({ children }) => (
          <h2 className="mb-2 mt-5 font-display text-base font-bold uppercase tracking-wide text-desk-ink">
            {children}
          </h2>
        ),
        h3: ({ children }) => (
          <h3 className="mb-1.5 mt-4 text-sm font-bold text-desk-ink">{children}</h3>
        ),
        p: ({ children }) => (
          <p className="mb-3 text-[15px] leading-7 text-desk-soft">{children}</p>
        ),
        ul: ({ children }) => <ul className="mb-3 space-y-1.5 pl-1">{children}</ul>,
        ol: ({ children }) => (
          <ol className="mb-3 list-inside list-decimal space-y-1.5 pl-1 text-[15px] text-desk-soft">
            {children}
          </ol>
        ),
        li: ({ children }) => (
          <li className="flex gap-2 text-[15px] leading-7 text-desk-soft">
            <span className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-instrument" />
            <span className="min-w-0">{children}</span>
          </li>
        ),
        a: ({ href, children }) => (
          <a
            href={href}
            target="_blank"
            rel="noreferrer"
            className="text-instrument underline decoration-instrument/40 underline-offset-2 transition hover:decoration-instrument"
          >
            {children}
          </a>
        ),
        strong: ({ children }) => (
          <strong className="font-semibold text-desk-ink">{children}</strong>
        ),
        em: ({ children }) => <em className="text-desk-soft">{children}</em>,
        hr: () => <hr className="my-4 border-desk-line" />,
        code: ({ children }) => (
          <code className="rounded bg-desk-deep px-1.5 py-0.5 font-mono text-xs text-desk-soft">
            {children}
          </code>
        ),
        blockquote: ({ children }) => (
          <blockquote className="mb-3 border-l-2 border-instrument/50 pl-3 text-sm text-desk-soft">
            {children}
          </blockquote>
        ),
      }}
    >
      {children}
    </ReactMarkdown>
  );
}
