"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import DossierView from "@/components/DossierView";
import MarketPanel from "@/components/MarketPanel";
import { fetchMarketDetail } from "@/lib/api";
import type { MarketState } from "@/lib/types";
import { useAgentRun } from "@/lib/useAgentRun";

export default function MarketPage() {
  const { slug } = useParams<{ slug: string }>();
  const [market, setMarket] = useState<MarketState | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const { running, elapsed, result, fetchError, run } = useAgentRun();

  useEffect(() => {
    if (!slug) return;
    fetchMarketDetail(slug)
      .then(setMarket)
      .catch((e) => setLoadError(e instanceof Error ? e.message : String(e)));
  }, [slug]);

  function generateIntel() {
    run(`Market: ${slug}\nFocus: all\nTrade: no`);
  }

  return (
    <div className="mx-auto max-w-4xl space-y-8 px-4 py-8 md:px-8">
      <Link href="/" className="inline-flex items-center gap-1.5 text-sm text-zinc-500 transition hover:text-zinc-200">
        ← All markets
      </Link>

      {loadError && (
        <div className="rounded-xl border border-amber-900/60 bg-amber-950/30 p-4 text-sm text-amber-300">
          Could not load this market: {loadError}
        </div>
      )}

      {!market && !loadError && (
        <div className="h-52 animate-pulse rounded-2xl bg-zinc-900" />
      )}

      {market && (
        <>
          <MarketPanel market={market} onGenerate={generateIntel} running={running} />

          {market.resolution_criteria && (
            <details className="group rounded-xl border border-zinc-800 bg-zinc-900/60">
              <summary className="cursor-pointer select-none px-4 py-3 text-sm font-semibold text-zinc-300 transition hover:text-zinc-100">
                Resolution criteria
                <span className="ml-2 text-zinc-600 group-open:hidden">show</span>
              </summary>
              <p className="whitespace-pre-wrap border-t border-zinc-800 px-4 py-3 text-sm leading-relaxed text-zinc-400">
                {market.resolution_criteria}
              </p>
            </details>
          )}
        </>
      )}

      {running && (
        <div className="flex items-center gap-3 rounded-xl border border-zinc-800 bg-zinc-900/60 p-4 text-sm text-zinc-400">
          <span className="h-4 w-4 animate-spin rounded-full border-2 border-zinc-700 border-t-emerald-400" />
          {elapsed}s — resolving market, reading news &amp; socials, convening the AI council…
        </div>
      )}

      <DossierView result={result} fetchError={fetchError} liveMarket={market} />
    </div>
  );
}
