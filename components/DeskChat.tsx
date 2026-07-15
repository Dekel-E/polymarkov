"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import Markdown from "@/components/Markdown";
import { deskChat, type DeskChatResult } from "@/lib/api";

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  citations?: { title: string; url: string }[];
  gathered?: DeskChatResult["gathered"];
  market?: { slug: string; question: string } | null;
}

export default function DeskChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, busy]);

  async function send() {
    const question = input.trim();
    if (!question || busy) return;
    setInput("");
    setError(null);
    setBusy(true);
    const history = messages.map((m) => ({ role: m.role, content: m.content }));
    setMessages((prev) => [...prev, { role: "user", content: question }]);
    try {
      const res = await deskChat(question, history);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: res.answer ?? "(no answer)",
          citations: res.citations,
          gathered: res.gathered,
          market: res.market,
        },
      ]);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="max-w-3xl rounded-2xl border border-desk-line bg-desk-panel/60 p-4">
      <div className="flex items-baseline justify-between gap-4">
        <h2 className="text-sm font-bold uppercase tracking-wider text-desk-dim">Ask the desk</h2>
        <span className="font-mono text-[10px] text-desk-faint">
          markets · portfolio · what the agent can do
        </span>
      </div>

      {messages.length === 0 && (
        <p className="mt-2 text-xs text-desk-dim">
          Talk to the agent about anything it knows: a market (&ldquo;what&apos;s the
          latest on the Fed cutting in September?&rdquo;), the paper portfolio
          (&ldquo;what did you trade today?&rdquo;), or itself (&ldquo;what can you
          do?&rdquo;). It searches and indexes fresh sources when a question needs them.
        </p>
      )}

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
                  {m.market && (
                    <Link
                      href={`/market/${m.market.slug}`}
                      className="mb-1.5 block truncate font-mono text-[10px] uppercase tracking-wider text-instrument hover:underline"
                    >
                      ↳ {m.market.question}
                    </Link>
                  )}
                  {m.gathered?.searched && (
                    <div className="mb-1.5 font-mono text-[10px] uppercase tracking-wider text-instrument">
                      searched fresh intel · {m.gathered.articles} article
                      {m.gathered.articles === 1 ? "" : "s"}
                      {m.gathered.articles_indexed > 0 && ` (${m.gathered.articles_indexed} indexed)`}
                      {m.gathered.social_posts > 0 && ` · ${m.gathered.social_posts} social posts`}
                    </div>
                  )}
                  <div className="text-sm text-desk-ink">
                    <Markdown>{m.content}</Markdown>
                  </div>
                  {m.citations && m.citations.length > 0 && (
                    <div className="mt-2 space-y-0.5 border-t border-desk-line/60 pt-1.5">
                      {m.citations.map((c, j) => (
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
                  )}
                </div>
              </div>
            ),
          )}
          {busy && (
            <div className="flex justify-start">
              <div className="rounded-xl rounded-bl-sm border border-desk-line bg-desk-deep/60 px-3 py-2 font-mono text-xs text-desk-dim">
                thinking — may search &amp; index sources…
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
              send();
            }
          }}
          rows={1}
          maxLength={600}
          placeholder="Ask about a market, the portfolio, or the agent…"
          className="min-h-[38px] flex-1 resize-y rounded-xl border border-desk-line bg-desk-deep/80 px-3 py-2 text-sm text-desk-ink placeholder-desk-faint focus:border-instrument/60 focus:outline-none"
        />
        <button
          onClick={send}
          disabled={busy || !input.trim()}
          className="rounded-xl bg-instrument px-4 py-2 text-sm font-bold text-desk-deep transition hover:bg-instrument-bright disabled:cursor-not-allowed disabled:opacity-40"
        >
          {busy ? "…" : "Ask"}
        </button>
      </div>
      <p className="mt-2 font-mono text-[10px] text-desk-faint">
        educational tool · paper trading only · not financial advice
      </p>
    </section>
  );
}
