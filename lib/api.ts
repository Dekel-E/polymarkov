import type { ExecuteOut, FillReport, MarketState, MarketSummary, Portfolio } from "./types";

function authHeaders(token?: string | null): Record<string, string> {
  return token ? { Authorization: `Bearer ${token}` } : {};
}

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

export async function fetchPortfolio(
  scope: "agent" | "mine",
  token?: string | null,
): Promise<Portfolio> {
  const res = await fetch(`/api/portfolio?scope=${scope}`, { headers: authHeaders(token) });
  if (!res.ok) throw new Error(`API returned HTTP ${res.status}`);
  const data = (await res.json()) as { portfolio: Portfolio | null; error: string | null };
  if (!data.portfolio) throw new Error(data.error ?? "portfolio unavailable");
  return data.portfolio;
}

export async function executeTrade(
  slug: string,
  side: "BUY_YES" | "BUY_NO",
  sizeUsd: number,
  token?: string | null,
): Promise<FillReport> {
  const res = await fetch("/api/trade", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify({ slug, side, size_usd: sizeUsd }),
  });
  if (!res.ok) throw new Error(`API returned HTTP ${res.status}`);
  const data = (await res.json()) as { fill: FillReport | null; error: string | null };
  if (!data.fill) throw new Error(data.error ?? "trade failed");
  return data.fill;
}

export async function closePosition(
  positionId: string,
  token?: string | null,
): Promise<{ exit_price: number; pnl: number }> {
  const res = await fetch("/api/position/close", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify({ position_id: positionId }),
  });
  if (!res.ok) throw new Error(`API returned HTTP ${res.status}`);
  const data = (await res.json()) as { error: string | null; exit_price?: number; pnl?: number };
  if (data.error) throw new Error(data.error);
  return { exit_price: data.exit_price!, pnl: data.pnl! };
}

export async function fetchMarketDetail(slug: string): Promise<MarketState> {
  const res = await fetch(`/api/market?slug=${encodeURIComponent(slug)}`);
  if (!res.ok) throw new Error(`API returned HTTP ${res.status}`);
  const data = (await res.json()) as { market: MarketState | null; error: string | null };
  if (!data.market) throw new Error(data.error ?? "Market not found");
  return data.market;
}
