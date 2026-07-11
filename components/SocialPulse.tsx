"use client";

import type { SocialPulse as SocialPulseData } from "@/lib/types";

export default function SocialPulse({ data }: { data: SocialPulseData }) {
  const sentiments = data.posts
    .map((p) => p.sentiment)
    .filter((s): s is number => s !== null && s !== undefined);
  const avg =
    sentiments.length > 0
      ? sentiments.reduce((a, b) => a + b, 0) / sentiments.length
      : null;

  return (
    <section>
      <h2 className="mb-3 text-lg font-semibold text-slate-200">Social pulse</h2>
      <div className="rounded-lg border border-slate-800 bg-slate-900 p-4">
        <div className="flex flex-wrap gap-x-8 gap-y-2 text-sm">
          <div>
            <span className="text-slate-400">Aggregate sentiment: </span>
            <span className="font-semibold text-slate-100">
              {avg === null ? "n/a" : `${avg > 0 ? "+" : ""}${avg.toFixed(2)}`}
            </span>
          </div>
          <div>
            <span className="text-slate-400">Mention velocity: </span>
            <span className="font-semibold text-slate-100">
              {data.mention_velocity === null ? "n/a" : `${data.mention_velocity}×`}
            </span>
          </div>
          <div>
            <span className="text-slate-400">Posts: </span>
            <span className="font-semibold text-slate-100">{data.posts.length}</span>
          </div>
        </div>
        {data.note && <p className="mt-2 text-xs text-slate-500">{data.note}</p>}
      </div>
    </section>
  );
}
