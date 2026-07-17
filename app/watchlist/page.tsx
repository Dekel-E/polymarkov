"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { fetchWatchlist, setWatched } from "@/lib/api";
import type { WatchItem } from "@/lib/types";

function ageLabel(iso: string | null): string | null {
  if (!iso) return null;
  const mins = Math.floor((Date.now() - new Date(iso).getTime()) / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  return hours < 24 ? `${hours}h ago` : `${Math.floor(hours / 24)}d ago`;
}

function VerdictChip({ verdict }: { verdict: string | null }) {
  if (!verdict) return <span className="font-mono text-[11px] text-desk-faint">not analyzed yet</span>;
  const cls =
    verdict === "BUY_YES"
      ? "border-emerald-400/60 text-emerald-400"
      : verdict === "BUY_NO"
        ? "border-red-400/60 text-red-400"
        : "border-desk-edge text-desk-dim";
  return (
    <span className={`rounded border px-2 py-0.5 font-mono text-[11px] font-bold uppercase ${cls}`}>
      {verdict.replace("_", " ")}
    </span>
  );
}

export default function WatchlistPage() {
  const [items, setItems] = useState<WatchItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    fetchWatchlist()
      .then(setItems)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function unwatch(marketId: string) {
    setItems((prev) => prev.filter((i) => i.market_id !== marketId));
    try {
      await setWatched(marketId, false);
    } catch {
      load();
    }
  }

  return (
    <div className="desk-rise mx-auto max-w-4xl space-y-6 px-4 py-8 md:px-8">
      <header>
        <h1 className="font-display text-2xl font-bold uppercase tracking-wide md:text-3xl">
          Watchlist
        </h1>
        <p className="mt-1 text-sm text-desk-dim">
          Markets you follow. The agent re-analyzes them automatically on schedule, so the
          verdict here stays current.
        </p>
      </header>

      <>
          {error && (
            <div className="rounded-xl border border-amber-900/60 bg-amber-950/30 p-4 text-sm text-amber-300">
              Could not load the watchlist: {error}
              <button onClick={load} className="ml-2 text-instrument hover:underline">
                Retry
              </button>
            </div>
          )}
          {loading && <div className="h-40 animate-pulse rounded-2xl bg-desk-panel" />}

          {!loading && !error && items.length === 0 && (
            <div className="rounded-xl border border-desk-line bg-desk-panel/60 p-6 text-sm text-desk-dim">
              Nothing watched yet. Star a market on the{" "}
              <Link href="/" className="text-instrument hover:underline">
                dashboard
              </Link>{" "}
              to follow it here.
            </div>
          )}

          {!loading && items.length > 0 && (
            <div className="overflow-hidden rounded-2xl border border-desk-line bg-desk-panel/60">
              {items.map((item) => (
                <div
                  key={item.market_id}
                  className="flex flex-wrap items-center gap-3 border-b border-desk-line/60 px-4 py-3 last:border-0"
                >
                  <Link
                    href={`/market/${item.market_id}`}
                    className="min-w-0 flex-1 truncate text-sm font-semibold text-desk-ink transition hover:text-instrument"
                  >
                    {item.question}
                  </Link>
                  {item.last_mid != null && (
                    <span className="font-mono text-sm tabular-nums text-desk-soft">
                      {(Number(item.last_mid) * 100).toFixed(0)}%
                    </span>
                  )}
                  <VerdictChip verdict={item.verdict} />
                  {item.verdict && item.fair_probability != null && (
                    <span className="font-mono text-[11px] text-desk-dim">
                      fair {(item.fair_probability * 100).toFixed(1)}%
                    </span>
                  )}
                  {item.analyzed_at && (
                    <span className="font-mono text-[10px] text-desk-faint">
                      {ageLabel(item.analyzed_at)}
                    </span>
                  )}
                  <button
                    onClick={() => unwatch(item.market_id)}
                    aria-label="Remove from watchlist"
                    className="rounded-lg p-1 text-instrument transition hover:text-desk-dim"
                    title="Remove from watchlist"
                  >
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" strokeWidth="1.5">
                      <path d="M12 3l2.7 5.7 6.3.8-4.6 4.3 1.2 6.2L12 17l-5.6 3 1.2-6.2L3 9.5l6.3-.8L12 3Z" />
                    </svg>
                  </button>
                </div>
              ))}
            </div>
          )}
      </>
    </div>
  );
}
