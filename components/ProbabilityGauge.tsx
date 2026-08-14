"use client";

import { useEffect, useState } from "react";

// 0-100 probability axis: market price below the track, deterministic agent fair value
// above it, the shaded span between them is the edge.
export default function ProbabilityGauge({
  market,
  fair,
}: {
  market: number; // 0..1
  fair?: number | null; // 0..1, present once a dossier exists
}) {
  // fair marker slides from the market position on mount; disabled under prefers-reduced-motion via CSS
  const [fairPos, setFairPos] = useState(market);
  useEffect(() => {
    if (fair == null) return;
    const id = requestAnimationFrame(() => setFairPos(fair));
    return () => cancelAnimationFrame(id);
  }, [fair]);

  const mPct = Math.min(99, Math.max(1, market * 100));
  const fPct = Math.min(99, Math.max(1, fairPos * 100));
  const hasFair = fair != null;
  const edgeUp = hasFair && fair! > market;
  const spanLeft = Math.min(mPct, fPct);
  const spanWidth = Math.abs(fPct - mPct);
  const clampLabel = (p: number) => Math.min(88, Math.max(4, p));

  return (
    <div className="select-none" role="img" aria-label={
      hasFair
    ? `Market ${Math.round(market * 100)} percent, agent fair value ${Math.round(fair! * 100)} percent`
        : `Market ${Math.round(market * 100)} percent, fair value not yet assessed`
    }>
      {/* fair value label, above the track */}
      <div className="relative h-6">
        {hasFair ? (
          <div
            className="absolute -translate-x-1/2 whitespace-nowrap font-mono text-[11px] font-semibold uppercase tracking-wider text-instrument text-glow transition-[left] duration-700 ease-out motion-reduce:transition-none"
            style={{ left: `${clampLabel(fPct)}%` }}
          >
          agent fair {(fairPos * 100).toFixed(1)}%
          </div>
        ) : (
          <div className="absolute left-0 font-mono text-[11px] uppercase tracking-wider text-desk-faint">
            fair value — not yet assessed
          </div>
        )}
      </div>

      {/* fair marker (▼ from above) */}
      <div className="relative h-2">
        {hasFair && (
          <div
            className="absolute -translate-x-1/2 transition-[left] duration-700 ease-out motion-reduce:transition-none"
            style={{ left: `${fPct}%` }}
          >
            <div className="h-0 w-0 border-x-[5px] border-t-[7px] border-x-transparent border-t-instrument [filter:drop-shadow(0_0_5px_rgb(34_225_230_/_0.7))]" />
          </div>
        )}
      </div>

      {/* track */}
      <div className="relative h-2 rounded-full bg-desk-line">
        {[10, 20, 30, 40, 50, 60, 70, 80, 90].map((t) => (
          <div
            key={t}
            className={`absolute top-0 h-full w-px ${t === 50 ? "bg-desk-edge" : "bg-desk-panel"}`}
            style={{ left: `${t}%` }}
          />
        ))}
        {hasFair && spanWidth > 0.2 && (
          <div
            className={`absolute top-0 h-full ${edgeUp ? "bg-emerald-400/50" : "bg-red-400/50"} transition-all duration-700 ease-out motion-reduce:transition-none`}
            style={{ left: `${spanLeft}%`, width: `${spanWidth}%` }}
          />
        )}
      </div>

      {/* market marker (▲ from below) + labels */}
      <div className="relative h-2">
        <div className="absolute -translate-x-1/2" style={{ left: `${mPct}%` }}>
          <div className="h-0 w-0 border-x-[5px] border-b-[7px] border-x-transparent border-b-desk-ink" />
        </div>
      </div>
      <div className="relative h-6">
        <span className="absolute left-0 font-mono text-[10px] text-desk-faint">0</span>
        <span className="absolute left-1/2 -translate-x-1/2 font-mono text-[10px] text-desk-faint">50</span>
        <span className="absolute right-0 font-mono text-[10px] text-desk-faint">100</span>
        <div
          className="absolute -translate-x-1/2 whitespace-nowrap font-mono text-[11px] font-semibold uppercase tracking-wider text-desk-soft"
          style={{ left: `${clampLabel(mPct)}%` }}
        >
          market {(market * 100).toFixed(1)}%
        </div>
      </div>
    </div>
  );
}
