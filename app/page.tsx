"use client";

import { useEffect, useRef, useState } from "react";
import CouncilCards from "@/components/CouncilCards";
import MarketBrowser from "@/components/MarketBrowser";
import MarketPanel from "@/components/MarketPanel";
import NewsSentiment from "@/components/NewsSentiment";
import SocialPulse from "@/components/SocialPulse";
import StepsTrace from "@/components/StepsTrace";
import Verdict from "@/components/Verdict";
import { executeAgent, fetchMarketDetail } from "@/lib/api";
import type { ExecuteOut, MarketState, MarketSummary } from "@/lib/types";

export default function Home() {
  const [prompt, setPrompt] = useState("");
  const [running, setRunning] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [result, setResult] = useState<ExecuteOut | null>(null);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [selected, setSelected] = useState<MarketState | null>(null);
  const [selectedError, setSelectedError] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const topRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, []);

  async function run(promptOverride?: string) {
    const text = (promptOverride ?? prompt).trim();
    if (!text || running) return;
    setRunning(true);
    setResult(null);
    setFetchError(null);
    setElapsed(0);
    const started = Date.now();
    timerRef.current = setInterval(
      () => setElapsed(Math.floor((Date.now() - started) / 1000)),
      1000,
    );
    try {
      setResult(await executeAgent(text));
    } catch (err) {
      setFetchError(err instanceof Error ? err.message : String(err));
    } finally {
      if (timerRef.current) clearInterval(timerRef.current);
      setRunning(false);
    }
  }

  async function selectMarket(m: MarketSummary) {
    setSelectedError(null);
    setPrompt(`Market: ${m.slug}\nFocus: all\nTrade: no`);
    topRef.current?.scrollIntoView({ behavior: "smooth" });
    try {
      setSelected(await fetchMarketDetail(m.slug));
    } catch (err) {
      setSelected(null);
      setSelectedError(err instanceof Error ? err.message : String(err));
    }
  }

  const ui = result?.ui ?? null;

  return (
    <main className="mx-auto max-w-4xl space-y-8 px-4 py-10">
      <header ref={topRef}>
        <h1 className="text-3xl font-bold tracking-tight">Polymarkov</h1>
        <p className="mt-1 text-sm text-slate-400">
          Pre-trade intelligence dossiers for Polymarket — news, sentiment, AI
          council, deterministic verdict, paper trading. Educational tool, not
          financial advice.
        </p>
      </header>

      <section className="space-y-3">
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          rows={4}
          placeholder={
            'e.g. "Analyze the Fed September rate cut market", paste a Polymarket URL, or pick a market below'
          }
          className="w-full resize-y rounded-lg border border-slate-700 bg-slate-900 p-3 text-sm text-slate-100 placeholder-slate-500 focus:border-sky-500 focus:outline-none"
        />
        <div className="flex items-center gap-4">
          <button
            onClick={() => run()}
            disabled={running || !prompt.trim()}
            className="rounded-lg bg-sky-600 px-5 py-2 text-sm font-semibold text-white transition hover:bg-sky-500 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {running ? "Running…" : "Run Agent"}
          </button>
          {running && (
            <span className="flex items-center gap-2 text-sm text-slate-400">
              <span className="h-3 w-3 animate-spin rounded-full border-2 border-slate-600 border-t-sky-400" />
              {elapsed}s elapsed
            </span>
          )}
        </div>
      </section>

      {selectedError && (
        <div className="rounded-lg border border-amber-800 bg-amber-950/40 p-3 text-sm text-amber-300">
          Could not load market detail: {selectedError}
        </div>
      )}

      {selected && (
        <MarketPanel market={selected} onGenerate={() => run()} running={running} />
      )}

      {fetchError && (
        <div className="rounded-lg border border-red-800 bg-red-950/50 p-4 text-sm text-red-300">
          Request failed: {fetchError}
        </div>
      )}

      {result?.status === "error" && (
        <div className="rounded-lg border border-red-800 bg-red-950/50 p-4 text-sm text-red-300">
          Agent error: {result.error}
        </div>
      )}

      {/* Dossier sections — populated once the pipeline (Phase 5) returns `ui` */}
      {ui?.verdict && <Verdict data={ui.verdict} market={ui.market ?? selected ?? undefined} />}
      {ui?.market && !selected && <MarketPanel market={ui.market} />}
      {ui?.news && <NewsSentiment clusters={ui.news} />}
      {ui?.social && <SocialPulse data={ui.social} />}
      {ui?.council && <CouncilCards council={ui.council} />}

      {ui?.fill && (
        <section className="rounded-lg border border-slate-800 bg-slate-900 p-4 text-sm">
          <h2 className="mb-2 text-lg font-semibold text-slate-200">Paper-trade fill</h2>
          <div className="grid grid-cols-2 gap-2 text-slate-300 sm:grid-cols-3">
            <div>Side: {ui.fill.side}</div>
            <div>Size: ${ui.fill.size_usd.toFixed(2)}</div>
            <div>VWAP: {(ui.fill.vwap * 100).toFixed(1)}%</div>
            <div>Slippage: {ui.fill.slippage_bps.toFixed(1)} bps</div>
            <div>Fee: ${ui.fill.fee_paid.toFixed(2)}</div>
            <div className="truncate">Position: {ui.fill.position_id}</div>
          </div>
        </section>
      )}

      {result?.response && (
        <section>
          <h2 className="mb-3 text-lg font-semibold text-slate-200">Response</h2>
          <div className="whitespace-pre-wrap rounded-lg border border-slate-800 bg-slate-900 p-4 text-sm leading-relaxed text-slate-200">
            {result.response}
          </div>
        </section>
      )}

      {result && <StepsTrace steps={result.steps} />}

      <MarketBrowser onSelect={selectMarket} selectedSlug={selected?.slug ?? null} />
    </main>
  );
}
