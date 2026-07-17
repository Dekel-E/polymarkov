"use client";

import { useEffect, useRef, useState } from "react";
import DeskChat from "@/components/DeskChat";
import DossierView from "@/components/DossierView";
import MarketGrid from "@/components/MarketGrid";
import PipelineProgress from "@/components/PipelineProgress";
import { useAgentRun } from "@/lib/useAgentRun";

export default function Home() {
  const [prompt, setPrompt] = useState("");
  const { running, elapsed, result, fetchError, run, pastRuns } = useAgentRun();
  const resultsRef = useRef<HTMLDivElement | null>(null);

  // bring the progress/results into view when a run starts
  useEffect(() => {
    if (running) resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [running]);

  return (
    <div className="mx-auto max-w-6xl space-y-10 px-4 py-8 md:px-8">
      <header className="pt-2">
        <div className="desk-rise flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.25em] text-instrument text-glow" style={{ "--i": 0 } as React.CSSProperties}>
          <span className="h-1.5 w-1.5 rounded-full bg-instrument desk-breathe" />
          Polymarkov · pre-trade intelligence
        </div>
        <h1 className="desk-rise mt-3 font-display text-3xl font-bold uppercase leading-none tracking-tight text-balance md:text-5xl" style={{ "--i": 1 } as React.CSSProperties}>
          Every market has a fair price.
          <br />
          <span className="text-desk-dim">The desk finds it.</span>
        </h1>
      </header>

      <section className="desk-rise max-w-3xl rounded-2xl border border-desk-line bg-desk-panel/60 p-4" style={{ "--i": 2 } as React.CSSProperties}>
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          rows={3}
          placeholder={'Ask about any market — e.g. "Analyze the Fed September rate cut market" — or paste a Polymarket URL'}
          className="w-full resize-y rounded-xl border border-desk-line bg-desk-deep/80 p-3 text-sm text-desk-ink placeholder-desk-faint focus:border-instrument/60 focus:outline-none"
        />
        <div className="mt-3 flex items-center gap-4">
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
          {!running && (
            <span className="font-mono text-[11px] text-desk-faint">
              typical run ~1 min · repeat runs are cached · follow-ups welcome
            </span>
          )}
        </div>

        {pastRuns.length > 1 && (
          <div className="mt-3 border-t border-desk-line/60 pt-2">
            <div className="mb-1 font-mono text-[10px] uppercase tracking-widest text-desk-faint">
              this session
            </div>
            {pastRuns.slice(0, -1).map((r, i) => (
              <div key={i} className="truncate font-mono text-[11px] text-desk-dim">
                <span className="text-desk-faint">›</span> {r.prompt} — {r.summary}
              </div>
            ))}
          </div>
        )}
      </section>

      <DeskChat />

      <div ref={resultsRef} className="scroll-mt-4">
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

      <section>
        <div className="mb-4 flex items-baseline justify-between">
          <h2 className="font-display text-xl font-bold uppercase tracking-wide">
            Trending markets
          </h2>
          <span className="font-mono text-[11px] text-desk-faint">
            top by 24h volume · live from Polymarket
          </span>
        </div>
        <MarketGrid />
      </section>
    </div>
  );
}
