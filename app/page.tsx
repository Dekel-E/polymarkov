"use client";

import { useState } from "react";
import DossierView from "@/components/DossierView";
import MarketGrid from "@/components/MarketGrid";
import { useAgentRun } from "@/lib/useAgentRun";

export default function Home() {
  const [prompt, setPrompt] = useState("");
  const { running, elapsed, result, fetchError, run } = useAgentRun();

  return (
    <div className="mx-auto max-w-6xl space-y-10 px-4 py-8 md:px-8">
      <header className="pt-2 text-center">
        <h1 className="text-3xl font-bold tracking-tight md:text-4xl">
          Market <span className="text-emerald-400">intelligence</span>, on demand
        </h1>
        <p className="mx-auto mt-2 max-w-xl text-sm text-zinc-400">
          AI-built pre-trade dossiers for any Polymarket market — live news, social
          sentiment, a four-analyst AI council, and a deterministic fair-value verdict.
        </p>
      </header>

      <section className="mx-auto max-w-3xl rounded-2xl border border-zinc-800 bg-zinc-900/60 p-4 shadow-xl shadow-black/20">
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          rows={3}
          placeholder={'Ask about any market — e.g. "Analyze the Fed September rate cut market" — or paste a Polymarket URL'}
          className="w-full resize-y rounded-xl border border-zinc-800 bg-zinc-950/80 p-3 text-sm text-zinc-100 placeholder-zinc-600 focus:border-emerald-500/60 focus:outline-none"
        />
        <div className="mt-3 flex items-center gap-4">
          <button
            onClick={() => run(prompt)}
            disabled={running || !prompt.trim()}
            className="rounded-xl bg-emerald-500 px-6 py-2 text-sm font-bold text-zinc-950 transition hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {running ? "Running…" : "Run Agent"}
          </button>
          {running && (
            <span className="flex items-center gap-2 text-sm text-zinc-400">
              <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-zinc-700 border-t-emerald-400" />
              {elapsed}s — gathering evidence, convening the council…
            </span>
          )}
          {!running && (
            <span className="text-xs text-zinc-600">Typical run: ~1 minute</span>
          )}
        </div>
      </section>

      {(result || fetchError) && (
        <section className="mx-auto max-w-4xl">
          <DossierView result={result} fetchError={fetchError} />
        </section>
      )}

      <section>
        <div className="mb-4 flex items-baseline justify-between">
          <h2 className="text-xl font-bold tracking-tight">Trending markets</h2>
          <span className="text-xs text-zinc-500">top by 24h volume, live from Polymarket</span>
        </div>
        <MarketGrid />
      </section>
    </div>
  );
}
