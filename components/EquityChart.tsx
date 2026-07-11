"use client";

import type { Portfolio } from "@/lib/types";

/**
 * Equity over time: starting bankroll, stepped by each settled trade's PnL,
 * ending at current equity (incl. unrealized). One line, one baseline.
 */
export default function EquityChart({ portfolio }: { portfolio: Portfolio }) {
  const { stats } = portfolio;
  const settled = portfolio.resolved
    .filter((p) => p.pnl !== null)
    .sort(
      (a, b) =>
        new Date(a.resolved_at ?? a.opened_at).getTime() -
        new Date(b.resolved_at ?? b.opened_at).getTime(),
    );
  if (settled.length === 0) return null;

  const points: { t: number; v: number }[] = [];
  const firstT = new Date(settled[0].resolved_at ?? settled[0].opened_at).getTime();
  points.push({ t: firstT - 3_600_000, v: stats.bankroll_usd });
  let running = stats.bankroll_usd;
  for (const p of settled) {
    running += Number(p.pnl);
    points.push({ t: new Date(p.resolved_at ?? p.opened_at).getTime(), v: running });
  }
  points.push({ t: Date.now(), v: stats.equity_usd });

  const W = 640;
  const H = 160;
  const PAD = 8;
  const t0 = points[0].t;
  const t1 = points[points.length - 1].t;
  const values = points.map((p) => p.v).concat(stats.bankroll_usd);
  const vMin = Math.min(...values);
  const vMax = Math.max(...values);
  const span = vMax - vMin || 1;
  const x = (t: number) => PAD + ((t - t0) / Math.max(1, t1 - t0)) * (W - 2 * PAD);
  const y = (v: number) => H - PAD - ((v - vMin) / span) * (H - 2 * PAD);

  const path = points
    .map((p, i) => `${i === 0 ? "M" : "L"}${x(p.t).toFixed(1)},${y(p.v).toFixed(1)}`)
    .join(" ");
  const up = stats.equity_usd >= stats.bankroll_usd;

  return (
    <div className="rounded-2xl border border-desk-line bg-desk-panel/60 p-4">
      <div className="mb-2 flex items-baseline justify-between">
        <span className="font-mono text-[10px] uppercase tracking-widest text-desk-faint">
          equity curve
        </span>
        <span className={`font-mono text-xs font-semibold tabular-nums ${up ? "text-emerald-400" : "text-red-400"}`}>
          {up ? "+" : ""}
          {(stats.equity_usd - stats.bankroll_usd).toLocaleString("en-US", {
            style: "currency",
            currency: "USD",
          })}{" "}
          all-time
        </span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Equity over time">
        {/* starting-bankroll baseline */}
        <line
          x1={PAD}
          x2={W - PAD}
          y1={y(stats.bankroll_usd)}
          y2={y(stats.bankroll_usd)}
          stroke="#243247"
          strokeDasharray="4 4"
        />
        <text
          x={W - PAD}
          y={y(stats.bankroll_usd) - 4}
          textAnchor="end"
          className="fill-[#516075] font-mono"
          fontSize="9"
        >
          start {stats.bankroll_usd.toLocaleString()}
        </text>
        <path d={path} fill="none" stroke="#F0B441" strokeWidth="1.75" />
        <circle
          cx={x(points[points.length - 1].t)}
          cy={y(points[points.length - 1].v)}
          r="3"
          fill="#F0B441"
        />
      </svg>
    </div>
  );
}
