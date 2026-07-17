"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import MarketCard from "@/components/MarketCard";
import { fetchMarkets, fetchWatchlist, searchMarkets, setWatched } from "@/lib/api";
import type { MarketSummary } from "@/lib/types";

// Trending markets to pull; server caps at 300.
const MARKETS_TO_FETCH = 200;

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
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<MarketSummary[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [watchedSlugs, setWatchedSlugs] = useState<Set<string>>(new Set());
  const searchRef = useRef<HTMLInputElement | null>(null);

  // press "/" anywhere to jump to search
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const target = e.target as HTMLElement | null;
      if (e.key === "/" && target?.tagName !== "INPUT" && target?.tagName !== "TEXTAREA") {
        e.preventDefault();
        searchRef.current?.focus();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // debounced text search, replaces the grid while a query is active
  useEffect(() => {
    const q = query.trim();
    if (!q) {
      setResults(null);
      setSearching(false);
      return;
    }
    setSearching(true);
    const id = setTimeout(() => {
      searchMarkets(q)
        .then(setResults)
        .catch(() => setResults([]))
        .finally(() => setSearching(false));
    }, 400);
    return () => clearTimeout(id);
  }, [query]);

  useEffect(() => {
    fetchWatchlist()
      .then((items) => setWatchedSlugs(new Set(items.map((i) => i.market_id))))
      .catch(() => undefined);
  }, []);

  const toggleWatch = useCallback((slug: string, watched: boolean) => {
    setWatchedSlugs((prev) => {
      const next = new Set(prev);
      if (watched) next.add(slug);
      else next.delete(slug);
      return next;
    });
    setWatched(slug, watched).catch(() =>
      setWatchedSlugs((prev) => {
        const next = new Set(prev);
        if (watched) next.delete(slug);
        else next.add(slug);
        return next;
      }),
    );
  }, []);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    fetchMarkets(MARKETS_TO_FETCH)
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

  const cardProps = (m: MarketSummary) => ({
    watched: watchedSlugs.has(m.slug),
    onToggleWatch: toggleWatch,
  });

  return (
    <section>
      <div className="mb-4">
        <input
          ref={searchRef}
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search any market — team, candidate, event…  ( / )"
          className="w-full max-w-md rounded-xl border border-desk-line bg-desk-deep/80 px-4 py-2 text-sm text-desk-ink placeholder-desk-faint focus:border-instrument/60 focus:outline-none"
        />
      </div>

      {query.trim() && (
        <div className="mb-6">
          <div className="mb-3 font-mono text-[11px] uppercase tracking-wider text-desk-dim">
            {searching
              ? "searching…"
              : `${results?.length ?? 0} result${(results?.length ?? 0) === 1 ? "" : "s"} for “${query.trim()}”`}
          </div>
          {!searching && results && results.length === 0 && (
            <div className="rounded-xl border border-desk-line bg-desk-panel p-5 text-sm text-desk-dim">
              No active markets match. Try fewer or different words.
            </div>
          )}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {(results ?? []).map((m, i) => (
              <MarketCard key={m.id} market={m} index={i} {...cardProps(m)} />
            ))}
          </div>
        </div>
      )}

      <div className={`mb-5 flex flex-wrap items-center gap-2 ${query.trim() ? "hidden" : ""}`}>
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
            <div key={i} style={{ "--i": i } as React.CSSProperties} className="desk-rise desk-skeleton h-44 rounded-2xl" />
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
      {!loading && !query.trim() && category === "all" && (
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
                {group.slice(0, 6).map((m, i) => (
                  <MarketCard key={m.id} market={m} index={i} {...cardProps(m)} />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* single category (flat) */}
      {!loading && !query.trim() && category !== "all" && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {flat.map((m, i) => (
            <MarketCard key={m.id} market={m} index={i} {...cardProps(m)} />
          ))}
        </div>
      )}
    </section>
  );
}
