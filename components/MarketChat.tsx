"use client";

import ChatPanel, { CitationsList, GatheredBadge } from "@/components/ChatPanel";
import { marketChat, type MarketChatResult } from "@/lib/api";

type Extras = Pick<MarketChatResult, "citations" | "gathered">;

export default function MarketChat({ slug }: { slug: string }) {
  return (
    <ChatPanel<Extras>
      title="Ask the desk"
      hint="grounded answers · searches web & socials when it needs fresh evidence"
      emptyText={
        <>
          Ask anything about this market — &ldquo;what&apos;s the latest news?&rdquo;,
          &ldquo;why did the price move today?&rdquo;, &ldquo;what would make this resolve
          NO?&rdquo;. The agent answers from its dossier and, when needed, searches the
          web and social chatter first — indexing what it finds for future analyses.
        </>
      }
      placeholder="Ask about this market…"
      busyLabel="thinking — may search & index sources…"
      send={async (question, history) => {
        const res = await marketChat(slug, question, history);
        return {
          content: res.answer ?? "(no answer)",
          extras: { citations: res.citations, gathered: res.gathered },
        };
      }}
      renderExtrasTop={(e) => <GatheredBadge gathered={e.gathered} />}
      renderExtrasBottom={(e) => <CitationsList citations={e.citations} />}
    />
  );
}
