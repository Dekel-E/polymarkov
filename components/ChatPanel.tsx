"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import Markdown from "@/components/Markdown";

/**
 * Shared chat scaffold for DeskChat / MarketChat / StrategyChat: message
 * state, history snapshotting, scroll, bubbles, input row. Variants supply
 * the transport (`send`) and optional extras renderers for assistant
 * bubbles (market links, gathered badges, citations, applied diffs).
 */

export interface ChatTransportResult<E> {
  content: string;
  extras?: E;
}

interface ChatMessage<E> {
  role: "user" | "assistant";
  content: string;
  extras?: E;
}

export default function ChatPanel<E>({
  title,
  hint,
  emptyText,
  placeholder,
  busyLabel = "thinking…",
  footer = "educational tool · paper trading only · not financial advice",
  sendLabel = "Ask",
  send,
  renderExtrasTop,
  renderExtrasBottom,
}: {
  title: string;
  hint: string;
  emptyText: ReactNode;
  placeholder: string;
  busyLabel?: string;
  footer?: string;
  sendLabel?: string;
  send: (
    question: string,
    history: { role: "user" | "assistant"; content: string }[],
  ) => Promise<ChatTransportResult<E>>;
  renderExtrasTop?: (extras: E) => ReactNode;
  renderExtrasBottom?: (extras: E) => ReactNode;
}) {
  const [messages, setMessages] = useState<ChatMessage<E>[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, busy]);

  async function handleSend() {
    const question = input.trim();
    if (!question || busy) return;
    setInput("");
    setError(null);
    setBusy(true);
    const history = messages.map((m) => ({ role: m.role, content: m.content }));
    setMessages((prev) => [...prev, { role: "user", content: question }]);
    try {
      const res = await send(question, history);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: res.content, extras: res.extras },
      ]);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="rounded-2xl border border-desk-line bg-desk-panel/60 p-4">
      <div className="flex items-baseline justify-between gap-4">
        <h2 className="text-sm font-bold uppercase tracking-wider text-desk-dim">{title}</h2>
        <span className="font-mono text-[10px] text-desk-faint">{hint}</span>
      </div>

      {messages.length === 0 && <p className="mt-2 text-xs text-desk-dim">{emptyText}</p>}

      {messages.length > 0 && (
        <div ref={scrollRef} className="mt-4 max-h-96 space-y-3 overflow-y-auto pr-1">
          {messages.map((m, i) =>
            m.role === "user" ? (
              <div key={i} className="flex justify-end">
                <div className="max-w-[85%] rounded-xl rounded-br-sm bg-instrument/15 px-3 py-2 text-sm text-desk-ink">
                  {m.content}
                </div>
              </div>
            ) : (
              <div key={i} className="flex justify-start">
                <div className="max-w-[92%] rounded-xl rounded-bl-sm border border-desk-line bg-desk-deep/60 px-3 py-2">
                  {m.extras !== undefined && renderExtrasTop?.(m.extras)}
                  <div className="text-sm text-desk-ink">
                    <Markdown>{m.content}</Markdown>
                  </div>
                  {m.extras !== undefined && renderExtrasBottom?.(m.extras)}
                </div>
              </div>
            ),
          )}
          {busy && (
            <div className="flex justify-start">
              <div className="rounded-xl rounded-bl-sm border border-desk-line bg-desk-deep/60 px-3 py-2 font-mono text-xs text-desk-dim">
                {busyLabel}
              </div>
            </div>
          )}
        </div>
      )}

      {error && (
        <div className="mt-3 rounded-lg border border-red-900/60 bg-red-950/40 px-3 py-2 text-xs text-red-300">
          {error}
        </div>
      )}

      <div className="mt-4 flex items-end gap-2">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
          rows={1}
          maxLength={600}
          placeholder={placeholder}
          className="min-h-[38px] flex-1 resize-y rounded-xl border border-desk-line bg-desk-deep/80 px-3 py-2 text-sm text-desk-ink placeholder-desk-faint focus:border-instrument/60 focus:outline-none"
        />
        <button
          onClick={handleSend}
          disabled={busy || !input.trim()}
          className="rounded-xl bg-instrument px-4 py-2 text-sm font-bold text-desk-deep transition hover:bg-instrument-bright disabled:cursor-not-allowed disabled:opacity-40"
        >
          {busy ? "…" : sendLabel}
        </button>
      </div>
      <p className="mt-2 font-mono text-[10px] text-desk-faint">{footer}</p>
    </section>
  );
}

/** Shared "searched fresh intel" badge (DeskChat + MarketChat). */
export function GatheredBadge({
  gathered,
}: {
  gathered?: { searched: boolean; articles: number; articles_indexed: number; social_posts: number };
}) {
  if (!gathered?.searched) return null;
  return (
    <div className="mb-1.5 font-mono text-[10px] uppercase tracking-wider text-instrument">
      searched fresh intel · {gathered.articles} article{gathered.articles === 1 ? "" : "s"}
      {gathered.articles_indexed > 0 && ` (${gathered.articles_indexed} indexed)`}
      {gathered.social_posts > 0 && ` · ${gathered.social_posts} social posts`}
    </div>
  );
}

/** Shared citations list (DeskChat + MarketChat). */
export function CitationsList({ citations }: { citations?: { title: string; url: string }[] }) {
  if (!citations || citations.length === 0) return null;
  return (
    <div className="mt-2 space-y-0.5 border-t border-desk-line/60 pt-1.5">
      {citations.map((c, j) => (
        <a
          key={j}
          href={c.url}
          target="_blank"
          rel="noreferrer"
          className="block truncate font-mono text-[10px] text-desk-dim transition hover:text-instrument"
        >
          ↗ {c.title || c.url}
        </a>
      ))}
    </div>
  );
}
