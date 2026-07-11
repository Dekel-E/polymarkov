"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { fetchActivity, type ActivityEvent } from "@/lib/api";

function when(iso: string): string {
  const mins = Math.floor((Date.now() - new Date(iso).getTime()) / 60_000);
  if (mins < 1) return "now";
  if (mins < 60) return `${mins}m`;
  const hours = Math.floor(mins / 60);
  return hours < 24 ? `${hours}h` : `${Math.floor(hours / 24)}d`;
}

function line(e: ActivityEvent): React.ReactNode {
  if (e.type === "analysis") {
    return (
      <>
        analyzed <MarketRef id={e.market_id} /> →{" "}
        <b className={e.verdict?.startsWith("BUY") ? "text-emerald-400" : "text-desk-soft"}>
          {(e.verdict ?? "?").replace("_", " ")}
        </b>
        {e.latency_ms ? ` in ${Math.round(e.latency_ms / 1000)}s` : ""}
      </>
    );
  }
  if (e.type === "trade") {
    return (
      <>
        opened{" "}
        <b className={e.side === "BUY_YES" ? "text-emerald-400" : "text-red-400"}>
          {(e.side ?? "").replace("_", " ")}
        </b>{" "}
        ${e.size_usd?.toFixed(0)} on <MarketRef id={e.market_id} />
        {e.strategy ? <span className="text-desk-faint"> · {e.strategy.replace("_", " ")}</span> : null}
      </>
    );
  }
  const pnl = e.pnl ?? 0;
  return (
    <>
      settled <MarketRef id={e.market_id} /> ({e.outcome}) →{" "}
      <b className={pnl >= 0 ? "text-emerald-400" : "text-red-400"}>
        {pnl >= 0 ? "+" : ""}${pnl.toFixed(2)}
      </b>
    </>
  );
}

function MarketRef({ id }: { id: string | null }) {
  if (!id) return <span className="text-desk-faint">unknown market</span>;
  return (
    <Link href={`/market/${id}`} className="text-desk-soft underline decoration-desk-line underline-offset-2 hover:text-instrument">
      {id.length > 42 ? `${id.slice(0, 40)}…` : id}
    </Link>
  );
}

export default function ActivityFeed() {
  const [events, setEvents] = useState<ActivityEvent[] | null>(null);

  useEffect(() => {
    fetchActivity()
      .then(setEvents)
      .catch(() => setEvents([]));
  }, []);

  return (
    <section>
      <h2 className="mb-3 font-display text-lg font-bold uppercase tracking-wide">
        Activity
        <span className="ml-2 font-mono text-[11px] font-normal normal-case tracking-normal text-desk-faint">
          what the agent has been doing
        </span>
      </h2>
      {events === null && <div className="h-24 animate-pulse rounded-2xl bg-desk-panel" />}
      {events !== null && events.length === 0 && (
        <div className="rounded-xl border border-desk-line bg-desk-panel/60 p-5 text-sm text-desk-dim">
          Nothing yet — activity appears here after the first analysis or scheduled run.
        </div>
      )}
      {events !== null && events.length > 0 && (
        <div className="overflow-hidden rounded-2xl border border-desk-line bg-desk-panel/60">
          {events.map((e, i) => (
            <div
              key={i}
              className="flex items-baseline gap-3 border-b border-desk-line/60 px-4 py-2.5 text-xs last:border-0"
            >
              <span className="w-8 shrink-0 text-right font-mono text-[10px] text-instrument">
                {when(e.at)}
              </span>
              <span className="min-w-0 flex-1 truncate font-mono text-desk-dim">{line(e)}</span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
