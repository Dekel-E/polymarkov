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

export interface ChatTurn {
  role: "user" | "assistant";
  content: string;
}

export async function executeAgent(prompt: string, history: ChatTurn[] = []): Promise<ExecuteOut> {
  // ?ui=1 adds the structured dossier payload on top of the graded envelope.
  const res = await fetch("/api/execute?ui=1", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt, history }),
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

export async function fetchPortfolio(): Promise<Portfolio> {
  const res = await fetch("/api/portfolio");
  if (!res.ok) throw new Error(`API returned HTTP ${res.status}`);
  const data = (await res.json()) as { portfolio: Portfolio | null; error: string | null };
  if (!data.portfolio) throw new Error(data.error ?? "portfolio unavailable");
  return data.portfolio;
}

export async function executeTrade(
  slug: string,
  side: "BUY_YES" | "BUY_NO",
  sizeUsd: number,
): Promise<FillReport> {
  const res = await fetch("/api/trade", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ slug, side, size_usd: sizeUsd }),
  });
  if (!res.ok) throw new Error(`API returned HTTP ${res.status}`);
  const data = (await res.json()) as { fill: FillReport | null; error: string | null };
  if (!data.fill) throw new Error(data.error ?? "trade failed");
  return data.fill;
}

export async function closePosition(
  positionId: string,
  fraction = 1.0,
): Promise<{ exit_price: number; pnl: number; closed_fraction: number }> {
  const res = await fetch("/api/position/close", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ position_id: positionId, fraction }),
  });
  if (!res.ok) throw new Error(`API returned HTTP ${res.status}`);
  const data = (await res.json()) as {
    error: string | null;
    exit_price?: number;
    pnl?: number;
    closed_fraction?: number;
  };
  if (data.error) throw new Error(data.error);
  return { exit_price: data.exit_price!, pnl: data.pnl!, closed_fraction: data.closed_fraction ?? 1 };
}

export async function setPositionLimits(
  positionId: string,
  slPrice: number | null,
  tpPrice: number | null,
): Promise<void> {
  const res = await fetch("/api/position/limits", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ position_id: positionId, sl_price: slPrice, tp_price: tpPrice }),
  });
  if (!res.ok) throw new Error(`API returned HTTP ${res.status}`);
  const data = (await res.json()) as { error: string | null };
  if (data.error) throw new Error(data.error);
}

export async function fetchWorkingQuotes(): Promise<import("./types").WorkingQuote[]> {
  const res = await fetch("/api/quotes");
  if (!res.ok) throw new Error(`API returned HTTP ${res.status}`);
  const data = (await res.json()) as {
    quotes: import("./types").WorkingQuote[];
    error: string | null;
  };
  if (data.error) throw new Error(data.error);
  return data.quotes;
}

export async function cancelQuote(quoteId: string): Promise<void> {
  const res = await fetch("/api/quotes/cancel", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ quote_id: quoteId }),
  });
  if (!res.ok) throw new Error(`API returned HTTP ${res.status}`);
  const data = (await res.json()) as { error: string | null };
  if (data.error) throw new Error(data.error);
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

export async function fetchWatchlist(): Promise<WatchItem[]> {
  const res = await fetch("/api/watchlist");
  if (!res.ok) throw new Error(`API returned HTTP ${res.status}`);
  const data = (await res.json()) as { items: WatchItem[]; error: string | null };
  if (data.error) throw new Error(data.error);
  return data.items;
}

export async function setWatched(marketId: string, watched: boolean): Promise<void> {
  const res = await fetch(
    watched ? "/api/watchlist" : `/api/watchlist?market_id=${encodeURIComponent(marketId)}`,
    {
      method: watched ? "POST" : "DELETE",
      headers: { "Content-Type": "application/json" },
      body: watched ? JSON.stringify({ market_id: marketId }) : undefined,
    },
  );
  if (!res.ok) throw new Error(`API returned HTTP ${res.status}`);
  const data = (await res.json()) as { error: string | null };
  if (data.error) throw new Error(data.error);
}

export async function fetchFollowedWallets(): Promise<FollowedWallet[]> {
  const res = await fetch("/api/wallets");
  if (!res.ok) throw new Error(`API returned HTTP ${res.status}`);
  const data = (await res.json()) as { wallets: FollowedWallet[]; error: string | null };
  if (data.error) throw new Error(data.error);
  return data.wallets;
}

export async function followWallet(wallet: string, label: string): Promise<void> {
  const res = await fetch("/api/wallets", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ wallet, label }),
  });
  if (!res.ok) throw new Error(`API returned HTTP ${res.status}`);
  const data = (await res.json()) as { error: string | null };
  if (data.error) throw new Error(data.error);
}

