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
      <h2 className="mb-3 font-display text-lg font-bold uppercase tracking-wide text-desk-ink">
        Social pulse
      </h2>
      <div className="rounded-lg border border-desk-line bg-desk-panel p-4">
        <div className="flex flex-wrap gap-x-8 gap-y-2 text-sm">
          <div>
            <span className="text-desk-dim">Aggregate sentiment: </span>
            <span className="font-semibold text-desk-ink">
              {avg === null ? "n/a" : `${avg > 0 ? "+" : ""}${avg.toFixed(2)}`}
            </span>
          </div>
          <div>
            <span className="text-desk-dim">Mention velocity: </span>
            <span className="font-semibold text-desk-ink">
              {data.mention_velocity === null ? "n/a" : `${data.mention_velocity}x`}
            </span>
          </div>
          <div>
            <span className="text-desk-dim">Posts: </span>
            <span className="font-semibold text-desk-ink">{data.posts.length}</span>
          </div>
        </div>
        {data.note && <p className="mt-2 text-xs text-desk-dim">{data.note}</p>}
      </div>
    </section>
  );
}
