"use client";

import type { Microstructure, SmartMoneyFlow } from "@/lib/types";

function Stat({ label, value, tone }: { label: string; value: string; tone?: "up" | "down" | "neutral" }) {
  const color =
    tone === "up" ? "text-emerald-400" : tone === "down" ? "text-red-400" : "text-desk-ink";
  return (
    <div>
      <div className="font-mono text-[10px] uppercase tracking-widest text-desk-faint">{label}</div>
      <div className={`mt-0.5 font-mono text-sm font-semibold tabular-nums ${color}`}>{value}</div>
    </div>
  );
}

const fmtPts = (v: number | null) => (v == null ? "n/a" : `${v >= 0 ? "+" : ""}${v.toFixed(1)}pts`);
const money = (v: number) => (v >= 1000 ? `$${(v / 1000).toFixed(1)}k` : `$${v.toFixed(0)}`);

export function MicrostructureCard({ m }: { m: Microstructure }) {
  const imb = m.imbalance;
  return (
    <section className="rounded-2xl border border-desk-line bg-desk-panel/70 p-4">
      <div className="mb-3 flex items-baseline justify-between">
        <h2 className="font-display text-lg font-bold uppercase tracking-wide text-desk-ink">
          Microstructure
        </h2>
        <span className="font-mono text-[11px] text-desk-faint">order book · price action · for the Quant</span>
      </div>
      <div className="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-4">
        <Stat
          label="book imbalance"
          value={imb == null ? "n/a" : `${imb >= 0 ? "+" : ""}${imb.toFixed(2)}`}
          tone={imb == null ? "neutral" : imb > 0.05 ? "up" : imb < -0.05 ? "down" : "neutral"}
        />
        <Stat label="micro vs mid" value={fmtPts(m.micro_vs_mid_pts)} tone={(m.micro_vs_mid_pts ?? 0) > 0 ? "up" : (m.micro_vs_mid_pts ?? 0) < 0 ? "down" : "neutral"} />
        <Stat label="24h momentum" value={fmtPts(m.momentum_24h_pts)} tone={(m.momentum_24h_pts ?? 0) > 0 ? "up" : (m.momentum_24h_pts ?? 0) < 0 ? "down" : "neutral"} />
        <Stat label="7d momentum" value={fmtPts(m.momentum_7d_pts)} tone={(m.momentum_7d_pts ?? 0) > 0 ? "up" : (m.momentum_7d_pts ?? 0) < 0 ? "down" : "neutral"} />
        <Stat label="depth ±5c (bid/ask)" value={`${money(m.bid_depth_5c_usd)} / ${money(m.ask_depth_5c_usd)}`} />
        <Stat label="spread" value={m.spread_pct == null ? "n/a" : `${m.spread_pct.toFixed(1)}%`} />
        <Stat label="volatility" value={fmtPts(m.volatility_pts)} />
        <Stat label="trend · RSI" value={`${m.trend}${m.rsi == null ? "" : ` · ${m.rsi.toFixed(0)}`}`} tone={m.trend === "up" ? "up" : m.trend === "down" ? "down" : "neutral"} />
      </div>
    </section>
  );
}

function WalletRow({ w, kind }: { w: { label: string; wallet: string; rank?: number | null; side: "YES" | "NO"; yes_lean_usd: number }; kind: "followed" | "top" }) {
  return (
    <div className="flex items-center justify-between gap-3 py-1 font-mono text-xs">
      <span className="flex min-w-0 items-center gap-2">
        <span className={`rounded px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider ${kind === "followed" ? "bg-instrument/15 text-instrument" : "bg-desk-line text-desk-dim"}`}>
          {kind === "followed" ? "followed" : w.rank ? `#${w.rank}` : "top"}
        </span>
        <span className="truncate text-desk-soft">{w.label || `${w.wallet.slice(0, 8)}…`}</span>
      </span>
      <span className={`shrink-0 font-semibold ${w.side === "YES" ? "text-emerald-400" : "text-red-400"}`}>
        {w.side} {money(Math.abs(w.yes_lean_usd))}
      </span>
    </div>
  );
}

export function SmartMoneyCard({ s }: { s: SmartMoneyFlow }) {
  const rows = [...s.followed_active.map((w) => ({ w, kind: "followed" as const })), ...s.top_active.map((w) => ({ w, kind: "top" as const }))];
  if (rows.length === 0 && s.whale_prints.length === 0) return null;
  const netSide = s.net_yes_usd >= 0 ? "YES" : "NO";
  return (
    <section className="rounded-2xl border border-desk-line bg-desk-panel/70 p-4">
      <div className="mb-3 flex items-baseline justify-between">
        <h2 className="font-display text-lg font-bold uppercase tracking-wide text-desk-ink">Smart money</h2>
        <span className="font-mono text-[11px] text-desk-faint">
          net{" "}
          <span className={s.net_yes_usd >= 0 ? "text-emerald-400" : "text-red-400"}>
            {netSide} {money(Math.abs(s.net_yes_usd))}
          </span>{" "}
          · {s.trades_scanned} trades
        </span>
      </div>
      <div className="divide-y divide-desk-line/60">
        {rows.slice(0, 8).map(({ w, kind }, i) => (
          <WalletRow key={i} w={w} kind={kind} />
        ))}
      </div>
      {s.whale_prints.length > 0 && (
        <div className="mt-2 border-t border-desk-line/60 pt-2 font-mono text-[11px] text-instrument/90">
          {s.whale_prints.slice(0, 3).map((wh, i) => (
            <div key={i}>⚑ whale: {wh.side} {wh.outcome} {money(wh.notional_usd)}</div>
          ))}
        </div>
      )}
    </section>
  );
}
