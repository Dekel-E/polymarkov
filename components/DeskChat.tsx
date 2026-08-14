"use client";

import Link from "next/link";
import ChatPanel, { CitationsList, GatheredBadge } from "@/components/ChatPanel";
import { deskChat, type DeskChatResult } from "@/lib/api";
import type { AgentSettings } from "@/lib/types";

type Extras = Pick<
  DeskChatResult,
  "citations" | "gathered" | "market" | "fill" | "watchlisted" | "analyzed" | "closed"
>;

// Replayed into history so the model remembers what it actually did, not just
// what it wrote — "close that one" needs the earlier trade to be on the record.
function summarizeExtras(e: Extras): string | null {
  const parts: string[] = [];
  if (e.market) parts.push(`market: ${e.market.slug}`);
  if (e.analyzed) parts.push(`ran full analysis · verdict ${e.analyzed.verdict ?? "n/a"}`);
  if (e.fill) parts.push(`placed paper trade: ${e.fill.side} $${e.fill.size_usd.toFixed(0)}`);
  if (e.closed) parts.push(`closed position ${e.closed.position_id} · pnl $${e.closed.pnl.toFixed(2)}`);
  if (e.watchlisted) parts.push(`watchlist ${e.watchlisted.action}: ${e.watchlisted.slug}`);
  return parts.length ? parts.join(" · ") : null;
}

// The single omni-chat. Talks about markets, runs paper trades, edits the
// watchlist, reports the portfolio, controls the desk, and describes itself.
// `slug` scopes "buy $50 yes" / "watch this" / "what's the latest?" to the
// market in view; `onApplied` lets a page refresh after a control instruction.
export default function DeskChat({
  slug,
  onApplied,
}: {
  slug?: string;
  onApplied?: (settings: AgentSettings) => void;
}) {
  return (
    <div className="max-w-3xl">
      <ChatPanel<Extras>
        title="Ask the desk"
        hint="ask · analyze · trade · watch · control"
        emptyText={
          <>
            Ask for market research, a full analysis, or portfolio status. You can also
            place and close paper trades, manage the watchlist, or change risk settings—for
            example, &ldquo;analyze this market&rdquo; or &ldquo;set the stop-loss to 30%.&rdquo;
          </>
        }
        placeholder={
          slug
            ? "Ask, analyze, “buy $50 yes”, “close it”, “watch this”…"
            : "Ask, analyze, trade, close, watch, or instruct the agent…"
        }
        busyLabel="Working—complex research may take about a minute…"
        storageKey={slug ? `polymarkov.chat.${slug}` : "polymarkov.chat.desk"}
        summarizeExtras={summarizeExtras}
        send={async (question, history) => {
          const res = await deskChat(question, history, slug);
          if (res.settings && onApplied) onApplied(res.settings);
          return {
            content: res.answer ?? "(no answer)",
            extras: {
              citations: res.citations,
              gathered: res.gathered,
              market: res.market,
              fill: res.fill,
              watchlisted: res.watchlisted,
              analyzed: res.analyzed,
              closed: res.closed,
            },
          };
        }}
        renderExtrasTop={(e) => (
          <>
            {e.market && !slug && (
              <Link
                href={`/market/${e.market.slug}`}
                className="mb-1.5 block truncate font-mono text-[10px] uppercase tracking-wider text-instrument hover:underline"
              >
                ↳ {e.market.question}
              </Link>
            )}
            {e.analyzed && (
              <div className="mb-1.5 inline-block rounded bg-instrument/15 px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wider text-instrument">
                full analysis{e.analyzed.verdict ? ` · ${e.analyzed.verdict.replace("_", " ")}` : ""}
              </div>
            )}
            {e.fill && (
              <div className="mb-1.5 inline-block rounded bg-emerald-400/15 px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wider text-emerald-400">
                paper fill · {e.fill.side.replace("_", " ")} ${e.fill.size_usd.toFixed(0)}
              </div>
            )}
            {e.closed && (
              <div
                className={`mb-1.5 inline-block rounded px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wider ${
                  e.closed.pnl >= 0
                    ? "bg-emerald-400/15 text-emerald-400"
                    : "bg-red-400/15 text-red-400"
                }`}
              >
                closed{e.closed.fraction < 0.999 ? ` ${(e.closed.fraction * 100).toFixed(0)}%` : ""} ·
                pnl ${e.closed.pnl.toFixed(2)}
              </div>
            )}
            {e.watchlisted && (
              <div className="mb-1.5 inline-block rounded bg-instrument/15 px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wider text-instrument">
                watchlist · {e.watchlisted.action}ed
              </div>
            )}
            <GatheredBadge gathered={e.gathered} />
          </>
        )}
        renderExtrasBottom={(e) => <CitationsList citations={e.citations} />}
      />
    </div>
  );
}
