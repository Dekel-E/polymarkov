"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import EquityChart from "@/components/EquityChart";
import { closePosition, fetchPortfolio } from "@/lib/api";
import { authConfigured, useAuth } from "@/lib/auth";
import type { Portfolio, Position } from "@/lib/types";

const usd = (v: number) =>
  v.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 });

function Pnl({ value }: { value: number | null | undefined }) {
  if (value === null || value === undefined) return <span className="text-desk-faint">—</span>;
  const cls = value > 0 ? "text-emerald-400" : value < 0 ? "text-red-400" : "text-desk-dim";
  return <span className={`font-semibold ${cls}`}>{value >= 0 ? "+" : ""}{usd(value)}</span>;
}

function SideChip({ side }: { side: Position["side"] }) {
  return (
    <span
      className={`rounded-md px-2 py-0.5 text-[11px] font-bold ${
        side === "BUY_YES"
          ? "bg-emerald-950 text-emerald-300"
          : "bg-red-950 text-red-300"
      }`}
    >
      {side.replace("_", " ")}
    </span>
  );
}

const STRATEGY_LABELS: Record<string, string> = {
  ai_signal: "ai signal",
  arbitrage: "arb",
  copy: "copy",
  manual: "manual",
};

function StrategyTag({ strategy }: { strategy: string | null }) {
  if (!strategy) return null;
  return (
    <span className="rounded bg-desk-line/70 px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wider text-desk-dim">
      {STRATEGY_LABELS[strategy] ?? strategy}
    </span>
  );
}

function StatCard({ label, value, sub }: { label: string; value: React.ReactNode; sub?: string }) {
  return (
    <div className="rounded-2xl border border-desk-line bg-desk-panel/60 p-4">
      <div className="text-[11px] uppercase tracking-wider text-desk-dim">{label}</div>
      <div className="mt-1 text-2xl font-bold tabular-nums tracking-tight text-desk-ink">
        {value}
      </div>
      {sub && <div className="mt-0.5 text-xs text-desk-dim">{sub}</div>}
    </div>
  );
}

