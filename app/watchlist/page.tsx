"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { fetchWatchlist, setWatched } from "@/lib/api";
import { authConfigured, useAuth } from "@/lib/auth";
import type { WatchItem } from "@/lib/types";

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
  const { user, token, loading: authLoading } = useAuth();
  const [items, setItems] = useState<WatchItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!token) return;
    setLoading(true);
    setError(null);
    fetchWatchlist(token)
      .then(setItems)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, [token]);

  useEffect(() => {
    if (!authLoading && token) load();
    if (!authLoading && !token) setLoading(false);
  }, [authLoading, token, load]);

  async function unwatch(marketId: string) {
    if (!token) return;
    setItems((prev) => prev.filter((i) => i.market_id !== marketId));
    try {
      await setWatched(marketId, false, token);
    } catch {
      load();
    }
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6 px-4 py-8 md:px-8">
      <header>
        <h1 className="font-display text-2xl font-bold uppercase tracking-wide md:text-3xl">
          Watchlist
        </h1>
        <p className="mt-1 text-sm text-desk-dim">
          Markets you follow. The agent re-analyzes them automatically on schedule, so the
          verdict here stays current.
        </p>
      </header>

      {!user && !authLoading && (
        <div className="rounded-xl border border-desk-line bg-desk-panel/60 p-6 text-center">
          <p className="text-sm text-desk-soft">Log in to build a watchlist.</p>
          {authConfigured && (
            <Link
              href="/login"
              className="mt-3 inline-block rounded-xl bg-instrument px-5 py-2 text-sm font-bold text-desk-deep transition hover:bg-instrument-bright"
            >
              Log in / Register
            </Link>
          )}
        </div>
      )}

      {user && (
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
      )}
    </div>
  );
}
