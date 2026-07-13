"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import EquityChart from "@/components/EquityChart";
import {
  cancelQuote,
  closePosition,
  executeTrade,
  fetchPortfolio,
  fetchWorkingQuotes,
  setPositionLimits,
  updateSettings,
} from "@/lib/api";
import { authConfigured, useAuth } from "@/lib/auth";
import type { Portfolio, Position, WorkingQuote } from "@/lib/types";

const usd = (v: number) =>
  v.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 });
const pct = (v: number | null | undefined) => (v == null ? "—" : `${(v * 100).toFixed(1)}%`);

function Pnl({ value }: { value: number | null | undefined }) {
  if (value === null || value === undefined) return <span className="text-desk-faint">—</span>;
  const cls = value > 0 ? "text-emerald-400" : value < 0 ? "text-red-400" : "text-desk-dim";
  return <span className={`font-semibold ${cls}`}>{value >= 0 ? "+" : ""}{usd(value)}</span>;
}

function SideChip({ side }: { side: Position["side"] }) {
  return (
    <span
      className={`rounded-md px-2 py-0.5 text-[11px] font-bold ${
        side === "BUY_YES" ? "bg-emerald-950 text-emerald-300" : "bg-red-950 text-red-300"
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
  market_making: "mm",
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

function StatCard({ label, value, sub }: { label: string; value: React.ReactNode; sub?: React.ReactNode }) {
  return (
    <div className="rounded-2xl border border-desk-line bg-desk-panel/60 p-4">
      <div className="text-[11px] uppercase tracking-wider text-desk-dim">{label}</div>
      <div className="mt-1 text-xl font-bold tabular-nums tracking-tight text-desk-ink">{value}</div>
      {sub && <div className="mt-0.5 text-xs text-desk-dim">{sub}</div>}
    </div>
  );
}

const STRIP_COLORS = ["#F0B441", "#7A9CC6", "#3EB48E", "#C67AA8", "#8A98AB"];

function ExposureStrip({ title, data, total }: { title: string; data: Record<string, number>; total: number }) {
  const entries = Object.entries(data);
  if (!entries.length || total <= 0) return null;
  return (
    <div className="flex-1">
      <div className="mb-1 font-mono text-[10px] uppercase tracking-widest text-desk-faint">{title}</div>
      <div className="flex h-2.5 overflow-hidden rounded-full bg-desk-line">
        {entries.map(([k, v], i) => (
          <div
            key={k}
            title={`${k}: ${usd(v)}`}
            style={{ width: `${(v / total) * 100}%`, background: STRIP_COLORS[i % STRIP_COLORS.length] }}
          />
        ))}
      </div>
      <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5">
        {entries.map(([k, v], i) => (
          <span key={k} className="font-mono text-[10px] text-desk-dim">
            <span style={{ color: STRIP_COLORS[i % STRIP_COLORS.length] }}>●</span> {k} {usd(v)}
          </span>
        ))}
      </div>
    </div>
  );
}

type SortKey = "market_id" | "entry_price" | "current_price" | "size_usd" | "unrealized_pnl" | "opened_at";

function exportCsv(rows: Position[]) {
  const header = "market,side,strategy,entry,size_usd,outcome,pnl,opened_at,resolved_at";
  const lines = rows.map((p) =>
    [p.market_id, p.side, p.strategy ?? "", p.entry_price, p.size_usd, p.resolved_outcome ?? "", p.pnl ?? "", p.opened_at, p.resolved_at ?? ""]
      .map((v) => `"${String(v).replace(/"/g, '""')}"`)
      .join(","),
  );
  const blob = new Blob([[header, ...lines].join("\n")], { type: "text/csv" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "polymarkov-trades.csv";
  a.click();
  URL.revokeObjectURL(a.href);
}

export default function PortfolioPage() {
  const { user, token, loading: authLoading } = useAuth();
  const [scope, setScope] = useState<"agent" | "mine">("agent");
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [quotes, setQuotes] = useState<WorkingQuote[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [strategyFilter, setStrategyFilter] = useState<string>("all");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>("opened_at");
  const [sortAsc, setSortAsc] = useState(false);
  const [fundsDraft, setFundsDraft] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    Promise.all([fetchPortfolio(scope, token), fetchWorkingQuotes().catch(() => [])])
      .then(([p, q]) => {
        setPortfolio(p);
        setQuotes(q);
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, [scope, token]);

  useEffect(() => {
    if (!authLoading) load();
  }, [authLoading, load]);

  async function act(label: string, fn: () => Promise<string>) {
    setBusy(label);
    setNote(null);
    try {
      setNote(await fn());
      load();
    } catch (e) {
      setNote(`${label} failed: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusy(null);
    }
  }

  const stats = portfolio?.stats;
  const byStrategy = (rows: Position[]) =>
    strategyFilter === "all" ? rows : rows.filter((p) => (p.strategy ?? "manual") === strategyFilter);
  const presentStrategies = portfolio
    ? Array.from(new Set([...portfolio.open, ...portfolio.resolved].map((p) => p.strategy ?? "manual")))
    : [];

  const openRows = useMemo(() => {
    if (!portfolio) return [];
    const rows = [...byStrategy(portfolio.open)];
    rows.sort((a, b) => {
      const av = a[sortKey] ?? "";
      const bv = b[sortKey] ?? "";
      const cmp = typeof av === "number" && typeof bv === "number" ? av - bv : String(av).localeCompare(String(bv));
      return sortAsc ? cmp : -cmp;
    });
    return rows;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [portfolio, strategyFilter, sortKey, sortAsc]);

  function Th({ label, k }: { label: string; k?: SortKey }) {
    return (
      <th className="px-4 py-3 font-semibold">
        {k ? (
          <button
            onClick={() => {
              if (sortKey === k) setSortAsc(!sortAsc);
              else {
                setSortKey(k);
                setSortAsc(false);
              }
            }}
            className="transition hover:text-desk-ink"
          >
            {label}
            {sortKey === k ? (sortAsc ? " ↑" : " ↓") : ""}
          </button>
        ) : (
          label
        )}
      </th>
    );
  }

  return (
    <div className="mx-auto max-w-6xl space-y-8 px-4 py-8 md:px-8">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight md:text-3xl">
            Paper <span className="text-instrument">Portfolio</span>
          </h1>
          <p className="mt-1 text-sm text-desk-dim">
            Follow the agent&apos;s book, or manage your own — every fill is simulated against the live order book.
          </p>
        </div>
        <div className="flex rounded-xl border border-desk-line bg-desk-panel p-1">
          {(["agent", "mine"] as const).map((s) => (
            <button
              key={s}
              onClick={() => setScope(s)}
              className={`rounded-lg px-4 py-1.5 text-sm font-semibold transition ${
                scope === s ? "bg-instrument text-desk-deep" : "text-desk-dim hover:text-desk-ink"
              }`}
            >
              {s === "agent" ? "Agent book" : "My trades"}
            </button>
          ))}
        </div>
      </header>

      {scope === "mine" && !user && !authLoading && (
        <div className="rounded-xl border border-desk-line bg-desk-panel/60 p-6 text-center">
          <p className="text-sm text-desk-soft">Log in to manage your personal trades.</p>
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
            <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
              <StatCard
                label="Balance"
                value={usd(stats.balance_usd)}
                sub={
                  user ? (
                    fundsDraft === null ? (
                      <button onClick={() => setFundsDraft(String(stats.bankroll_usd))} className="text-instrument hover:underline">
                        bankroll {usd(stats.bankroll_usd)} · adjust
                      </button>
                    ) : (
                      <span className="flex items-center gap-1.5">
                        $
                        <input
                          value={fundsDraft}
                          onChange={(e) => setFundsDraft(e.target.value)}
                          className="w-20 rounded border border-desk-line bg-desk-deep px-1.5 py-0.5 font-mono text-xs text-desk-ink"
                        />
                        <button
                          onClick={() =>
                            act("Adjust funds", async () => {
                              await updateSettings({ funds: { bankroll_usd: Number(fundsDraft) } });
                              setFundsDraft(null);
                              return `Bankroll set to ${usd(Number(fundsDraft))}.`;
                            })
                          }
                          className="text-instrument hover:underline"
                        >
                          set
                        </button>
                        <button onClick={() => setFundsDraft(null)} className="text-desk-faint hover:underline">
                          ✕
                        </button>
                      </span>
                    )
                  ) : (
                    `bankroll ${usd(stats.bankroll_usd)}`
                  )
                }
              />
              <StatCard label="Equity" value={usd(stats.equity_usd)} sub={<>unrealized <Pnl value={stats.unrealized_pnl_usd} /></>} />
              <StatCard label="Available" value={usd(stats.available_usd)} sub="balance − open exposure" />
              <StatCard
                label="Open exposure"
                value={usd(stats.open_exposure_usd)}
                sub={`${stats.open_positions} position${stats.open_positions === 1 ? "" : "s"} · largest ${stats.largest_position_pct}%`}
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

          {stats && stats.open_exposure_usd > 0 && (
            <div className="flex flex-col gap-4 rounded-2xl border border-desk-line bg-desk-panel/60 p-4 sm:flex-row">
              <ExposureStrip title="exposure by strategy" data={stats.exposure_by_strategy} total={stats.open_exposure_usd} />
              <ExposureStrip title="exposure by category" data={stats.exposure_by_category} total={stats.open_exposure_usd} />
            </div>
          )}

          {error && (
            <div className="rounded-xl border border-amber-900/60 bg-amber-950/30 p-4 text-sm text-amber-300">
              Could not load portfolio: {error}
              <button onClick={load} className="ml-2 text-instrument hover:underline">Retry</button>
            </div>
          )}
          {note && <div className="rounded-xl border border-desk-edge bg-desk-panel p-3 text-sm text-desk-ink">{note}</div>}
          {loading && <div className="h-40 animate-pulse rounded-2xl bg-desk-panel" />}

          {!loading && portfolio && (
            <>
              <EquityChart portfolio={portfolio} />

              {presentStrategies.length > 1 && (
                <div className="flex flex-wrap items-center gap-2">
                  {["all", ...presentStrategies].map((s) => (
                    <button
                      key={s}
                      onClick={() => setStrategyFilter(s)}
                      className={`rounded-full px-3 py-1 font-mono text-[11px] font-semibold uppercase tracking-wider transition ${
                        strategyFilter === s ? "bg-instrument text-desk-deep" : "border border-desk-edge text-desk-dim hover:text-desk-ink"
                      }`}
                    >
                      {s === "all" ? "all strategies" : s.replace("_", " ")}
                    </button>
                  ))}
                </div>
              )}

              {/* open positions */}
              <section>
                <div className="mb-3 flex items-baseline justify-between gap-4">
                  <h2 className="text-lg font-bold tracking-tight">Open positions</h2>
                  <span className="font-mono text-[10px] text-desk-faint">
                    prices from the last market index (≤2h) · click a row for controls
                  </span>
                </div>
                {openRows.length === 0 ? (
                  <div className="rounded-xl border border-desk-line bg-desk-panel/60 p-5 text-sm text-desk-dim">
                    No open positions.
                  </div>
                ) : (
                  <div className="overflow-x-auto rounded-2xl border border-desk-line bg-desk-panel/60">
                    <table className="w-full min-w-[760px] text-left text-sm">
                      <thead>
                        <tr className="border-b border-desk-line text-[11px] uppercase tracking-wider text-desk-dim">
                          <Th label="Market" k="market_id" />
                          <Th label="Side" />
                          <Th label="Entry" k="entry_price" />
                          <Th label="Now" k="current_price" />
                          <Th label="Size" k="size_usd" />
                          <Th label="Unrealized" k="unrealized_pnl" />
                          <Th label="SL / TP" />
                          <Th label="Opened" k="opened_at" />
                        </tr>
                      </thead>
                      <tbody>
                        {openRows.map((p) => (
                          <PositionRow
                            key={p.id}
                            p={p}
                            scope={scope}
                            expanded={expanded === p.id}
                            onToggle={() => setExpanded(expanded === p.id ? null : p.id)}
                            busy={busy}
                            canClose={scope === "mine"}
                            canDirect={Boolean(user)}
                            onClose={(fraction) =>
                              act("Close", async () => {
                                const r = await closePosition(p.id, token, fraction);
                                return `Closed ${Math.round(r.closed_fraction * 100)}% of ${p.market_id} at ${(r.exit_price * 100).toFixed(1)}% for ${r.pnl >= 0 ? "+" : ""}${usd(r.pnl)}.`;
                              })
                            }
                            onLimits={(sl, tp) =>
                              act("Set limits", async () => {
                                await setPositionLimits(p.id, sl, tp, token);
                                return `Levels saved — the risk manager enforces them on its next pass.`;
                              })
                            }
                            onAdd={(amount) =>
                              act("Add", async () => {
                                const fill = await executeTrade(p.market_id, p.side, amount, token);
                                return `Added ${usd(fill.size_usd)} at ${(fill.vwap * 100).toFixed(1)}% (separate lot in My trades).`;
                              })
                            }
                          />
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>

              {/* working quotes (market maker) */}
              {scope === "agent" && quotes.length > 0 && (
                <section>
                  <h2 className="mb-3 text-lg font-bold tracking-tight">
                    Working quotes
                    <span className="ml-2 font-mono text-[11px] font-normal text-desk-faint">
                      resting market-maker orders
                    </span>
                  </h2>
                  <div className="overflow-hidden rounded-2xl border border-desk-line bg-desk-panel/60">
                    {quotes.map((q) => (
                      <div key={q.id} className="flex flex-wrap items-center gap-3 border-b border-desk-line/60 px-4 py-2.5 text-xs last:border-0">
                        <Link href={`/market/${q.market_id}`} className="min-w-0 flex-1 truncate font-mono text-desk-soft hover:text-instrument">
                          {q.market_id}
                        </Link>
                        <span className="font-mono tabular-nums text-emerald-400">bid {pct(q.bid)}</span>
                        <span className="font-mono tabular-nums text-red-400">ask {pct(q.ask)}</span>
                        <span className="font-mono tabular-nums text-desk-dim">{usd(q.size_usd)}/side</span>
                        {user && (
                          <button
                            onClick={() =>
                              act("Cancel quote", async () => {
                                await cancelQuote(q.id, token);
                                return `Quote on ${q.market_id} pulled.`;
                              })
                            }
                            className="rounded border border-red-500/50 px-2 py-0.5 font-semibold text-red-400 transition hover:bg-red-500/10"
                          >
                            Pull
                          </button>
                        )}
                      </div>
                    ))}
                  </div>
                </section>
              )}

              {/* history */}
              <section>
                <div className="mb-3 flex items-baseline justify-between">
                  <h2 className="text-lg font-bold tracking-tight">History</h2>
                  {portfolio.resolved.length > 0 && (
                    <button
                      onClick={() => exportCsv(byStrategy(portfolio.resolved))}
                      className="font-mono text-[11px] uppercase tracking-wider text-instrument hover:underline"
                    >
                      export csv
                    </button>
                  )}
                </div>
                {byStrategy(portfolio.resolved).length === 0 ? (
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
                        {byStrategy(portfolio.resolved).map((p) => (
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
                            <td className="px-4 py-3 tabular-nums text-desk-soft">{pct(p.entry_price)}</td>
                            <td className="px-4 py-3 tabular-nums text-desk-soft">{usd(p.size_usd)}</td>
                            <td className="px-4 py-3 font-mono text-xs font-semibold text-desk-dim">{p.resolved_outcome}</td>
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

function PositionRow({
  p,
  scope,
  expanded,
  onToggle,
  busy,
  canClose,
  canDirect,
  onClose,
  onLimits,
  onAdd,
}: {
  p: Position;
  scope: "agent" | "mine";
  expanded: boolean;
  onToggle: () => void;
  busy: string | null;
  canClose: boolean;
  canDirect: boolean;
  onClose: (fraction: number) => void;
  onLimits: (sl: number | null, tp: number | null) => void;
  onAdd: (amount: number) => void;
}) {
  const [sl, setSl] = useState(p.sl_price != null ? String(Math.round(p.sl_price * 100)) : "");
  const [tp, setTp] = useState(p.tp_price != null ? String(Math.round(p.tp_price * 100)) : "");
  const [addAmount, setAddAmount] = useState(25);

  const toPrice = (v: string): number | null => {
    const n = Number(v);
    return v.trim() === "" || !Number.isFinite(n) ? null : Math.min(0.99, Math.max(0.01, n / 100));
  };

  return (
    <>
      <tr onClick={onToggle} className="cursor-pointer border-b border-desk-line/60 transition last:border-0 hover:bg-desk-raised/40">
        <td className="max-w-[240px] truncate px-4 py-3">
          <span className="mr-1.5 text-desk-faint">{expanded ? "▾" : "▸"}</span>
          <Link href={`/market/${p.market_id}`} onClick={(e) => e.stopPropagation()} className="text-desk-ink hover:text-instrument">
            {p.market_id}
          </Link>
        </td>
        <td className="px-4 py-3">
          <span className="flex items-center gap-1.5">
            <SideChip side={p.side} />
            <StrategyTag strategy={p.strategy} />
          </span>
        </td>
        <td className="px-4 py-3 tabular-nums text-desk-soft">{pct(p.entry_price)}</td>
        <td className="px-4 py-3 tabular-nums text-desk-soft">{pct(p.current_price)}</td>
        <td className="px-4 py-3 tabular-nums text-desk-soft">{usd(p.size_usd)}</td>
        <td className="px-4 py-3 tabular-nums"><Pnl value={p.unrealized_pnl} /></td>
        <td className="px-4 py-3 font-mono text-[11px] tabular-nums text-desk-dim">
          {p.sl_price != null ? pct(p.sl_price) : "—"} / {p.tp_price != null ? pct(p.tp_price) : "—"}
        </td>
        <td className="px-4 py-3 text-xs text-desk-dim">{new Date(p.opened_at).toLocaleDateString()}</td>
      </tr>
      {expanded && (
        <tr className="border-b border-desk-line/60 bg-desk-deep/40 last:border-0">
          <td colSpan={8} className="px-4 py-4">
            <div className="flex flex-wrap items-start gap-x-10 gap-y-4">
              <div className="font-mono text-[11px] leading-relaxed text-desk-dim">
                entry fee {usd(p.fee_paid)} · slippage {p.slippage_bps?.toFixed(1)} bps
                {p.fair_prob_at_entry != null && <> · fair at entry {pct(p.fair_prob_at_entry)}</>}
                <br />
                opened {new Date(p.opened_at).toLocaleString()}
              </div>

              {canDirect && (
                <div className="flex items-center gap-2 font-mono text-[11px] text-desk-dim">
                  SL
                  <input
                    value={sl}
                    onChange={(e) => setSl(e.target.value)}
                    placeholder="%"
                    className="w-12 rounded border border-desk-line bg-desk-deep px-1.5 py-1 text-desk-ink"
                  />
                  TP
                  <input
                    value={tp}
                    onChange={(e) => setTp(e.target.value)}
                    placeholder="%"
                    className="w-12 rounded border border-desk-line bg-desk-deep px-1.5 py-1 text-desk-ink"
                  />
                  <button
                    onClick={() => onLimits(toPrice(sl), toPrice(tp))}
                    disabled={busy !== null}
                    className="rounded border border-instrument/50 px-2 py-1 font-semibold text-instrument transition hover:bg-instrument/10 disabled:opacity-40"
                  >
                    save levels
                  </button>
                </div>
              )}

              {canClose ? (
                <div className="flex items-center gap-2">
                  {[0.25, 0.5, 1].map((f) => (
                    <button
                      key={f}
                      onClick={() => onClose(f)}
                      disabled={busy !== null}
                      className="rounded-lg border border-red-500/50 px-2.5 py-1 text-xs font-semibold text-red-400 transition hover:bg-red-500/10 disabled:opacity-40"
                    >
                      Close {f === 1 ? "all" : `${f * 100}%`}
                    </button>
                  ))}
                  <span className="ml-3 flex items-center gap-1.5 font-mono text-[11px] text-desk-dim">
                    $
                    <input
                      type="number"
                      min={1}
                      max={1000}
                      value={addAmount}
                      onChange={(e) => setAddAmount(Number(e.target.value))}
                      className="w-16 rounded border border-desk-line bg-desk-deep px-1.5 py-1 text-desk-ink"
                    />
                    <button
                      onClick={() => onAdd(addAmount)}
                      disabled={busy !== null || addAmount <= 0}
                      className="rounded border border-emerald-500/50 px-2 py-1 font-semibold text-emerald-400 transition hover:bg-emerald-500/10 disabled:opacity-40"
                    >
                      add
                    </button>
                  </span>
                </div>
              ) : (
                <span className="font-mono text-[10px] uppercase tracking-wider text-desk-faint" title="Closed by the agent's risk rules and thesis checks — set SL/TP to direct them">
                  {scope === "agent" ? "agent-managed · direct via SL/TP" : ""}
                </span>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}
