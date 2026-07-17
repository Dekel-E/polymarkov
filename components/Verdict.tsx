"use client";

import type { MarketState, VerdictData } from "@/lib/types";

const STAMP: Record<VerdictData["verdict"], { cls: string; label: string; glow: string }> = {
  BUY_YES: { cls: "border-emerald-400 text-emerald-400", label: "BUY YES", glow: "text-glow-emerald" },
  BUY_NO: { cls: "border-red-400 text-red-400", label: "BUY NO", glow: "text-glow-red" },
  PASS: { cls: "border-desk-edge text-desk-dim", label: "PASS", glow: "" },
};

function Metric({ label, value, hero }: { label: string; value: string; hero?: boolean }) {
  return (
    <div>
      <div className="font-mono text-[10px] uppercase tracking-widest text-desk-faint">
        {label}
      </div>
      <div
        className={`mt-0.5 font-mono font-semibold text-desk-ink ${
          hero ? "text-base text-instrument text-glow" : "text-sm"
        }`}
      >
        {value}
      </div>
    </div>
  );
}

export default function Verdict({
  data,
  market,
}: {
  data: VerdictData;
  market?: MarketState;
}) {
  const stamp = STAMP[data.verdict];
  return (
    <section className="desk-rise rounded-2xl border border-desk-line bg-desk-panel/70 p-5">
      <div className="flex flex-wrap items-start gap-6">
        {/* the stamp: pressed onto the dossier, slightly off-axis */}
        <div className="flex min-w-[128px] items-center justify-center py-2">
          <div
            className={`desk-stamp rounded border-[3px] px-4 py-1.5 font-display text-2xl font-bold uppercase tracking-[0.18em] ${stamp.cls} ${stamp.glow}`}
            aria-label={`Verdict: ${stamp.label}`}
          >
            {stamp.label}
          </div>
        </div>

        <div className="min-w-0 flex-1">
          <div className="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-4">
            <Metric
              label="fair value"
              hero
              value={`${(data.fair_probability * 100).toFixed(1)}%${
                market ? ` vs ${(market.mid * 100).toFixed(1)}%` : ""
              }`}
            />
            <Metric label="net edge" value={`${(data.net_edge_pts * 100).toFixed(1)} pts`} />
            <Metric
              label="size"
              value={`${data.suggested_size_pct_bankroll.toFixed(1)}% bankroll`}
            />
            <Metric label="confidence" value={data.confidence} />
          </div>
          {data.summary && (
            <p className="mt-4 text-sm leading-relaxed text-desk-soft">{data.summary}</p>
          )}
          {data.key_risks?.length > 0 && (
            <ul className="mt-3 space-y-1 text-xs text-desk-dim">
              {data.key_risks.map((r, i) => (
                <li key={i} className="flex gap-2">
                  <span className="text-instrument">▲</span>
                  {r}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </section>
  );
}
