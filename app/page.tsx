"use client";

import { useEffect, useRef, useState } from "react";
import DossierView from "@/components/DossierView";
import MarketGrid from "@/components/MarketGrid";
import PipelineProgress from "@/components/PipelineProgress";
import { useAgentRun } from "@/lib/useAgentRun";

export default function Home() {
  const [prompt, setPrompt] = useState("");
  const { running, elapsed, result, fetchError, run } = useAgentRun();
  const resultsRef = useRef<HTMLDivElement | null>(null);

  // bring the progress/results into view when a run starts
  useEffect(() => {
    if (running) resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [running]);

  return (
    <div className="mx-auto max-w-6xl space-y-10 px-4 py-8 md:px-8">
      <header className="pt-2">
        <div className="font-mono text-[11px] uppercase tracking-[0.25em] text-instrument">
          Polymarkov · pre-trade intelligence
        </div>
        <h1 className="mt-2 font-display text-3xl font-bold uppercase leading-none tracking-tight md:text-5xl">
          Every market has a fair price.
          <br />
          <span className="text-desk-dim">The desk finds it.</span>
        </h1>
      </header>

      <section className="max-w-3xl rounded-2xl border border-desk-line bg-desk-panel/60 p-4">
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          rows={3}
          placeholder={'Ask about any market — e.g. "Analyze the Fed September rate cut market" — or paste a Polymarket URL'}
          className="w-full resize-y rounded-xl border border-desk-line bg-desk-deep/80 p-3 text-sm text-desk-ink placeholder-desk-faint focus:border-instrument/60 focus:outline-none"
        />
        <div className="mt-3 flex items-center gap-4">
          <button
            onClick={() => run(prompt)}
            disabled={running || !prompt.trim()}
            className="rounded-xl bg-instrument px-6 py-2 text-sm font-bold text-desk-deep transition hover:bg-instrument-bright disabled:cursor-not-allowed disabled:opacity-40"
          >
            {running ? "Running…" : "Run Agent"}
          </button>
          {!running && (
            <span className="font-mono text-[11px] text-desk-faint">
              typical run ~1 min · repeat runs are cached
            </span>
          )}
        </div>
      </section>

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
