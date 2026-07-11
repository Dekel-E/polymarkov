"use client";

import { useEffect, useState } from "react";
import { fetchNews } from "@/lib/api";
import type { NewsArticle } from "@/lib/types";

function age(date: string | null): string {
  if (!date) return "";
  const hours = Math.floor((Date.now() - new Date(date).getTime()) / 3_600_000);
  if (hours < 1) return "now";
  if (hours < 24) return `${hours}h`;
  return `${Math.floor(hours / 24)}d`;
}

export default function NewsWire() {
  const [articles, setArticles] = useState<NewsArticle[] | null>(null);

  useEffect(() => {
    fetchNews()
      .then(setArticles)
      .catch(() => setArticles([]));
  }, []);

  if (articles === null || articles.length === 0) return null; // silent until the indexer has run

  return (
    <section>
      <div className="mb-3 flex items-baseline gap-3">
        <h2 className="font-display text-lg font-bold uppercase tracking-wide">The wire</h2>
        <span className="font-mono text-[11px] text-desk-faint">
          latest indexed headlines
        </span>
      </div>
      <div className="overflow-hidden rounded-2xl border border-desk-line bg-desk-panel/60">
        {articles.slice(0, 8).map((a, i) => (
          <a
            key={i}
            href={a.url}
            target="_blank"
            rel="noreferrer"
            className="flex items-baseline gap-3 border-b border-desk-line/60 px-4 py-2.5 transition last:border-0 hover:bg-desk-raised/50"
          >
            <span className="w-8 shrink-0 font-mono text-[10px] text-instrument">
              {age(a.published_at)}
            </span>
            <span className="min-w-0 flex-1 truncate text-sm text-desk-soft">{a.title}</span>
            <span className="hidden shrink-0 font-mono text-[10px] text-desk-faint sm:block">
              {a.domain}
            </span>
          </a>
        ))}
      </div>
    </section>
  );
}
