"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  fetchFollowedWallets,
  fetchLeague,
  fetchWalletPositions,
  followWallet,
  importWallets,
  unfollowWallet,
} from "@/lib/api";
import type { FollowedWallet, LeaderRow, WalletPosition } from "@/lib/types";

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

function StarIcon({ filled }: { filled: boolean }) {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill={filled ? "currentColor" : "none"} stroke="currentColor" strokeWidth="1.8">
      <path d="M12 3l2.7 5.7 6.3.8-4.6 4.3 1.2 6.2L12 17l-5.6 3 1.2-6.2L3 9.5l6.3-.8L12 3Z" />
    </svg>
  );
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
  if (positions === null) return <div className="h-16 animate-pulse bg-desk-panel/60" />;
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

function ExpandableWalletRow({
  wallet,
  main,
  expanded,
  onToggle,
}: {
  wallet: string;
  main: React.ReactNode;
  expanded: boolean;
  onToggle: () => void;
}) {
  return (
    <div className="border-b border-desk-line/60 last:border-0">
      <div
        role="button"
        tabIndex={0}
        onClick={onToggle}
        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onToggle()}
        className="cursor-pointer transition hover:bg-desk-raised/50"
      >
        {main}
      </div>
      {expanded && (
        <div className="border-t border-desk-line/60 bg-desk-deep/40">
          <div className="flex items-center justify-between px-5 pt-3">
            <span className="font-mono text-[10px] uppercase tracking-widest text-desk-faint">
              current holdings
            </span>
            <a
              href={`https://polymarket.com/profile/${wallet}`}
              target="_blank"
              rel="noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="font-mono text-[10px] uppercase tracking-wider text-instrument hover:underline"
            >
              full profile ↗
            </a>
          </div>
          <WalletPositions address={wallet} />
        </div>
      )}
    </div>
  );
}

export default function LeaguePage() {
  const [window_, setWindow] = useState("30d");
  const [leaders, setLeaders] = useState<LeaderRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [followed, setFollowed] = useState<FollowedWallet[]>([]);
  const [note, setNote] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement | null>(null);

  const followedSet = new Set(followed.map((f) => f.wallet.toLowerCase()));

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    setExpanded(null);
    fetchLeague(window_)
      .then(setLeaders)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, [window_]);

  const loadFollowed = useCallback(() => {
    fetchFollowedWallets()
      .then(setFollowed)
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    loadFollowed();
  }, [loadFollowed]);

  async function toggleFollow(wallet: string, label: string) {
    const w = wallet.toLowerCase();
    setNote(null);
    if (followedSet.has(w)) {
      setFollowed((prev) => prev.filter((f) => f.wallet.toLowerCase() !== w));
      unfollowWallet(w).catch(loadFollowed);
    } else {
      setFollowed((prev) => [{ wallet: w, label }, ...prev]);
      followWallet(w, label).catch(loadFollowed);
    }
  }

  async function onImportFile(file: File) {
    setNote(null);
    try {
      const parsed = JSON.parse(await file.text());
      const list = Array.isArray(parsed) ? parsed : parsed?.wallets;
      if (!Array.isArray(list)) {
        setNote('Import failed: expected a JSON array (["0x…"] or [{"wallet": "0x…", "label": "…"}]).');
        return;
      }
      const { imported, skipped } = await importWallets(list);
      setNote(`Imported ${imported} wallet${imported === 1 ? "" : "s"}${skipped ? `, skipped ${skipped} invalid/duplicate` : ""}.`);
      loadFollowed();
    } catch (e) {
      setNote(`Import failed: ${e instanceof Error ? e.message : String(e)}`);
    }
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6 px-4 py-8 md:px-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-bold uppercase tracking-wide md:text-3xl">
            Smart Money <span className="text-instrument">League</span>
          </h1>
          <p className="mt-1 max-w-2xl text-sm text-desk-dim">
            Polymarket&apos;s most profitable wallets, live from the public data API. Open a
            row to see holdings; star a wallet to follow it.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => fileRef.current?.click()}
            className="rounded-xl border border-desk-edge px-3.5 py-1.5 text-xs font-semibold text-desk-soft transition hover:border-instrument/60 hover:text-instrument"
          >
            Import wallets (JSON)
          </button>
          <input
            ref={fileRef}
            type="file"
            accept=".json,application/json"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) onImportFile(f);
              e.target.value = "";
            }}
          />
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
        </div>
      </header>

      {note && (
        <div className="rounded-xl border border-desk-edge bg-desk-panel p-3 text-sm text-desk-ink">
          {note}
        </div>
      )}

      {followed.length > 0 && (
        <section>
          <h2 className="mb-2 font-mono text-[11px] uppercase tracking-widest text-instrument">
            following · {followed.length}
          </h2>
          <div className="overflow-hidden rounded-2xl border border-instrument/30 bg-desk-panel/60">
            {followed.map((f) => (
              <ExpandableWalletRow
                key={f.wallet}
                wallet={f.wallet}
                expanded={expanded === `f:${f.wallet}`}
                onToggle={() => setExpanded(expanded === `f:${f.wallet}` ? null : `f:${f.wallet}`)}
                main={
                  <div className="flex items-center gap-3 px-5 py-3">
                    <span className="min-w-0 flex-1 truncate text-sm font-semibold text-desk-ink">
                      {f.label || shortWallet(f.wallet)}
                    </span>
                    <span className="hidden font-mono text-xs text-desk-faint md:block">
                      {shortWallet(f.wallet)}
                    </span>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        toggleFollow(f.wallet, f.label);
                      }}
                      aria-label="Unfollow wallet"
                      title="Unfollow"
                      className="text-instrument transition hover:text-desk-dim"
                    >
                      <StarIcon filled />
                    </button>
                  </div>
                }
              />
            ))}
          </div>
        </section>
      )}

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
          <div className="grid grid-cols-[2rem_2.5rem_1fr_auto_auto] items-center gap-3 border-b border-desk-line px-5 py-2.5 font-mono text-[10px] uppercase tracking-widest text-desk-faint md:grid-cols-[2rem_2.5rem_1fr_8rem_8rem]">
            <span />
            <span>#</span>
            <span>Wallet</span>
            <span className="text-right">PnL ({window_})</span>
            <span className="hidden text-right md:block">Volume</span>
          </div>
          {leaders.map((l) => (
            <ExpandableWalletRow
              key={l.wallet}
              wallet={l.wallet}
              expanded={expanded === l.wallet}
              onToggle={() => setExpanded(expanded === l.wallet ? null : l.wallet)}
              main={
                <div className="grid grid-cols-[2rem_2.5rem_1fr_auto_auto] items-center gap-3 px-5 py-3 md:grid-cols-[2rem_2.5rem_1fr_8rem_8rem]">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      toggleFollow(l.wallet, l.name);
                    }}
                    aria-label={
                      followedSet.has(l.wallet.toLowerCase()) ? "Unfollow wallet" : "Follow wallet"
                    }
                    title={followedSet.has(l.wallet.toLowerCase()) ? "Unfollow" : "Follow"}
                    className={`transition ${
                      followedSet.has(l.wallet.toLowerCase())
                        ? "text-instrument"
                        : "text-desk-faint hover:text-instrument"
                    }`}
                  >
                    <StarIcon filled={followedSet.has(l.wallet.toLowerCase())} />
                  </button>
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
                </div>
              }
            />
          ))}
        </div>
      )}

    </div>
  );
}
