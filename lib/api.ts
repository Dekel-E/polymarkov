import type {
  AgentSettings,
  AgentStats,
  ArbOpportunity,
  ExecuteOut,
  FillReport,
  FollowedWallet,
  LeaderRow,
  MarketState,
  MarketSummary,
  NewsArticle,
  Portfolio,
  WalletPosition,
  WatchItem,
} from "./types";

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

export async function searchMarkets(query: string): Promise<MarketSummary[]> {
  const res = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
  if (!res.ok) throw new Error(`API returned HTTP ${res.status}`);
  const data = (await res.json()) as { markets: MarketSummary[]; error: string | null };
  if (data.error) throw new Error(data.error);
  return data.markets;
}

export async function fetchLeague(window = "30d"): Promise<LeaderRow[]> {
  const res = await fetch(`/api/league?window=${window}`);
  if (!res.ok) throw new Error(`API returned HTTP ${res.status}`);
  const data = (await res.json()) as { leaders: LeaderRow[]; error: string | null };
  if (data.error) throw new Error(data.error);
  return data.leaders;
}

export async function fetchWalletPositions(address: string): Promise<WalletPosition[]> {
  const res = await fetch(`/api/league/wallet?address=${encodeURIComponent(address)}`);
  if (!res.ok) throw new Error(`API returned HTTP ${res.status}`);
  const data = (await res.json()) as { positions: WalletPosition[]; error: string | null };
  if (data.error) throw new Error(data.error);
  return data.positions;
}

export async function fetchAgentStats(): Promise<AgentStats> {
  const res = await fetch("/api/agent/stats");
  if (!res.ok) throw new Error(`API returned HTTP ${res.status}`);
  const data = (await res.json()) as { stats: AgentStats | null; error: string | null };
  if (!data.stats) throw new Error(data.error ?? "stats unavailable");
  return data.stats;
}

export async function fetchWatchlist(token: string): Promise<WatchItem[]> {
  const res = await fetch("/api/watchlist", { headers: authHeaders(token) });
  if (!res.ok) throw new Error(`API returned HTTP ${res.status}`);
  const data = (await res.json()) as { items: WatchItem[]; error: string | null };
  if (data.error) throw new Error(data.error);
  return data.items;
}

export async function setWatched(
  marketId: string,
  watched: boolean,
  token: string,
): Promise<void> {
  const res = await fetch(
    watched ? "/api/watchlist" : `/api/watchlist?market_id=${encodeURIComponent(marketId)}`,
    {
      method: watched ? "POST" : "DELETE",
      headers: { "Content-Type": "application/json", ...authHeaders(token) },
      body: watched ? JSON.stringify({ market_id: marketId }) : undefined,
    },
  );
  if (!res.ok) throw new Error(`API returned HTTP ${res.status}`);
  const data = (await res.json()) as { error: string | null };
  if (data.error) throw new Error(data.error);
}

export async function fetchFollowedWallets(token: string): Promise<FollowedWallet[]> {
  const res = await fetch("/api/wallets", { headers: authHeaders(token) });
  if (!res.ok) throw new Error(`API returned HTTP ${res.status}`);
  const data = (await res.json()) as { wallets: FollowedWallet[]; error: string | null };
  if (data.error) throw new Error(data.error);
  return data.wallets;
}

export async function followWallet(
  wallet: string,
  label: string,
  token: string,
): Promise<void> {
  const res = await fetch("/api/wallets", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify({ wallet, label }),
  });
  if (!res.ok) throw new Error(`API returned HTTP ${res.status}`);
  const data = (await res.json()) as { error: string | null };
  if (data.error) throw new Error(data.error);
}

export async function unfollowWallet(wallet: string, token: string): Promise<void> {
  const res = await fetch(`/api/wallets?wallet=${encodeURIComponent(wallet)}`, {
    method: "DELETE",
    headers: authHeaders(token),
  });
  if (!res.ok) throw new Error(`API returned HTTP ${res.status}`);
  const data = (await res.json()) as { error: string | null };
  if (data.error) throw new Error(data.error);
}

export async function importWallets(
  wallets: unknown[],
  token: string,
): Promise<{ imported: number; skipped: number }> {
  const res = await fetch("/api/wallets/import", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify({ wallets }),
  });
  if (!res.ok) throw new Error(`API returned HTTP ${res.status}`);
  const data = (await res.json()) as {
    imported: number;
    skipped: number;
    error: string | null;
  };
  if (data.error) throw new Error(data.error);
  return { imported: data.imported, skipped: data.skipped };
}

export async function fetchSettings(): Promise<{ settings: AgentSettings; realized_today: number }> {
  const res = await fetch("/api/settings");
  if (!res.ok) throw new Error(`API returned HTTP ${res.status}`);
  const data = (await res.json()) as {
    settings: AgentSettings | null;
    realized_today: number;
    error: string | null;
  };
  if (!data.settings) throw new Error(data.error ?? "settings unavailable");
  return { settings: data.settings, realized_today: data.realized_today };
}

export async function updateSettings(patch: {
  strategies?: Partial<AgentSettings["strategies"]>;
  risk?: Partial<AgentSettings["risk"]>;
  halt?: { active: boolean };
}): Promise<AgentSettings> {
  const res = await fetch("/api/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  if (!res.ok) throw new Error(`API returned HTTP ${res.status}`);
  const data = (await res.json()) as { settings: AgentSettings | null; error: string | null };
  if (!data.settings) throw new Error(data.error ?? "update failed");
  return data.settings;
}

export async function fetchArbitrage(fresh = false): Promise<{ opportunities: ArbOpportunity[]; cached: boolean }> {
  const res = await fetch(`/api/arbitrage${fresh ? "?fresh=true" : ""}`);
  if (!res.ok) throw new Error(`API returned HTTP ${res.status}`);
  const data = (await res.json()) as {
    opportunities: ArbOpportunity[];
    cached: boolean;
    error: string | null;
  };
  if (data.error) throw new Error(data.error);
  return { opportunities: data.opportunities, cached: data.cached };
}

export async function executeArbitrage(
  opportunity: ArbOpportunity,
  token?: string | null,
): Promise<{ slug: string; filled: boolean; vwap?: number }[]> {
  const res = await fetch("/api/arbitrage/execute", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders(token) },
    body: JSON.stringify({ opportunity }),
  });
  if (!res.ok) throw new Error(`API returned HTTP ${res.status}`);
  const data = (await res.json()) as { reports: never[]; error: string | null };
  if (data.error) throw new Error(data.error);
  return data.reports;
}

export async function fetchNews(): Promise<NewsArticle[]> {
  const res = await fetch("/api/news");
  if (!res.ok) throw new Error(`API returned HTTP ${res.status}`);
  const data = (await res.json()) as { articles: NewsArticle[]; error: string | null };
  if (data.error) throw new Error(data.error);
  return data.articles;
}

export async function fetchMarketDetail(slug: string): Promise<MarketState> {
  const res = await fetch(`/api/market?slug=${encodeURIComponent(slug)}`);
  if (!res.ok) throw new Error(`API returned HTTP ${res.status}`);
  const data = (await res.json()) as { market: MarketState | null; error: string | null };
  if (!data.market) throw new Error(data.error ?? "Market not found");
  return data.market;
}
