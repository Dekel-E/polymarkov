"use client";

import type { MarketState } from "@/lib/types";

function Sparkline({ points }: { points: [number, number][] }) {
  if (points.length < 2) return null;
  const w = 260;
  const h = 48;
  const prices = points.map(([, p]) => p);
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const range = max - min || 1;
  const path = points
    .map(([, p], i) => {
      const x = (i / (points.length - 1)) * w;
      const y = h - ((p - min) / range) * (h - 6) - 3;
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  const rising = prices[prices.length - 1] >= prices[0];
  return (
    <svg width={w} height={h} className="overflow-visible">
      <path d={path} fill="none" stroke={rising ? "#34d399" : "#f87171"} strokeWidth="1.5" />
    </svg>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[11px] uppercase tracking-wide text-desk-dim">{label}</div>
      <div className="text-sm font-semibold text-desk-ink">{value}</div>
    </div>
  );
}

const pct = (v: number | null | undefined) =>
  v === null || v === undefined ? "n/a" : `${(v * 100).toFixed(1)}%`;

export default function MarketPanel({
  market,
  onGenerate,
  running,
}: {
  market: MarketState;
  onGenerate?: () => void;
  running?: boolean;
}) {
  return (
    <section className="rounded-2xl border border-desk-line bg-desk-panel/70 p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <h1 className="text-lg font-bold leading-snug text-desk-ink">{market.question}</h1>
          <div className="mt-1.5 text-xs text-desk-dim">
            <span className="capitalize">{market.category}</span>
            {" | ends "}
            {market.end_date ? new Date(market.end_date).toLocaleDateString() : "n/a"}
            {" | "}
            <a
              href={`https://polymarket.com/market/${market.slug}`}
              target="_blank"
              rel="noreferrer"
              className="text-instrument hover:underline"
            >
              view on Polymarket
            </a>
          </div>
        </div>
        {onGenerate && (
          <button
            onClick={onGenerate}
            disabled={running}
            className="rounded-xl bg-instrument px-5 py-2.5 text-sm font-bold text-desk-deep transition hover:bg-instrument-bright disabled:cursor-not-allowed disabled:opacity-40"
          >
            {running ? "Generating…" : "Generate intel"}
          </button>
        )}
      </div>

      <div className="mt-5 flex flex-wrap items-end justify-between gap-4">
        <div className="grid grid-cols-3 gap-x-6 gap-y-3 sm:grid-cols-6">
          <Stat label="Mid" value={pct(market.mid)} />
          <Stat label="Bid" value={pct(market.best_bid)} />
          <Stat label="Ask" value={pct(market.best_ask)} />
          <Stat label="Spread" value={pct(market.spread)} />
          <Stat
            label="Ask depth"
            value={`$${Math.round(market.depth_at_ask_usd).toLocaleString()}`}
          />
          <Stat label="Vol 24h" value={`$${Math.round(market.volume24h).toLocaleString()}`} />
        </div>
        <div>
          <div className="mb-1 text-[11px] uppercase tracking-wide text-desk-dim">
            7-day price
          </div>
          <Sparkline points={market.price_history_7d} />
        </div>
      </div>
    </section>
  );
}