export default function PortfolioPage() {
  const { user, token, loading: authLoading } = useAuth();
  const [scope, setScope] = useState<"agent" | "mine">("agent");
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [closing, setClosing] = useState<string | null>(null);
  const [closeNote, setCloseNote] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    fetchPortfolio(scope, token)
      .then(setPortfolio)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, [scope, token]);

  useEffect(() => {
    if (!authLoading) load();
  }, [authLoading, load]);

  async function onClose(position: Position) {
    setClosing(position.id);
    setCloseNote(null);
    try {
      const { exit_price, pnl } = await closePosition(position.id, token);
      setCloseNote(
        `Closed ${position.market_id} at ${(exit_price * 100).toFixed(1)}% for ${pnl >= 0 ? "+" : ""}${usd(pnl)}.`,
      );
      load();
    } catch (e) {
      setCloseNote(`Close failed: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setClosing(null);
    }
  }

  const stats = portfolio?.stats;

  return (
    <div className="mx-auto max-w-6xl space-y-8 px-4 py-8 md:px-8">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight md:text-3xl">
            Paper <span className="text-instrument">Portfolio</span>
          </h1>
          <p className="mt-1 text-sm text-desk-dim">
            Follow the agent&apos;s book, or your own — every fill is simulated against the
            live order book.
          </p>
        </div>
        <div className="flex rounded-xl border border-desk-line bg-desk-panel p-1">
          <button
            onClick={() => setScope("agent")}
            className={`rounded-lg px-4 py-1.5 text-sm font-semibold transition ${
              scope === "agent" ? "bg-instrument text-desk-deep" : "text-desk-dim hover:text-desk-ink"
            }`}
          >
            Agent book
          </button>
          <button
            onClick={() => setScope("mine")}
            className={`rounded-lg px-4 py-1.5 text-sm font-semibold transition ${
              scope === "mine" ? "bg-instrument text-desk-deep" : "text-desk-dim hover:text-desk-ink"
            }`}
          >
            My trades
          </button>
        </div>
      </header>

      {scope === "mine" && !user && !authLoading && (
        <div className="rounded-xl border border-desk-line bg-desk-panel/60 p-6 text-center">
          <p className="text-sm text-desk-soft">Log in to see your personal trades.</p>
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

      {(scope === "agent" || user) && (
        <>
          {stats && (
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              <StatCard
                label="Balance"
                value={usd(stats.balance_usd)}
                sub={`start ${usd(stats.bankroll_usd)} + realized PnL`}
              />
              <StatCard
                label="Equity"
                value={usd(stats.equity_usd)}
                sub="balance + unrealized PnL"
              />
              <StatCard
                label="Open exposure"
                value={usd(stats.open_exposure_usd)}
                sub={`${stats.open_positions} open position${stats.open_positions === 1 ? "" : "s"}`}
              />
              <StatCard
                label="Realized PnL"
                value={<Pnl value={stats.realized_pnl_usd} />}
                sub={
                  stats.win_rate !== null
                    ? `${(stats.win_rate * 100).toFixed(0)}% win rate over ${stats.resolved_positions}`
                    : "no resolved trades yet"
                }
              />
            </div>
          )}

          {error && (
            <div className="rounded-xl border border-amber-900/60 bg-amber-950/30 p-4 text-sm text-amber-300">
              Could not load portfolio: {error}
              <button onClick={load} className="ml-2 text-instrument hover:underline">
                Retry
              </button>
            </div>
          )}
          {closeNote && (
            <div className="rounded-xl border border-desk-edge bg-desk-panel p-3 text-sm text-desk-ink">
              {closeNote}
            </div>
          )}
          {loading && <div className="h-40 animate-pulse rounded-2xl bg-desk-panel" />}

          {!loading && portfolio && (
            <>
              <EquityChart portfolio={portfolio} />

              <section>
                <h2 className="mb-3 text-lg font-bold tracking-tight">Open positions</h2>
                {portfolio.open.length === 0 ? (
                  <div className="rounded-xl border border-desk-line bg-desk-panel/60 p-5 text-sm text-desk-dim">
                    No open positions. Run the agent with <code className="rounded bg-desk-deep px-1">Trade: yes</code>,
                    or execute a trade from any market&apos;s analysis.
                  </div>
                ) : (
                  <div className="overflow-x-auto rounded-2xl border border-desk-line bg-desk-panel/60">
                    <table className="w-full min-w-[720px] text-left text-sm">
                      <thead>
                        <tr className="border-b border-desk-line text-[11px] uppercase tracking-wider text-desk-dim">
                          <th className="px-4 py-3 font-semibold">Market</th>
                          <th className="px-4 py-3 font-semibold">Side</th>
                          <th className="px-4 py-3 font-semibold">Entry</th>
                          <th className="px-4 py-3 font-semibold">Now</th>
                          <th className="px-4 py-3 font-semibold">Size</th>
                          <th className="px-4 py-3 font-semibold">Unrealized</th>
                          <th className="px-4 py-3 font-semibold">Opened</th>
                          <th className="px-4 py-3" />
                        </tr>
                      </thead>
                      <tbody>
                        {portfolio.open.map((p) => (
                          <tr key={p.id} className="border-b border-desk-line/60 last:border-0">
                            <td className="max-w-[260px] truncate px-4 py-3">
                              <Link href={`/market/${p.market_id}`} className="text-desk-ink hover:text-instrument">
                                {p.market_id}
                              </Link>
                            </td>
                            <td className="px-4 py-3">
                              <span className="flex items-center gap-1.5">
                                <SideChip side={p.side} />
                                <StrategyTag strategy={p.strategy} />
                              </span>
                            </td>
                            <td className="px-4 py-3 tabular-nums text-desk-soft">{(p.entry_price * 100).toFixed(1)}%</td>
                            <td className="px-4 py-3 tabular-nums text-desk-soft">
                              {p.current_price != null ? `${(p.current_price * 100).toFixed(1)}%` : "—"}
                            </td>
                            <td className="px-4 py-3 tabular-nums text-desk-soft">{usd(p.size_usd)}</td>
                            <td className="px-4 py-3 tabular-nums"><Pnl value={p.unrealized_pnl} /></td>
                            <td className="px-4 py-3 text-xs text-desk-dim">
                              {new Date(p.opened_at).toLocaleDateString()}
                            </td>
                            <td className="px-4 py-3 text-right">
                              <button
                                onClick={() => onClose(p)}
                                disabled={closing === p.id}
                                className="rounded-lg border border-red-500/50 px-3 py-1 text-xs font-semibold text-red-400 transition hover:bg-red-500/10 disabled:opacity-40"
                              >
                                {closing === p.id ? "Closing…" : "Close"}
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>

              <section>
                <h2 className="mb-3 text-lg font-bold tracking-tight">History</h2>
                {portfolio.resolved.length === 0 ? (
                  <div className="rounded-xl border border-desk-line bg-desk-panel/60 p-5 text-sm text-desk-dim">
                    No resolved trades yet.
                  </div>
                ) : (
                  <div className="overflow-x-auto rounded-2xl border border-desk-line bg-desk-panel/60">
                    <table className="w-full min-w-[640px] text-left text-sm">
                      <thead>
                        <tr className="border-b border-desk-line text-[11px] uppercase tracking-wider text-desk-dim">
                          <th className="px-4 py-3 font-semibold">Market</th>
                          <th className="px-4 py-3 font-semibold">Side</th>
                          <th className="px-4 py-3 font-semibold">Entry</th>
                          <th className="px-4 py-3 font-semibold">Size</th>
                          <th className="px-4 py-3 font-semibold">Outcome</th>
                          <th className="px-4 py-3 font-semibold">PnL</th>
                        </tr>
                      </thead>
                      <tbody>
                        {portfolio.resolved.map((p) => (
                          <tr key={p.id} className="border-b border-desk-line/60 last:border-0">
                            <td className="max-w-[260px] truncate px-4 py-3">
                              <Link href={`/market/${p.market_id}`} className="text-desk-ink hover:text-instrument">
                                {p.market_id}
                              </Link>
                            </td>
                            <td className="px-4 py-3">
                              <span className="flex items-center gap-1.5">
                                <SideChip side={p.side} />
                                <StrategyTag strategy={p.strategy} />
                              </span>
                            </td>
                            <td className="px-4 py-3 tabular-nums text-desk-soft">{(p.entry_price * 100).toFixed(1)}%</td>
                            <td className="px-4 py-3 tabular-nums text-desk-soft">{usd(p.size_usd)}</td>
                            <td className="px-4 py-3 text-xs font-semibold text-desk-dim">{p.resolved_outcome}</td>
                            <td className="px-4 py-3 tabular-nums"><Pnl value={p.pnl} /></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>
            </>
          )}
        </>
      )}
    </div>
  );
}
