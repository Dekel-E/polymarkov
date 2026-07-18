"use client";

import Link from "next/link";
import ChatPanel, { CitationsList, GatheredBadge } from "@/components/ChatPanel";
import { deskChat, type DeskChatResult } from "@/lib/api";
import type { AgentSettings } from "@/lib/types";

type Extras = Pick<DeskChatResult, "citations" | "gathered" | "market" | "fill" | "watchlisted">;

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
            One chat for everything the agent can do. Ask about a market
            (&ldquo;what&apos;s the latest on the Fed cutting in September?&rdquo;), place a
            paper trade (&ldquo;buy $50 yes on the election&rdquo;), manage the watchlist
            (&ldquo;watch this market&rdquo;), check the paper book (&ldquo;how&apos;s the
            portfolio?&rdquo;), or steer the desk (&ldquo;set stop loss to 30%&rdquo;,
            &ldquo;halt everything&rdquo;). If it can do it, it does it — paper trading
            only, not financial advice.
          </>
        }
        placeholder={
          slug
            ? "Ask about this market, or say “buy $50 yes” / “watch this”…"
            : "Ask, analyze, trade, watch, or instruct the agent…"
        }
        busyLabel="working — may search, index, or trade…"
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
            {e.fill && (
              <div className="mb-1.5 inline-block rounded bg-emerald-400/15 px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wider text-emerald-400">
                paper fill · {e.fill.side.replace("_", " ")} ${e.fill.size_usd.toFixed(0)}
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
