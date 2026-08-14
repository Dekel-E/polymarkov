"use client";

import { useEffect, useRef, useState } from "react";
import DeskChat from "@/components/DeskChat";
import DossierView from "@/components/DossierView";
import MarketGrid from "@/components/MarketGrid";
import PipelineProgress from "@/components/PipelineProgress";
import { useAgentRun } from "@/lib/useAgentRun";

const EXAMPLES = [
  "Will the Fed cut interest rates at its next meeting?",
  "Will Bitcoin close above $100k this year?",
  "Who will win the next US presidential election?",
];

export default function Home() {
  const [prompt, setPrompt] = useState("");
  const { running, elapsed, result, fetchError, run, pastRuns } = useAgentRun();
  const resultsRef = useRef<HTMLDivElement | null>(null);
  const consoleRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    if (running) resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [running]);

  return (
    <div className="mx-auto max-w-7xl space-y-14 px-4 py-10 md:px-8">
      {/* hero */}
      <section className="grid items-center gap-8 lg:grid-cols-[1.05fr_1fr]">
        <header className="space-y-5">
          <div
            className="desk-rise inline-flex items-center gap-2 rounded-full border border-desk-line bg-desk-panel/60 px-3 py-1 font-mono text-[11px] uppercase tracking-[0.2em] text-instrument text-glow"
            style={{ "--i": 0 } as React.CSSProperties}
          >
            <span className="h-1.5 w-1.5 rounded-full bg-instrument desk-breathe" />
            live research · paper trading
          </div>
          <h1
            className="desk-rise font-display text-4xl font-bold leading-[1.02] tracking-tight text-balance md:text-6xl"
            style={{ "--i": 1 } as React.CSSProperties}
          >
            Research a market.
            <br />
            <span className="text-desk-dim">See the case for and against.</span>
          </h1>
          <p
            className="desk-rise max-w-lg text-sm leading-relaxed text-desk-soft md:text-base"
            style={{ "--i": 2 } as React.CSSProperties}
          >
            Polymarkov combines live prices, recent evidence, social signals, and four
            analyst views. Deterministic risk rules turn that research into{" "}
            <span className="text-emerald-400">BUY YES</span>, BUY NO, or{" "}
            <span className="text-desk-dim">PASS</span>—with an optional paper trade.
          </p>
          <div
            className="desk-rise flex flex-wrap gap-x-5 gap-y-1 font-mono text-[11px] text-desk-faint"
            style={{ "--i": 3 } as React.CSSProperties}
          >
            <span>8 LLM modules in a full run</span>
            <span>· deterministic pricing</span>
            <span>· paper trading only</span>
          </div>
        </header>

        {/* the console */}
        <section
          className="desk-rise overflow-hidden rounded-2xl border border-desk-edge bg-desk-panel/70 shadow-lift"
          style={{ "--i": 2 } as React.CSSProperties}
        >
          <div className="flex items-center gap-2 border-b border-desk-line px-4 py-2.5 font-mono text-[11px] text-desk-dim">
            <span className="flex gap-1.5">
              <span className="h-2 w-2 rounded-full bg-desk-edge" />
              <span className="h-2 w-2 rounded-full bg-desk-edge" />
              <span className="h-2 w-2 rounded-full bg-instrument/60" />
            </span>
            <span className="ml-1 tracking-wider">agent://console</span>
            <span className="ml-auto text-desk-faint">Market · Focus · Trade</span>
          </div>

          <div className="p-4">
            <div className="flex gap-2">
              <span className="pt-3 font-mono text-sm text-instrument text-glow">›</span>
              <textarea
                ref={consoleRef}
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && prompt.trim()) run(prompt);
                }}
                rows={3}
                placeholder={'Name an active Polymarket market, ask a question, or paste its URL'}
                className="w-full resize-y bg-transparent py-2.5 font-mono text-sm text-desk-ink placeholder-desk-faint focus:outline-none"
              />
            </div>

            <div className="mt-2 flex flex-wrap gap-1.5">
              {EXAMPLES.map((ex) => (
                <button
                  key={ex}
                  onClick={() => {
                    setPrompt(ex);
                    consoleRef.current?.focus();
                  }}
                  className="rounded-lg border border-desk-line bg-desk-deep/60 px-2.5 py-1 text-left font-mono text-[11px] text-desk-dim transition-colors hover:border-instrument/40 hover:text-desk-ink"
                >
                  {ex}
                </button>
              ))}
            </div>

            <div className="mt-4 flex items-center gap-4">
              <button onClick={() => run(prompt)} disabled={running || !prompt.trim()} className="btn-primary px-6">
                {running ? (
                  <>
                    <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-desk-deep/30 border-t-desk-deep" />
                    Running…
                  </>
                ) : (
                  "Run Agent"
                )}
              </button>
              <span className="font-mono text-[11px] text-desk-faint">
                Ctrl/⌘ + Enter · usually under a minute · repeats may use cache
              </span>
            </div>

            {pastRuns.length > 1 && (
              <div className="mt-3 space-y-0.5 border-t border-desk-line/60 pt-2">
                {pastRuns.slice(0, -1).map((r, i) => (
                  <div key={i} className="truncate font-mono text-[11px] text-desk-dim">
                    <span className="text-desk-faint">›</span> {r.prompt} — {r.summary}
                  </div>
                ))}
              </div>
            )}
          </div>
        </section>
      </section>

      <div ref={resultsRef} className="scroll-mt-20">
        {running && (
          <section className="max-w-3xl">
            <PipelineProgress elapsed={elapsed} />
          </section>
        )}
        {(result || fetchError) && !running && (
          <section className="max-w-4xl">
            <DossierView result={result} fetchError={fetchError} appendixOpen />
          </section>
        )}
      </div>

      <DeskChat />

      <section>
        <div className="mb-5 flex items-baseline justify-between">
          <h2 className="font-display text-xl font-bold uppercase tracking-wide">
            Trending markets
          </h2>
          <span className="font-mono text-[11px] text-desk-faint">
            active markets ranked by 24h volume
          </span>
        </div>
        <MarketGrid />
      </section>
    </div>
  );
}
