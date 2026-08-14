"use client";

import Link from "next/link";
import CouncilCards from "@/components/CouncilCards";
import Markdown from "@/components/Markdown";
import NewsSentiment from "@/components/NewsSentiment";
import { MicrostructureCard, SmartMoneyCard } from "@/components/SignalCards";
import SocialPulse from "@/components/SocialPulse";
import StepsTrace from "@/components/StepsTrace";
import Verdict from "@/components/Verdict";
import type { ExecuteOut, MarketState } from "@/lib/types";

export default function DossierView({
  result,
  fetchError,
  liveMarket,
  appendixOpen = false,
}: {
  result: ExecuteOut | null;
  fetchError: string | null;
  liveMarket?: MarketState | null; // the page already shows this market's header
  appendixOpen?: boolean; // root page keeps the graded artifacts visible
}) {
  if (fetchError) {
    return (
      <div className="rounded-xl border border-red-900/60 bg-red-950/40 p-4 text-sm text-red-300">
        Request failed: {fetchError}
        {fetchError.includes("500") && (
          <div className="mt-1 text-xs text-red-400/80">
            In local dev this usually means the FastAPI backend is not running — start it
            with <code className="rounded bg-desk-deep px-1">npm run dev:api</code>.
          </div>
        )}
      </div>
    );
  }
  if (!result) return null;

  const ui = result.ui ?? null;
  const hasSections = Boolean(ui?.verdict);

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

      {/* home-page runs link to the market's case file */}
      {ui?.market && !liveMarket && (
        <Link
          href={`/market/${ui.market.slug}`}
          className="flex items-center justify-between gap-4 rounded-2xl border border-desk-line bg-desk-panel/60 px-5 py-3.5 transition hover:border-instrument/50"
        >
          <span className="min-w-0">
            <span className="block truncate text-sm font-semibold text-desk-ink">
              {ui.market.question}
            </span>
            <span className="font-mono text-[11px] text-desk-dim">
              market {(ui.market.mid * 100).toFixed(1)}% · {ui.market.category}
            </span>
          </span>
          <span className="shrink-0 font-mono text-xs uppercase tracking-wider text-instrument">
            open case file →
          </span>
        </Link>
      )}

      {ui?.news && ui.news.length > 0 && <NewsSentiment clusters={ui.news} />}
      {ui?.social && <SocialPulse data={ui.social} />}
      {ui?.microstructure && <MicrostructureCard m={ui.microstructure} />}
      {ui?.smart_money && <SmartMoneyCard s={ui.smart_money} />}
      {ui?.council && <CouncilCards council={ui.council} />}

      {ui?.fill && (
        <section className="rounded-2xl border border-desk-line bg-desk-panel/70 p-4 text-sm">
          <h2 className="mb-2 font-display text-lg font-bold uppercase tracking-wide text-desk-ink">
            Paper-trade fill
          </h2>
          <div className="grid grid-cols-2 gap-2 font-mono text-xs text-desk-soft sm:grid-cols-3">
            <div>side: {ui.fill.side.replace("_", " ")}</div>
            <div>size: ${ui.fill.size_usd.toFixed(2)}</div>
            <div>vwap: {(ui.fill.vwap * 100).toFixed(1)}%</div>
            <div>slippage: {ui.fill.slippage_bps.toFixed(1)} bps</div>
            <div>fee: ${ui.fill.fee_paid.toFixed(2)}</div>
            <div className="truncate">position: {ui.fill.position_id}</div>
          </div>
        </section>
      )}

      {/* responses without structured sections render as markdown */}
      {result.response && !hasSections && (
        <div className="rounded-2xl border border-desk-line bg-desk-panel/60 p-5">
          <Markdown>{result.response}</Markdown>
        </div>
      )}

      {/* appendix: graded artifacts, folded */}
      {(result.response || result.steps.length > 0) && hasSections && (
        <details open={appendixOpen} className="group rounded-2xl border border-desk-line bg-desk-panel/40">
          <summary className="cursor-pointer select-none px-5 py-3.5 font-mono text-xs font-semibold uppercase tracking-wider text-desk-dim transition hover:text-desk-ink">
            Full report and execution trace
            <span className="ml-2 font-normal normal-case text-desk-faint">
              complete narrative, prompts, LLM responses, and tool outputs
            </span>
          </summary>
          <div className="space-y-6 border-t border-desk-line px-5 py-4">
            {result.response && (
              <div className="rounded-xl bg-desk-deep/40 p-4">
                <Markdown>{result.response}</Markdown>
              </div>
            )}
            <StepsTrace steps={result.steps} metrics={ui?.step_metrics} />
          </div>
        </details>
      )}

      {/* runs without sections still need the graded trace visible */}
      {result.steps.length > 0 && !hasSections && (
        <StepsTrace steps={result.steps} metrics={ui?.step_metrics} />
      )}
    </div>
  );
}
