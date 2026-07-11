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
  "economics",
  "finance",
  "tech",
  "culture",
  "weather",
  "other",
];

const CATEGORY_LABELS: Record<string, string> = {
  politics: "Politics",
  geopolitics: "Geopolitics",
  sports: "Sports",
  crypto: "Crypto",
  economics: "Economics",
  finance: "Finance",
  tech: "Tech",
  culture: "Culture",
  weather: "Weather",
  other: "Everything else",
};

export default function MarketGrid() {
  const [markets, setMarkets] = useState<MarketSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [category, setCategory] = useState<string>("all");

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    fetchMarkets(90)
      .then(setMarkets)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const grouped = useMemo(() => {
    const byCategory = new Map<string, MarketSummary[]>();
    for (const m of markets) {
      const c = m.category || "other";
      byCategory.set(c, [...(byCategory.get(c) ?? []), m]);
    }
    return CATEGORY_ORDER.filter((c) => byCategory.has(c)).map((c) => ({
      category: c,
      markets: byCategory.get(c)!,
    }));
  }, [markets]);

  const chips = useMemo(() => ["all", ...grouped.map((g) => g.category)], [grouped]);
  const flat = useMemo(
    () => (category === "all" ? [] : markets.filter((m) => (m.category || "other") === category)),
    [markets, category],
  );

  return (
    <section>
      <div className="mb-5 flex flex-wrap items-center gap-2">
        {chips.map((c) => (
          <button
            key={c}
            onClick={() => setCategory(c)}
            className={`rounded-full px-3.5 py-1.5 text-xs font-semibold transition ${
              category === c
                ? "bg-instrument text-desk-deep"
                : "border border-desk-edge text-desk-dim hover:border-desk-dim hover:text-desk-ink"
            }`}
          >
            {c === "all" ? "All" : CATEGORY_LABELS[c] ?? c}
            {c !== "all" && (
              <span className="ml-1.5 font-mono text-[10px] opacity-70">
                {grouped.find((g) => g.category === c)?.markets.length}
              </span>
            )}
          </button>
        ))}
        <button
          onClick={load}
          disabled={loading}
          className="ml-auto rounded-full border border-desk-line px-3 py-1.5 text-xs text-desk-dim transition hover:border-desk-edge hover:text-desk-soft disabled:opacity-40"
          title="Refresh markets"
        >
          {loading ? "Loading…" : "↻ Refresh"}
        </button>
      </div>

      {loading && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-44 animate-pulse rounded-2xl bg-desk-panel" />
          ))}
        </div>
      )}

      {error && !loading && (
        <div className="rounded-xl border border-amber-900/60 bg-amber-950/30 p-4 text-sm text-amber-300">
          Could not load markets: {error}
          {error.includes("500") && (
            <div className="mt-1 text-xs text-amber-400/80">
              In local dev this usually means the FastAPI backend is not running — start it
              with <code className="rounded bg-desk-deep px-1">npm run dev:api</code>.
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

      {!loading && !error && markets.length === 0 && (
        <div className="rounded-xl border border-desk-line bg-desk-panel p-5 text-sm text-desk-dim">
          No markets returned from Polymarket right now.
          <button onClick={load} className="ml-2 text-instrument hover:underline">
            Retry
          </button>
        </div>
      )}

      {/* grouped by category (All) */}
      {!loading && category === "all" && (
        <div className="space-y-10">
          {grouped.map(({ category: c, markets: group }) => (
            <div key={c}>
              <div className="mb-3 flex items-baseline gap-3 border-b border-desk-line pb-2">
                <h3 className="font-display text-lg font-bold uppercase tracking-wide text-desk-ink">
                  {CATEGORY_LABELS[c] ?? c}
                </h3>
                <span className="font-mono text-[11px] text-desk-faint">
                  {group.length} market{group.length === 1 ? "" : "s"}
                </span>
                {group.length > 6 && (
                  <button
                    onClick={() => setCategory(c)}
                    className="ml-auto font-mono text-[11px] uppercase tracking-wider text-instrument hover:underline"
                  >
                    view all →
                  </button>
                )}
              </div>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
                {group.slice(0, 6).map((m) => (
                  <MarketCard key={m.id} market={m} />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* single category (flat) */}
      {!loading && category !== "all" && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {flat.map((m) => (
            <MarketCard key={m.id} market={m} />
          ))}
        </div>
      )}
    </section>
  );
}
