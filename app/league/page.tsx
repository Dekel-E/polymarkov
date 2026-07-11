"use client";

import { useCallback, useEffect, useState } from "react";
import { fetchLeague, fetchWalletPositions } from "@/lib/api";
import type { LeaderRow, WalletPosition } from "@/lib/types";

const WINDOWS = [
  { key: "7d", label: "7 days" },
  { key: "30d", label: "30 days" },
  { key: "all", label: "All time" },
];

const usd = (v: number) =>
  v.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });

function shortWallet(w: string): string {
  return w.length > 12 ? `${w.slice(0, 6)}…${w.slice(-4)}` : w;
}

function WalletPositions({ address }: { address: string }) {
  const [positions, setPositions] = useState<WalletPosition[] | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    fetchWalletPositions(address)
      .then(setPositions)
      .catch(() => setError(true));
  }, [address]);

  if (error)
    return <div className="px-5 py-3 text-xs text-desk-dim">Positions unavailable for this wallet.</div>;
  if (positions === null)
    return <div className="h-16 animate-pulse bg-desk-panel/60" />;
  if (positions.length === 0)
    return <div className="px-5 py-3 text-xs text-desk-dim">No open positions right now.</div>;

  return (
    <div className="space-y-1.5 px-5 py-3">
      {positions.map((p, i) => (
        <div key={i} className="flex flex-wrap items-center gap-3 text-xs">
          <span className="min-w-0 flex-1 truncate text-desk-soft">{p.market}</span>
          {p.outcome && (
            <span
              className={`rounded px-1.5 py-px font-mono text-[10px] font-bold uppercase ${
                p.outcome.toLowerCase() === "yes"
                  ? "bg-emerald-950 text-emerald-300"
                  : "bg-red-950 text-red-300"
              }`}
            >
              {p.outcome}
            </span>
          )}
          <span className="font-mono tabular-nums text-desk-dim">{usd(p.size_usd)}</span>
          <span
            className={`font-mono tabular-nums ${
              p.pnl > 0 ? "text-emerald-400" : p.pnl < 0 ? "text-red-400" : "text-desk-dim"
            }`}
          >
            {p.pnl >= 0 ? "+" : ""}
            {usd(p.pnl)}
          </span>
        </div>
      ))}
    </div>
  );
}

export default function LeaguePage() {
  const [window_, setWindow] = useState("30d");
  const [leaders, setLeaders] = useState<LeaderRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    setExpanded(null);
    fetchLeague(window_)
      .then(setLeaders)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, [window_]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="mx-auto max-w-5xl space-y-6 px-4 py-8 md:px-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-bold uppercase tracking-wide md:text-3xl">
            Smart Money <span className="text-instrument">League</span>
          </h1>
          <p className="mt-1 max-w-2xl text-sm text-desk-dim">
            Polymarket&apos;s most profitable wallets, live from the public data API. Open a
            row to see what a wallet is holding right now.
          </p>
        </div>
        <div className="flex rounded-xl border border-desk-line bg-desk-panel p-1">
          {WINDOWS.map((w) => (
            <button
              key={w.key}
              onClick={() => setWindow(w.key)}
              className={`rounded-lg px-3.5 py-1.5 text-xs font-semibold transition ${
                window_ === w.key
                  ? "bg-instrument text-desk-deep"
                  : "text-desk-dim hover:text-desk-ink"
              }`}
            >
              {w.label}
            </button>
          ))}
        </div>
      </header>

      {error && (
        <div className="rounded-xl border border-amber-900/60 bg-amber-950/30 p-4 text-sm text-amber-300">
          Could not load the leaderboard: {error}
          <button onClick={load} className="ml-2 text-instrument hover:underline">
            Retry
          </button>
        </div>
      )}

      {loading && <div className="h-72 animate-pulse rounded-2xl bg-desk-panel" />}

      {!loading && !error && leaders.length === 0 && (
        <div className="rounded-xl border border-desk-line bg-desk-panel/60 p-6 text-sm text-desk-dim">
          The leaderboard came back empty — Polymarket&apos;s data API may be unavailable.
          <button onClick={load} className="ml-2 text-instrument hover:underline">
            Retry
          </button>
        </div>
      )}

      {!loading && leaders.length > 0 && (
        <div className="overflow-hidden rounded-2xl border border-desk-line bg-desk-panel/60">
          <div className="grid grid-cols-[2.5rem_1fr_auto_auto] items-center gap-3 border-b border-desk-line px-5 py-2.5 font-mono text-[10px] uppercase tracking-widest text-desk-faint md:grid-cols-[2.5rem_1fr_8rem_8rem]">
            <span>#</span>
            <span>Wallet</span>
            <span className="text-right">PnL ({window_})</span>
            <span className="hidden text-right md:block">Volume</span>
          </div>
          {leaders.map((l) => (
            <div key={l.wallet} className="border-b border-desk-line/60 last:border-0">
              <button
                onClick={() => setExpanded(expanded === l.wallet ? null : l.wallet)}
                className="grid w-full grid-cols-[2.5rem_1fr_auto_auto] items-center gap-3 px-5 py-3 text-left transition hover:bg-desk-raised/50 md:grid-cols-[2.5rem_1fr_8rem_8rem]"
              >
                <span className="font-mono text-sm font-bold text-desk-faint">{l.rank}</span>
                <span className="flex min-w-0 items-center gap-2.5">
                  {l.image ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={l.image} alt="" className="h-7 w-7 shrink-0 rounded-full object-cover" />
                  ) : (
                    <span className="h-7 w-7 shrink-0 rounded-full bg-desk-line" />
                  )}
                  <span className="truncate text-sm font-semibold text-desk-ink">
                    {l.name || shortWallet(l.wallet)}
                  </span>
                  {l.verified && <span className="text-instrument" title="Verified">✦</span>}
                </span>
                <span className="text-right font-mono text-sm font-semibold tabular-nums text-emerald-400">
                  +{usd(l.pnl)}
                </span>
                <span className="hidden text-right font-mono text-xs tabular-nums text-desk-dim md:block">
                  {usd(l.volume)}
                </span>
              </button>
              {expanded === l.wallet && (
                <div className="border-t border-desk-line/60 bg-desk-deep/40">
                  <div className="flex items-center justify-between px-5 pt-3">
                    <span className="font-mono text-[10px] uppercase tracking-widest text-desk-faint">
                      current holdings
                    </span>
                    <a
                      href={`https://polymarket.com/profile/${l.wallet}`}
                      target="_blank"
                      rel="noreferrer"
                      className="font-mono text-[10px] uppercase tracking-wider text-instrument hover:underline"
                    >
                      full profile ↗
                    </a>
                  </div>
                  <WalletPositions address={l.wallet} />
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      <p className="font-mono text-[11px] text-desk-faint">
        Wallet tracking against the agent&apos;s own verdicts is on the roadmap.
      </p>
    </div>
  );
}
