// Mirrors backend/agent/types.py; keep in sync.

export interface StepPrompt {
  system_prompt: string;
  user_prompt: string;
}

export interface Step {
  module: string;
  prompt: StepPrompt;
  response: unknown;
}

// Markets (GET /api/markets, GET /api/market)

export interface MarketSummary {
  id: string;
  slug: string;
  question: string;
  category: string;
  end_date: string | null;
  outcomes: string[];
  outcome_prices: number[];
  yes_token_id: string;
  mid: number;
  best_bid: number | null;
  best_ask: number | null;
  spread: number | null;
  volume24h: number;
  one_day_change: number | null;
  image: string;
  event_title: string;
}

export interface MarketState {
  question: string;
  slug: string;
  end_date: string | null;
  resolution_criteria: string;
  category: string;
  yes_token_id: string;
  mid: number;
  best_bid: number | null;
  best_ask: number | null;
  spread: number | null;
  depth_at_ask_usd: number;
  depth_at_no_ask_usd: number | null;
  volume24h: number;
  price_history_7d: [number, number][]; // [unix_ts, price]
}

// Dossier UI payload

export interface EvidenceCluster {
  id: string;
  headline: string;
  date: string | null;
  source: string;
  url: string;
  summary: string;
  sentiment: number | null;
  stance: "yes" | "no" | "neutral" | null;
}

export interface SocialPulse {
  posts: {
    id: string;
    text: string;
    source: string;
    url: string;
    created_at: string | null;
    sentiment: number | null;
  }[];
  mention_velocity: number | null;
  note: string;
}

export interface PersonaOpinion {
  thesis: string;
  estimated_probability: number;
  confidence: "low" | "medium" | "high";
  red_flags: string[];
}

export interface VerdictData {
  verdict: "BUY_YES" | "BUY_NO" | "PASS";
  fair_probability: number;
  net_edge_pts: number;
  confidence: "low" | "medium" | "high";
  suggested_size_pct_bankroll: number;
  summary: string;
  key_risks: string[];
}

export interface FillReport {
  position_id: string;
  side: "BUY_YES" | "BUY_NO";
  size_usd: number;
  vwap: number;
  slippage_bps: number;
  fee_paid: number;
  levels_consumed: number;
}

export interface DossierUi {
  cached_at?: string | null;
  verdict?: VerdictData;
  market?: MarketState;
  news?: EvidenceCluster[];
  social?: SocialPulse;
  council?: {
    bull?: PersonaOpinion;
    bear?: PersonaOpinion;
    quant?: PersonaOpinion;
    skeptic?: PersonaOpinion;
  };
  fill?: FillReport | null;
  step_metrics?: StepMetric[]; // per-step latency/tokens, index-aligned with steps
  microstructure?: Microstructure | null;
  smart_money?: SmartMoneyFlow | null;
}

// Order-book + price technicals (MicrostructureScanner)
export interface Microstructure {
  imbalance: number | null;
  micro_price: number | null;
  micro_vs_mid_pts: number | null;
  bid_depth_5c_usd: number;
  ask_depth_5c_usd: number;
  spread_pct: number | null;
  momentum_24h_pts: number | null;
  momentum_7d_pts: number | null;
  volatility_pts: number | null;
  trend: string;
  rsi: number | null;
  volume24h_usd: number;
}

// Tracked/top-wallet flow in a market (SmartMoneyScanner)
export interface WalletFlow {
  wallet: string;
  label: string;
  rank?: number | null;
  yes_lean_usd: number;
  notional_usd: number;
  side: "YES" | "NO";
}
export interface SmartMoneyFlow {
  net_yes_usd: number;
  followed_active: WalletFlow[];
  top_active: WalletFlow[];
  whale_prints: { wallet: string; side: string; outcome: string; notional_usd: number }[];
  trades_scanned: number;
  note: string;
}

// Per-step run cost, aligned with ExecuteOut.steps by index (GUI-only, not graded).
export interface StepMetric {
  kind: "llm" | "tool";
  latency_ms: number | null;
  tokens_in: number;
  tokens_out: number;
}

// Portfolio (GET /api/portfolio)

export interface Position {
  id: string;
  market_id: string; // slug
  side: "BUY_YES" | "BUY_NO";
  entry_price: number;
  size_usd: number;
  fee_paid: number;
  slippage_bps: number;
  fair_prob_at_entry: number | null;
  opened_at: string;
  status: "open" | "resolved";
  resolved_outcome: string | null;
  resolved_at: string | null;
  pnl: number | null;
  strategy: string | null;
  sl_price: number | null;
  tp_price: number | null;
  // enrichment on open rows
  current_price?: number | null;
  unrealized_pnl?: number | null;
  category?: string;
}

