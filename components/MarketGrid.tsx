"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import MarketCard from "@/components/MarketCard";
import { fetchMarkets } from "@/lib/api";
import type { MarketSummary } from "@/lib/types";

const CATEGORY_ORDER = [
  "politics",
  "geopolitics",
  "sports",
  "crypto",
  "finance",
  "economics",
  "tech",
  "culture",
  "weather",
  "other",
];

export default function MarketGrid() {
  const [markets, setMarkets] = useState<MarketSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [category, setCategory] = useState<string>("all");

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    fetchMarkets(40)
      .then(setMarkets)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const categories = useMemo(() => {
    const present = new Set(markets.map((m) => m.category || "other"));
    return ["all", ...CATEGORY_ORDER.filter((c) => present.has(c))];
  }, [markets]);

  const visible = useMemo(
    () => (category === "all" ? markets : markets.filter((m) => (m.category || "other") === category)),
    [markets, category],
  );

  return (
    <section>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        {categories.map((c) => (
          <button
            key={c}
            onClick={() => setCategory(c)}
            className={`rounded-full px-3.5 py-1.5 text-xs font-semibold capitalize transition ${
              category === c
                ? "bg-emerald-500 text-zinc-950"
                : "border border-zinc-700 text-zinc-400 hover:border-zinc-500 hover:text-zinc-200"
            }`}
          >
            {c === "all" ? "All markets" : c}
          </button>
        ))}
        <button
          onClick={load}
          disabled={loading}
          className="ml-auto rounded-full border border-zinc-800 px-3 py-1.5 text-xs text-zinc-500 transition hover:border-zinc-600 hover:text-zinc-300 disabled:opacity-40"
          title="Refresh markets"
        >
          {loading ? "Loading…" : "↻ Refresh"}
        </button>
      </div>

      {loading && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-44 animate-pulse rounded-2xl bg-zinc-900" />
          ))}
        </div>
      )}

      {error && !loading && (
        <div className="rounded-xl border border-amber-900/60 bg-amber-950/30 p-4 text-sm text-amber-300">
          Could not load markets: {error}
          {error.includes("500") && (
            <div className="mt-1 text-xs text-amber-400/80">
              In local dev this usually means the FastAPI backend is not running — start it
              with <code className="rounded bg-zinc-900 px-1">npm run dev:api</code>.
            </div>
          )}
          <button
            onClick={load}
            className="mt-2 block rounded-lg bg-amber-900/50 px-3 py-1 text-xs font-semibold text-amber-200 transition hover:bg-amber-800/50"
          >
            Retry
          </button>
        </div>
      )}

      {!loading && !error && visible.length === 0 && (
        <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-5 text-sm text-zinc-400">
          No markets in this category right now.
          <button onClick={load} className="ml-2 text-emerald-400 hover:underline">
            Retry
          </button>
        </div>
      )}

      {!loading && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {visible.map((m) => (
            <MarketCard key={m.id} market={m} />
          ))}
        </div>
      )}
    </section>
  );
}
