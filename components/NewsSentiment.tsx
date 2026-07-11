"use client";

import type { EvidenceCluster } from "@/lib/types";

function SentimentChip({ sentiment }: { sentiment: number | null }) {
  if (sentiment === null || sentiment === undefined)
    return <span className="rounded bg-slate-800 px-1.5 py-0.5 text-xs text-slate-400">n/a</span>;
  const positive = sentiment > 0.15;
  const negative = sentiment < -0.15;
  const cls = positive
    ? "bg-emerald-950 text-emerald-300 border-emerald-800"
    : negative
      ? "bg-red-950 text-red-300 border-red-800"
      : "bg-slate-800 text-slate-300 border-slate-700";
  return (
    <span className={`rounded border px-1.5 py-0.5 text-xs font-medium ${cls}`}>
      {sentiment > 0 ? "+" : ""}
      {sentiment.toFixed(2)}
    </span>
  );
}

function age(date: string | null): string {
  if (!date) return "";
  const days = Math.floor((Date.now() - new Date(date).getTime()) / 86_400_000);
  if (days <= 0) return "today";
  return days === 1 ? "1d ago" : `${days}d ago`;
}

export default function NewsSentiment({ clusters }: { clusters: EvidenceCluster[] }) {
  if (!clusters.length) return null;
  return (
    <section>
      <h2 className="mb-3 text-lg font-semibold text-slate-200">News &amp; sentiment</h2>
      <div className="space-y-2">
        {clusters.map((c) => (
          <div key={c.id} className="rounded-lg border border-slate-800 bg-slate-900 p-3">
            <div className="flex items-start justify-between gap-3">
              <a
                href={c.url}
                target="_blank"
                rel="noreferrer"
                className="text-sm font-medium text-slate-100 hover:text-sky-400"
              >
                <span className="mr-2 font-mono text-xs text-slate-500">{c.id}</span>
                {c.headline}
              </a>
              <SentimentChip sentiment={c.sentiment} />
            </div>
            <div className="mt-1 text-xs text-slate-500">
              {c.source} · {age(c.date)}
              {c.stance && c.stance !== "neutral" && (
                <span className="ml-2 uppercase">leans {c.stance}</span>
              )}
            </div>
            {c.summary && <p className="mt-1 text-xs text-slate-400">{c.summary}</p>}
          </div>
        ))}
      </div>
    </section>
  );
}
