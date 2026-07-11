"use client";

import CouncilCards from "@/components/CouncilCards";
import MarketPanel from "@/components/MarketPanel";
import NewsSentiment from "@/components/NewsSentiment";
import SocialPulse from "@/components/SocialPulse";
import StepsTrace from "@/components/StepsTrace";
import Verdict from "@/components/Verdict";
import type { ExecuteOut, MarketState } from "@/lib/types";

export default function DossierView({
  result,
  fetchError,
  liveMarket,
}: {
  result: ExecuteOut | null;
  fetchError: string | null;
  liveMarket?: MarketState | null; // already shown by the page? then skip ui.market
}) {
  if (fetchError) {
    return (
      <div className="rounded-xl border border-red-900/60 bg-red-950/40 p-4 text-sm text-red-300">
        Request failed: {fetchError}
        {fetchError.includes("500") && (
          <div className="mt-1 text-xs text-red-400/80">
            In local dev this usually means the FastAPI backend is not running — start it
            with <code className="rounded bg-desk-panel px-1">npm run dev:api</code>.
          </div>
        )}
      </div>
    );
  }
  if (!result) return null;

  const ui = result.ui ?? null;
  return (
    <div className="space-y-8">
      {result.status === "error" && (
        <div className="rounded-xl border border-red-900/60 bg-red-950/40 p-4 text-sm text-red-300">
          Agent error: {result.error}
        </div>
      )}

      {ui?.verdict && (
        <Verdict data={ui.verdict} market={ui.market ?? liveMarket ?? undefined} />
      )}
      {ui?.market && !liveMarket && <MarketPanel market={ui.market} />}
      {ui?.news && ui.news.length > 0 && <NewsSentiment clusters={ui.news} />}
      {ui?.social && <SocialPulse data={ui.social} />}
      {ui?.council && <CouncilCards council={ui.council} />}

      {ui?.fill && (
        <section className="rounded-xl border border-desk-line bg-desk-panel p-4 text-sm">
          <h2 className="mb-2 text-lg font-semibold text-desk-ink">Paper-trade fill</h2>
          <div className="grid grid-cols-2 gap-2 text-desk-soft sm:grid-cols-3">
            <div>Side: {ui.fill.side}</div>
            <div>Size: ${ui.fill.size_usd.toFixed(2)}</div>
            <div>VWAP: {(ui.fill.vwap * 100).toFixed(1)}%</div>
            <div>Slippage: {ui.fill.slippage_bps.toFixed(1)} bps</div>
            <div>Fee: ${ui.fill.fee_paid.toFixed(2)}</div>
            <div className="truncate">Position: {ui.fill.position_id}</div>
          </div>
        </section>
      )}

      {result.response && (
        <section>
          <h2 className="mb-3 font-display text-lg font-bold uppercase tracking-wide text-desk-ink">
            Full report
          </h2>
          <div className="whitespace-pre-wrap rounded-xl border border-desk-line bg-desk-panel p-5 text-sm leading-relaxed text-desk-ink">
            {result.response}
          </div>
        </section>
      )}

      <StepsTrace steps={result.steps} />
    </div>
  );
}