export async function unfollowWallet(wallet: string): Promise<void> {
  const res = await fetch(`/api/wallets?wallet=${encodeURIComponent(wallet)}`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error(`API returned HTTP ${res.status}`);
  const data = (await res.json()) as { error: string | null };
  if (data.error) throw new Error(data.error);
}

export async function importWallets(
  wallets: unknown[],
): Promise<{ imported: number; skipped: number }> {
  const res = await fetch("/api/wallets/import", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
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
  funds?: { bankroll_usd: number };
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

export interface ArbLegReport {
  slug: string;
  filled: boolean;
  side?: string;
  vwap?: number;
  size_usd?: number;
  position_id?: string;
  error?: string;
}

export async function executeArbitrage(opportunity: ArbOpportunity): Promise<ArbLegReport[]> {
  const res = await fetch("/api/arbitrage/execute", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ opportunity }),
  });
  if (!res.ok) throw new Error(`API returned HTTP ${res.status}`);
  const data = (await res.json()) as { reports: ArbLegReport[]; error: string | null };
  if (data.error) throw new Error(data.error);
  return data.reports;
}

export interface ActivityEvent {
  type: "analysis" | "trade" | "settle";
  at: string;
  market_id: string | null;
  verdict?: string | null;
  latency_ms?: number | null;
  side?: string;
  size_usd?: number;
  strategy?: string | null;
  outcome?: string | null;
  pnl?: number | null;
}

export async function fetchActivity(): Promise<ActivityEvent[]> {
  const res = await fetch("/api/activity");
  if (!res.ok) throw new Error(`API returned HTTP ${res.status}`);
  const data = (await res.json()) as { events: ActivityEvent[]; error: string | null };
  if (data.error) throw new Error(data.error);
  return data.events;
}

export async function fetchMarketNews(slug: string): Promise<NewsArticle[]> {
  const res = await fetch(`/api/market/news?slug=${encodeURIComponent(slug)}`);
  if (!res.ok) throw new Error(`API returned HTTP ${res.status}`);
  const data = (await res.json()) as { articles: NewsArticle[]; error: string | null };
  if (data.error) throw new Error(data.error);
  return data.articles;
}

export interface MarketChatResult {
  answer: string | null;
  citations: { title: string; url: string }[];
  gathered?: {
    searched: boolean;
    queries: string[];
    articles: number;
    articles_indexed: number;
    social_posts: number;
  };
  dossier_age_min?: number | null;
  error: string | null;
}

export async function marketChat(
  slug: string,
  question: string,
  history: { role: "user" | "assistant"; content: string }[],
): Promise<MarketChatResult> {
  const res = await fetch("/api/market/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ slug, question, history }),
  });
  if (!res.ok) throw new Error(`API returned HTTP ${res.status}`);
  const data = (await res.json()) as MarketChatResult;
  if (data.error) throw new Error(data.error);
  return data;
}

export interface DeskChatResult extends MarketChatResult {
  market?: { slug: string; question: string } | null;
  // action side-effects the omni-chat can produce
  settings?: AgentSettings | null; // control instruction applied
  applied?: Record<string, { from: unknown; to: unknown }> | null;
  fill?: FillReport | null; // paper trade placed
  watchlisted?: { slug: string; action: "add" | "remove" } | null;
}

export async function deskChat(
  question: string,
  history: ChatTurn[],
  slug?: string,
): Promise<DeskChatResult> {
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, history, slug: slug ?? null }),
  });
  if (!res.ok) throw new Error(`API returned HTTP ${res.status}`);
  const data = (await res.json()) as DeskChatResult;
  if (data.error) throw new Error(data.error);
  return data;
}

export interface StrategyChatResult {
  answer: string | null;
  applied: Record<string, { from: unknown; to: unknown }> | null;
  settings: AgentSettings | null;
  error: string | null;
}

export async function strategyChat(
  question: string,
  history: ChatTurn[],
): Promise<StrategyChatResult> {
  const res = await fetch("/api/strategy/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, history }),
  });
  if (!res.ok) throw new Error(`API returned HTTP ${res.status}`);
  const data = (await res.json()) as StrategyChatResult;
  if (data.error) throw new Error(data.error);
  return data;
}

export async function fetchMarketDetail(slug: string): Promise<MarketState> {
  const res = await fetch(`/api/market?slug=${encodeURIComponent(slug)}`);
  if (!res.ok) throw new Error(`API returned HTTP ${res.status}`);
  const data = (await res.json()) as { market: MarketState | null; error: string | null };
  if (!data.market) throw new Error(data.error ?? "Market not found");
  return data.market;
}
