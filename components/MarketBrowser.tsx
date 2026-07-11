"use client";

import { useEffect, useState } from "react";
import { fetchMarkets } from "@/lib/api";
import type { MarketSummary } from "@/lib/types";

function formatVolume(v: number): string {
  if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `$${(v / 1_000).toFixed(0)}k`;
  return `$${v.toFixed(0)}`;
}

export default function MarketBrowser({
  onSelect,
  selectedSlug,
}: {
  onSelect: (market: MarketSummary) => void;
  selectedSlug: string | null;
}) {
  const [markets, setMarkets] = useState<MarketSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchMarkets(20)
      .then(setMarkets)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, []);

  return (
    <section>
      <h2 className="mb-3 text-lg font-semibold text-slate-200">
        Trending markets
        <span className="ml-2 text-xs font-normal text-slate-500">
          top by 24h volume — click one to inspect &amp; generate intel
        </span>
      </h2>

      {loading && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-24 animate-pulse rounded-lg bg-slate-900" />
          ))}
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-amber-800 bg-amber-950/40 p-3 text-sm text-amber-300">
          Could not load markets: {error}
        </div>
      )}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {markets.map((m) => {
          const selected = m.slug === selectedSlug;
          return (
            <button
              key={m.id}
              onClick={() => onSelect(m)}
              className={`flex items-start gap-3 rounded-lg border p-3 text-left transition ${
                selected
                  ? "border-sky-500 bg-sky-950/40"
                  : "border-slate-800 bg-slate-900 hover:border-slate-600"
              }`}
            >
              {m.image ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={m.image}
                  alt=""
                  className="h-10 w-10 shrink-0 rounded-md object-cover"
                />
              ) : (
                <div className="h-10 w-10 shrink-0 rounded-md bg-slate-800" />
              )}
              <div className="min-w-0 flex-1">
                <div className="line-clamp-2 text-sm font-medium text-slate-100">
                  {m.question}
                </div>
                <div className="mt-1 flex items-center gap-3 text-xs text-slate-400">
                  <span className="font-semibold text-emerald-400">
                    {(m.mid * 100).toFixed(0)}% YES
                  </span>
                  <span>{formatVolume(m.volume24h)} / 24h</span>
                  {m.category && m.category !== "other" && (
                    <span className="rounded bg-slate-800 px-1.5 py-0.5">{m.category}</span>
                  )}
                </div>
              </div>
            </button>
          );
        })}
      </div>
    </section>
  );
}
