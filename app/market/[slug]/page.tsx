"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import DossierView from "@/components/DossierView";
import Markdown from "@/components/Markdown";
import MarketChat from "@/components/MarketChat";
import MarketNews from "@/components/MarketNews";
import PipelineProgress from "@/components/PipelineProgress";
import ProbabilityGauge from "@/components/ProbabilityGauge";
import Sparkline from "@/components/Sparkline";
import TradePanel from "@/components/TradePanel";
import { fetchMarketDetail, fetchWatchlist, setWatched } from "@/lib/api";
import type { MarketState } from "@/lib/types";
import { useAgentRun } from "@/lib/useAgentRun";

const pct = (v: number | null | undefined) =>
  v === null || v === undefined ? "—" : `${(v * 100).toFixed(1)}%`;

function cachedAge(iso: string): string {
  const mins = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 60_000));
  return mins === 0 ? "just now" : `${mins}m ago`;
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="font-mono text-[10px] uppercase tracking-widest text-desk-faint">
        {label}
      </div>
      <div className="mt-0.5 font-mono text-sm font-semibold text-desk-ink">{value}</div>
    </div>
  );
}

export default function MarketPage() {
  const { slug } = useParams<{ slug: string }>();
  const [market, setMarket] = useState<MarketState | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [watched, setWatchedState] = useState(false);
  const { running, elapsed, result, fetchError, run } = useAgentRun();

  useEffect(() => {
    if (!slug) return;
    fetchMarketDetail(slug)
      .then(setMarket)
      .catch((e) => setLoadError(e instanceof Error ? e.message : String(e)));
  }, [slug]);

  useEffect(() => {
    if (!slug) return;
    fetchWatchlist()
      .then((items) => setWatchedState(items.some((i) => i.market_id === slug)))
      .catch(() => undefined);
  }, [slug]);

  function toggleWatch() {
    const next = !watched;
    setWatchedState(next);
    setWatched(slug, next).catch(() => setWatchedState(!next));
  }

  const ui = result?.status === "ok" ? result.ui : null;
  const fairValue = ui?.verdict?.fair_probability ?? null;

  return (
    <div className="mx-auto max-w-4xl space-y-6 px-4 py-8 md:px-8">
      <Link
        href="/"
        className="inline-flex items-center gap-1.5 font-mono text-xs uppercase tracking-wider text-desk-dim transition hover:text-desk-ink"
      >
        ← markets
      </Link>

      {loadError && (
        <div className="rounded-xl border border-amber-900/60 bg-amber-950/30 p-4 text-sm text-amber-300">
          Could not load this market: {loadError}
        </div>
      )}

      {!market && !loadError && <div className="h-64 animate-pulse rounded-2xl bg-desk-panel" />}

      {market && (
        <section className="rounded-2xl border border-desk-line bg-desk-panel/70">
          {/* case-file bar */}
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-desk-line px-5 py-2.5 font-mono text-[11px] uppercase tracking-wider text-desk-dim">
            <span className="text-instrument">case file</span>
            <span className="truncate">{market.slug}</span>
            <span>· {market.category}</span>
            {market.end_date && (
              <span>· ends {new Date(market.end_date).toLocaleDateString()}</span>
            )}
            {ui?.cached_at && (
              <span className="rounded border border-instrument/50 px-1.5 py-px text-instrument">
                cached {cachedAge(ui.cached_at)}
              </span>
            )}
            <span className="ml-auto flex items-center gap-3">
              <button
                onClick={toggleWatch}
                aria-label={watched ? "Remove from watchlist" : "Add to watchlist"}
                title={watched ? "Remove from watchlist" : "Add to watchlist"}
                className={`flex items-center gap-1.5 transition ${
                  watched ? "text-instrument" : "text-desk-dim hover:text-instrument"
                }`}
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill={watched ? "currentColor" : "none"} stroke="currentColor" strokeWidth="1.8">
                  <path d="M12 3l2.7 5.7 6.3.8-4.6 4.3 1.2 6.2L12 17l-5.6 3 1.2-6.2L3 9.5l6.3-.8L12 3Z" />
                </svg>
                {watched ? "watching" : "watch"}
              </button>
              <a
                href={`https://polymarket.com/market/${market.slug}`}
                target="_blank"
                rel="noreferrer"
                className="text-desk-dim transition hover:text-instrument"
              >
                polymarket ↗
              </a>
            </span>
          </div>

          <div className="space-y-6 p-5">
            <h1 className="font-display text-2xl font-bold leading-tight tracking-tight text-desk-ink md:text-3xl">
              {market.question}
            </h1>

            {/* the instrument */}
            <ProbabilityGauge market={market.mid} fair={fairValue} />

            <div className="flex flex-wrap items-end justify-between gap-5 border-t border-desk-line pt-4">
              <div className="grid grid-cols-3 gap-x-7 gap-y-3 sm:grid-cols-5">
                <Stat label="bid" value={pct(market.best_bid)} />
                <Stat label="ask" value={pct(market.best_ask)} />
                <Stat label="spread" value={pct(market.spread)} />
                <Stat
                  label="ask depth"
                  value={`$${Math.round(market.depth_at_ask_usd).toLocaleString()}`}
                />
                <Stat
                  label="vol 24h"
                  value={`$${Math.round(market.volume24h).toLocaleString()}`}
                />
              </div>
              <div>
                <div className="mb-1 font-mono text-[10px] uppercase tracking-widest text-desk-faint">
                  7-day price
                </div>
                <Sparkline points={market.price_history_7d} width={220} height={44} />
              </div>
            </div>

            {!result && !running && (
              <button
                onClick={() => run(`Market: ${slug}\nFocus: all\nTrade: no`)}
                className="rounded-xl bg-instrument px-6 py-2.5 text-sm font-bold text-desk-deep transition hover:bg-instrument-bright"
              >
                Generate intel
              </button>
            )}
          </div>
        </section>
      )}

      {market?.resolution_criteria && (
        <details className="group rounded-xl border border-desk-line bg-desk-panel/60">
          <summary className="cursor-pointer select-none px-4 py-3 font-mono text-xs font-semibold uppercase tracking-wider text-desk-dim transition hover:text-desk-ink">
            resolution terms
          </summary>
          <div className="border-t border-desk-line px-4 py-3">
            <Markdown>{market.resolution_criteria}</Markdown>
          </div>
        </details>
      )}

      {/* related headlines until the dossier's scored exhibits take over */}
      {!ui?.news?.length && <MarketNews slug={slug} />}

      {running && <PipelineProgress elapsed={elapsed} />}

      <DossierView result={result} fetchError={fetchError} liveMarket={market} />

      {result?.status === "ok" && result.ui && <TradePanel slug={slug} ui={result.ui} />}

      {/* grounded Q&A: the agent answers from its dossier and gathers +
          indexes fresh news/social evidence when the question needs it */}
      <MarketChat slug={slug} />
    </div>
  );
}
