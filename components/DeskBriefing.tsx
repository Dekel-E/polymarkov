"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import Markdown from "@/components/Markdown";

interface AgendaItem {
  market_id: string;
  reason: string;
  priority: number;
  created_at: string;
}

export default function DeskBriefing() {
  const [briefing, setBriefing] = useState<{ content: string; created_at: string } | null | undefined>(undefined);
  const [agendaItems, setAgendaItems] = useState<AgendaItem[]>([]);

  useEffect(() => {
    fetch("/api/briefing")
      .then((r) => r.json())
      .then((d) => setBriefing(d.briefing ?? null))
      .catch(() => setBriefing(null));
    fetch("/api/agenda")
      .then((r) => r.json())
      .then((d) => setAgendaItems(d.items ?? []))
      .catch(() => undefined);
  }, []);

  if (briefing === undefined) return <div className="h-24 animate-pulse rounded-2xl bg-desk-panel" />;

  return (
    <div className="grid gap-3 lg:grid-cols-[3fr_2fr]">
      <section className="rounded-2xl border border-desk-line bg-desk-panel/60 p-5">
        <div className="mb-3 flex items-baseline justify-between">
          <h2 className="font-mono text-[11px] font-semibold uppercase tracking-wider text-instrument">
            morning briefing
          </h2>
          {briefing && (
            <span className="font-mono text-[10px] text-desk-faint">
              {new Date(briefing.created_at).toLocaleString()}
            </span>
          )}
        </div>
        {briefing ? (
          <Markdown>{briefing.content}</Markdown>
        ) : (
          <p className="text-sm text-desk-dim">
            No briefing yet — the agent writes one every morning at 06:00 UTC once the
            autonomy schedule is running.
          </p>
        )}
      </section>

      <section className="rounded-2xl border border-desk-line bg-desk-panel/60 p-5">
        <h2 className="mb-3 font-mono text-[11px] font-semibold uppercase tracking-wider text-instrument">
          agenda · {agendaItems.length} pending
        </h2>
        {agendaItems.length === 0 ? (
          <p className="text-sm text-desk-dim">
            Clear. The sentinel files items here when it notices price moves, positions
            at risk, news bursts, or approaching resolutions.
          </p>
        ) : (
          <div className="space-y-2">
            {agendaItems.map((item, i) => (
              <div key={i} className="flex items-baseline gap-2.5 text-xs">
                <span className="w-10 shrink-0 text-right font-mono text-[10px] font-bold text-instrument">
                  {Number(item.priority).toFixed(0)}
                </span>
                <span className="min-w-0">
                  <Link
                    href={`/market/${item.market_id}`}
                    className="block truncate font-mono text-desk-soft hover:text-instrument"
                  >
                    {item.market_id}
                  </Link>
                  <span className="text-desk-faint">{item.reason}</span>
                </span>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
