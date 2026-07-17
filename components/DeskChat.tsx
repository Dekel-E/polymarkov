"use client";

import Link from "next/link";
import ChatPanel, { CitationsList, GatheredBadge } from "@/components/ChatPanel";
import { deskChat, type DeskChatResult } from "@/lib/api";

type Extras = Pick<DeskChatResult, "citations" | "gathered" | "market">;

export default function DeskChat() {
  return (
    <div className="max-w-3xl">
      <ChatPanel<Extras>
        title="Ask the desk"
        hint="markets · portfolio · strategy controls · what the agent can do"
        emptyText={
          <>
            Talk to the agent about anything it knows: a market (&ldquo;what&apos;s the
            latest on the Fed cutting in September?&rdquo;), the paper portfolio
            (&ldquo;what did you trade today?&rdquo;), the strategy desk (&ldquo;turn off
            copy trading&rdquo;, &ldquo;halt everything&rdquo;), or itself (&ldquo;what can
            you do?&rdquo;). It searches and indexes fresh sources when a question needs
            them.
          </>
        }
        placeholder="Ask about a market, the portfolio, or instruct the agent…"
        busyLabel="thinking — may search & index sources…"
        send={async (question, history) => {
          const res = await deskChat(question, history);
          return {
            content: res.answer ?? "(no answer)",
            extras: { citations: res.citations, gathered: res.gathered, market: res.market },
          };
        }}
        renderExtrasTop={(e) => (
          <>
            {e.market && (
              <Link
                href={`/market/${e.market.slug}`}
                className="mb-1.5 block truncate font-mono text-[10px] uppercase tracking-wider text-instrument hover:underline"
              >
                ↳ {e.market.question}
              </Link>
            )}
            <GatheredBadge gathered={e.gathered} />
          </>
        )}
        renderExtrasBottom={(e) => <CitationsList citations={e.citations} />}
      />
    </div>
  );
}
