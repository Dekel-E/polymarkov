import type { ExecuteOut, MarketState, MarketSummary } from "./types";

export async function executeAgent(prompt: string): Promise<ExecuteOut> {
  const res = await fetch("/api/execute", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt }),
  });
  if (!res.ok) {
    throw new Error(`API returned HTTP ${res.status}`);
  }
  return (await res.json()) as ExecuteOut;
}

export async function fetchMarkets(limit = 20): Promise<MarketSummary[]> {
  const res = await fetch(`/api/markets?limit=${limit}`);
  if (!res.ok) throw new Error(`API returned HTTP ${res.status}`);
  const data = (await res.json()) as { markets: MarketSummary[]; error: string | null };
  if (data.error) throw new Error(data.error);
  return data.markets;
}

export async function fetchMarketDetail(slug: string): Promise<MarketState> {
  const res = await fetch(`/api/market?slug=${encodeURIComponent(slug)}`);
  if (!res.ok) throw new Error(`API returned HTTP ${res.status}`);
  const data = (await res.json()) as { market: MarketState | null; error: string | null };
  if (!data.market) throw new Error(data.error ?? "Market not found");
  return data.market;
}
