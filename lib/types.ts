// Mirrors backend/agent/types.py — keep in sync.

export interface StepPrompt {
  system_prompt: string;
  user_prompt: string;
}

export interface Step {
  module: string;
  prompt: StepPrompt;
  response: unknown;
}

// ---------------------------------------------------------------------------
// Markets (GET /api/markets, GET /api/market)
// ---------------------------------------------------------------------------

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
  volume24h: number;
  price_history_7d: [number, number][]; // [unix_ts, price]
}

// ---------------------------------------------------------------------------
// Dossier UI payload (populated by the pipeline from Phase 5)
// ---------------------------------------------------------------------------

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
}

export interface ExecuteOut {
  status: "ok" | "error";
  error: string | null;
  response: string | null;
  steps: Step[];
  ui?: DossierUi | null;
}
