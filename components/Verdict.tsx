"use client";

import type { MarketState, VerdictData } from "@/lib/types";

const STYLES: Record<VerdictData["verdict"], { bg: string; label: string }> = {
  BUY_YES: { bg: "border-emerald-700 bg-emerald-950/50 text-emerald-300", label: "BUY YES" },
  BUY_NO: { bg: "border-red-700 bg-red-950/50 text-red-300", label: "BUY NO" },
  PASS: { bg: "border-zinc-700 bg-zinc-900 text-zinc-300", label: "PASS" },
};

export default function Verdict({
  data,
  market,
}: {
  data: VerdictData;
  market?: MarketState;
}) {
  const style = STYLES[data.verdict];
  return (
    <section className={`rounded-lg border p-4 ${style.bg}`}>
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="text-2xl font-bold tracking-tight">{style.label}</div>
        <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
          <div>
            <span className="text-zinc-400">Fair: </span>
            <span className="font-semibold">{(data.fair_probability * 100).toFixed(1)}%</span>
            {market && (
              <span className="text-zinc-400">
                {" "}
                vs market {(market.mid * 100).toFixed(1)}%
              </span>
            )}
          </div>
          <div>
            <span className="text-zinc-400">Net edge: </span>
            <span className="font-semibold">{(data.net_edge_pts * 100).toFixed(1)} pts</span>
          </div>
          <div>
            <span className="text-zinc-400">Size: </span>
            <span className="font-semibold">
              {data.suggested_size_pct_bankroll.toFixed(1)}% bankroll
            </span>
          </div>
          <div>
            <span className="text-zinc-400">Confidence: </span>
            <span className="font-semibold">{data.confidence}</span>
          </div>
        </div>
      </div>
      {data.summary && <p className="mt-3 text-sm leading-relaxed">{data.summary}</p>}
      {data.key_risks?.length > 0 && (
        <ul className="mt-2 list-inside list-disc text-xs text-zinc-400">
          {data.key_risks.map((r, i) => (
            <li key={i}>{r}</li>
          ))}
        </ul>
      )}
    </section>
  );
}