export interface PortfolioStats {
  bankroll_usd: number;
  balance_usd: number;
  available_usd: number;
  equity_usd: number;
  open_positions: number;
  open_exposure_usd: number;
  open_fees_usd: number;
  unrealized_pnl_usd: number;
  resolved_positions: number;
  realized_pnl_usd: number;
  win_rate: number | null;
  largest_position_pct: number;
  exposure_by_strategy: Record<string, number>;
  exposure_by_category: Record<string, number>;
}

export interface WorkingQuote {
  id: string;
  market_id: string;
  bid: number;
  ask: number;
  size_usd: number;
  mid_at_placement: number | null;
  placed_at: string;
}

export interface EquitySnapshot {
  day: string;
  equity_usd: number;
  balance_usd: number;
  realized_pnl_usd: number;
  unrealized_pnl_usd: number;
}

export interface Portfolio {
  open: Position[];
  resolved: Position[];
  stats: PortfolioStats;
  equity_history?: EquitySnapshot[];
}

// Smart Money League, watchlist, agent stats

export interface LeaderRow {
  rank: number;
  wallet: string;
  name: string;
  pnl: number;
  volume: number;
  image: string;
  verified: boolean;
}

export interface WalletPosition {
  market: string;
  slug: string;
  event_slug: string;
  outcome: string;
  size_usd: number;
  pnl: number;
  avg_price: number;
  current_price: number;
}

// Strategy Desk

export interface AgentSettings {
  strategies: {
    ai_signal: boolean;
    arbitrage: boolean;
    copy_trading: boolean;
    market_making: boolean;
    correlation: boolean;
  };
  risk: {
    stop_loss_pct: number;
    take_profit_pct: number;
    max_position_usd: number;
    max_open_positions: number;
    daily_loss_halt_usd: number;
  };
  halt: { active: boolean; reason: string; at: string };
  funds: { bankroll_usd: number };
}

export interface ArbLeg {
  slug: string;
  side: "BUY_YES" | "BUY_NO";
  price: number;
  size_usd: number;
}

export interface ArbOpportunity {
  type: "spread" | "dutch_book" | "correlation";
  question: string;
  event_title: string;
  cost_per_share: number;
  fees_per_share: number;
  profit_per_share: number;
  roi_pct: number;
  max_shares: number;
  guaranteed_profit_usd: number;
  legs: ArbLeg[];
}

export interface NewsArticle {
  title: string;
  url: string;
  domain: string;
  published_at: string | null;
}

export interface FollowedWallet {
  wallet: string;
  label: string;
}

export interface WatchItem {
  market_id: string;
  question: string;
  last_mid: number | null;
  category: string;
  verdict: string | null;
  fair_probability: number | null;
  analyzed_at: string | null;
}

export interface AgentStats {
  total_runs: number;
  verdicts: Record<string, number>;
  avg_latency_s: number | null;
  total_tokens_out: number;
  calibration: {
    scored_runs: number;
    resolved_markets: number;
    forecast_runs: number;
    forecast_markets: number;
    resolution_coverage_pct: number;
    sample_status: "early" | "developing" | "established";
    sample_warning: string | null;
    agent_brier: number;
    market_brier: number;
    brier_skill_vs_market: number | null;
    agent_log_loss: number;
    market_log_loss: number;
    expected_calibration_error: number;
    buckets: CalibrationBucket[];
    latest_per_market: CalibrationMetrics & { markets: number };
  } | null;
  recent: {
    market_id: string | null;
    verdict: string | null;
    fair_prob: number | null;
    mid_at_run: number | null;
    latency_ms: number | null;
    created_at: string;
  }[];
}

export interface CalibrationBucket {
  range: string;
  count: number;
  mean_forecast: number;
  outcome_rate: number;
  absolute_gap: number;
}

export interface CalibrationMetrics {
  agent_brier: number;
  market_brier: number;
  brier_skill_vs_market: number | null;
  agent_log_loss: number;
  market_log_loss: number;
  expected_calibration_error: number;
  buckets: CalibrationBucket[];
}

export interface ExecuteOut {
  status: "ok" | "error";
  error: string | null;
  response: string | null;
  steps: Step[];
  ui?: DossierUi | null;
}
