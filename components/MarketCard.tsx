"use client";

import Link from "next/link";
import type { MarketSummary } from "@/lib/types";

function formatVolume(v: number): string {
  if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `$${(v / 1_000).toFixed(0)}k`;
  return `$${v.toFixed(0)}`;
}

function daysLeft(endDate: string | null): string | null {
  if (!endDate) return null;
  const days = Math.ceil((new Date(endDate).getTime() - Date.now()) / 86_400_000);
  if (days < 0) return "ending";
  if (days === 0) return "today";
  return `${days}d`;
}

export default function MarketCard({ market }: { market: MarketSummary }) {
  const days = daysLeft(market.end_date);
  const prob = market.mid * 100;
  return (
    <Link
      href={`/market/${market.slug}`}
      className="group flex flex-col rounded-2xl border border-desk-line bg-desk-panel/70 p-4 transition hover:-translate-y-0.5 hover:border-desk-faint hover:bg-desk-panel"
    >
      <div className="flex items-start gap-3">
        {market.image ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={market.image} alt="" className="h-10 w-10 shrink-0 rounded-lg object-cover" />
        ) : (
          <div className="h-10 w-10 shrink-0 rounded-lg bg-desk-line" />
        )}
        <h3 className="line-clamp-2 flex-1 text-sm font-semibold leading-snug text-desk-ink">
          {market.question}
        </h3>
      </div>

      <div className="mt-4 flex items-end justify-between">
        <div>
          <div className="text-[11px] uppercase tracking-wider text-desk-dim">
            Market probability
          </div>
          <div
            className={`text-3xl font-bold tabular-nums tracking-tight ${
              prob >= 50 ? "text-emerald-400" : "text-desk-ink"
            }`}
          >
            {prob < 1 ? prob.toFixed(1) : prob.toFixed(0)}%
          </div>
        </div>
        <div className="text-right text-xs text-desk-dim">
          <div>{formatVolume(market.volume24h)} / 24h</div>
          {days && (
            <div className="mt-0.5 flex items-center justify-end gap-1">
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="9" />
                <path d="M12 7v5l3 2" />
              </svg>
              {days}
            </div>
          )}
        </div>
      </div>

      <div className="mt-4 flex items-center justify-between border-t border-desk-line/80 pt-3">
        <span className="rounded-md bg-desk-line/80 px-2 py-0.5 text-[11px] capitalize text-desk-dim">
          {market.category || "other"}
        </span>
        <span className="rounded-lg border border-instrument/50 px-3 py-1 text-xs font-semibold text-instrument transition group-hover:bg-instrument/10">
          Full analysis →
        </span>
      </div>
    </Link>
  );
}
